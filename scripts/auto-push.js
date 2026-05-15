#!/usr/bin/env node
/**
 * Cross-platform dispatcher for the Claude Code Stop hook.
 * Picks the right shell-script for the current OS so the same
 * `.claude/settings.json` hook works on Windows, macOS, and Linux.
 *
 * On Windows  → scripts/auto-push.ps1 (PowerShell)
 * On *nix     → scripts/auto-push.sh  (bash)
 *
 * Both scripts behave identically: bump dashboard version, validate JS,
 * commit, and push. Exits 0 silently when the tree is clean.
 */
const { spawnSync } = require('child_process');
const path = require('path');

const isWin = process.platform === 'win32';
const scriptsDir = __dirname;

let cmd, args;
if (isWin) {
  cmd = 'powershell';
  args = [
    '-ExecutionPolicy', 'Bypass',
    '-NoProfile',
    '-File', path.join(scriptsDir, 'auto-push.ps1'),
  ];
} else {
  cmd = 'bash';
  args = [path.join(scriptsDir, 'auto-push.sh')];
}

const r = spawnSync(cmd, args, { stdio: 'inherit' });
if (r.error) {
  console.error('[auto-push.js] failed to spawn', cmd, '-', r.error.message);
  process.exit(1);
}
process.exit(r.status ?? 0);
