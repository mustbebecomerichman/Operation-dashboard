#Requires -Version 5.1
<#
Fixes single-quoted JS strings that lost their closing quote to mojibake.
Pattern: '<text>??<terminator>  where terminator ∈ ; , ) ] } : +
              should be:  '<text>…'<terminator>

Strategy: walk the file character by character, tracking string state.
When inside a '-string and we see "??" followed by a terminator that
implies the string MUST have closed, insert the missing closing quote.
#>

$ErrorActionPreference = 'Stop'
$file = Join-Path (Split-Path -Parent $PSScriptRoot) 'delay_dashboard.html'
$content = Get-Content -LiteralPath $file -Raw -Encoding UTF8

# Tokenize-light: walk chars. Track:
#   inHtmlTag — between < and >
#   inComment — // line comment
#   inSingle / inDouble — string state
$inHtmlTag = $false
$inComment = $false
$inSingle = $false
$inDouble = $false
$prev = ''
$result = New-Object System.Text.StringBuilder
$fixes = 0
$i = 0
$len = $content.Length

# Terminators that imply prior string MUST end
$terminators = @{ ';'=$true; ','=$true; ')'=$true; ']'=$true; '}'=$true; ':'=$true; '+'=$true }

while ($i -lt $len) {
    $ch = $content[$i]

    # Reset per-line state
    if ($ch -eq "`n") {
        $inComment = $false
        # Note: strings shouldn't cross lines in this codebase; reset to be safe
        $inSingle = $false
        $inDouble = $false
        [void]$result.Append($ch)
        $prev = $ch
        $i++
        continue
    }

    if ($inComment) {
        [void]$result.Append($ch)
        $prev = $ch
        $i++
        continue
    }

    if ($inHtmlTag) {
        if ($ch -eq '>') { $inHtmlTag = $false }
        [void]$result.Append($ch)
        $prev = $ch
        $i++
        continue
    }

    # Detect // comment start (only outside strings)
    if (-not $inSingle -and -not $inDouble -and $ch -eq '/' -and $i+1 -lt $len -and $content[$i+1] -eq '/') {
        $inComment = $true
        [void]$result.Append($ch)
        $prev = $ch
        $i++
        continue
    }

    if (-not $inSingle -and -not $inDouble) {
        if ($ch -eq "'" -and $prev -ne '\') { $inSingle = $true; [void]$result.Append($ch); $prev=$ch; $i++; continue }
        if ($ch -eq '"' -and $prev -ne '\') { $inDouble = $true; [void]$result.Append($ch); $prev=$ch; $i++; continue }
        [void]$result.Append($ch)
        $prev = $ch
        $i++
        continue
    }

    if ($inDouble) {
        if ($ch -eq '"' -and $prev -ne '\') { $inDouble = $false }
        [void]$result.Append($ch)
        $prev = $ch
        $i++
        continue
    }

    # inSingle == true
    if ($ch -eq "'" -and $prev -ne '\') {
        $inSingle = $false
        [void]$result.Append($ch)
        $prev = $ch
        $i++
        continue
    }

    # Look for '??<terminator>' broken pattern while inside a single-quoted string
    if ($ch -eq '?' -and $i+2 -lt $len -and $content[$i+1] -eq '?') {
        $look = 2
        while ($i + $look -lt $len -and $content[$i+$look] -eq ' ') { $look++ }   # skip trailing spaces
        if ($i + $look -lt $len) {
            $next = $content[$i+$look]
            if ($terminators.ContainsKey([string]$next)) {
                # Heuristic: this is the broken-close-quote pattern.
                # Replace '??' with '…' (one ellipsis char), then close string, then continue.
                [void]$result.Append([char]0x2026)   # …
                [void]$result.Append("'")
                $inSingle = $false
                $i += 2   # consumed both ?
                $fixes++
                $prev = "'"
                continue
            }
        }
    }

    [void]$result.Append($ch)
    $prev = $ch
    $i++
}

$out = $result.ToString()
Set-Content -LiteralPath $file -Value $out -NoNewline -Encoding UTF8
"fixed $fixes broken single-quoted strings"
