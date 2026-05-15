#!/usr/bin/env node
/**
 * validate-html-js.js
 *
 * Extracts every inline <script> block from the repo's HTML files and verifies
 * they parse as valid JavaScript. Also smoke-checks any Apps Script .gs file.
 *
 * Exits with non-zero if any block fails to parse. Used by:
 *   - GitHub Actions (.github/workflows/validate.yml) — gates `main`
 *   - scripts/auto-push.ps1 — gates local commits
 *
 * Run manually:
 *   node scripts/validate-html-js.js
 *
 * Why this exists: the dashboard HTML once shipped with mojibake-induced
 * syntax errors that silently disabled the entire app in modern browsers.
 * This validator catches that class of bug before it reaches users.
 */

'use strict';

const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..');

// Files to check
const htmlFiles = ['delay_dashboard.html', 'index.html', 'hrci.html'];
const gsFiles = ['apps-script/seavantage-proxy.gs'];

let totalErrors = 0;

function locateLineCol(body, message) {
    // Best-effort: bisect to find the first failing line.
    const lines = body.split('\n');
    let lastOk = -1;
    for (let i = 0; i < lines.length; i++) {
        const chunk = lines.slice(0, i + 1).join('\n');
        try { new Function(chunk); lastOk = i; }
        catch (e) {
            // Only treat as "real" if not just incompleteness
            if (e.message !== 'Unexpected end of input' && !e.message.includes('Unexpected token')) {
                return { line: i + 1, snippet: (lines[i] || '').slice(0, 200) };
            }
        }
    }
    return { line: lastOk + 2, snippet: (lines[lastOk + 1] || '').slice(0, 200) };
}

function validateScriptBody(filePath, body, blockIndex) {
    try {
        // eslint-disable-next-line no-new-func
        new Function(body);
        return true;
    } catch (e) {
        totalErrors++;
        const loc = locateLineCol(body, e.message);
        console.error(`✗ ${filePath} [script #${blockIndex}] ${e.message}`);
        console.error(`    at script-body line ${loc.line}: ${loc.snippet}`);
        return false;
    }
}

function validateHtml(relPath) {
    const fullPath = path.join(repoRoot, relPath);
    if (!fs.existsSync(fullPath)) {
        console.log(`  skip: ${relPath} (not present)`);
        return;
    }
    const html = fs.readFileSync(fullPath, 'utf8');
    const blocks = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)];
    if (blocks.length === 0) {
        console.log(`  ${relPath}: no inline <script> blocks`);
        return;
    }
    let okCount = 0;
    blocks.forEach((m, i) => {
        if (validateScriptBody(relPath, m[1], i)) okCount++;
    });
    console.log(`  ${relPath}: ${okCount}/${blocks.length} script block(s) OK`);
}

function validateGs(relPath) {
    const fullPath = path.join(repoRoot, relPath);
    if (!fs.existsSync(fullPath)) {
        console.log(`  skip: ${relPath} (not present)`);
        return;
    }
    const body = fs.readFileSync(fullPath, 'utf8');
    // Apps Script V8 runtime is ES2019-ish. new Function gives us a close-enough check.
    try {
        // eslint-disable-next-line no-new-func
        new Function(body);
        console.log(`  ${relPath}: OK`);
    } catch (e) {
        totalErrors++;
        const loc = locateLineCol(body, e.message);
        console.error(`✗ ${relPath} ${e.message}`);
        console.error(`    at line ${loc.line}: ${loc.snippet}`);
    }
}

console.log('Validating inline JS in HTML files…');
htmlFiles.forEach(validateHtml);

console.log('\nValidating Apps Script .gs files…');
gsFiles.forEach(validateGs);

console.log('');
if (totalErrors > 0) {
    console.error(`FAILED — ${totalErrors} script block(s) did not parse.`);
    process.exit(1);
} else {
    console.log('OK — all script blocks parse cleanly.');
}
