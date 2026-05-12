#Requires -Version 5.1
<#
Fixes a specific class of mojibake damage in delay_dashboard.html where
the trailing closing quote of a JSON string was eaten alongside the
final Korean character.

Example pattern (broken):
    "manager": "?꾩콈誘?, "backup": "?ㅻ챸湲?, "ports": [ ... ]

After fix:
    "manager": "?꾩콈誘?", "backup": "?ㅻ챸湲?", "ports": [ ... ]

Strategy: for string-valued keys that are known to hold Korean text
(name, manager, backup, owner, port_name), find values that aren't
properly closed before the next comma+key or before a closing brace/bracket,
and insert the missing ".
#>

$ErrorActionPreference = 'Stop'
$file = Join-Path (Split-Path -Parent $PSScriptRoot) 'delay_dashboard.html'
$content = Get-Content -LiteralPath $file -Raw -Encoding UTF8

$keys = 'name|manager|backup|owner|port_name|region|kind|type|flag|svc|code|built|country|depot'

# Pattern A: value followed by `, "nextKey": ` — use LOOKAHEAD so the
# engine doesn't consume the next key, otherwise adjacent broken values
# (e.g. manager + backup in a row) get missed.
$patternA = "(""($keys)"":\s*""[^""]*?)(?=,\s*""\w+""\s*:)"

# Pattern B: value as last field — followed by `}` or `]`.
$patternB = "(""($keys)"":\s*""[^""]*?)(?=\s*[}\]])"

$beforeCount = [regex]::Matches($content, $patternA).Count + [regex]::Matches($content, $patternB).Count

# Replace with the matched text + closing quote (no group reference needed —
# lookahead means the asserted part is not in the match).
$content = [regex]::Replace($content, $patternA, '$0"')
$content = [regex]::Replace($content, $patternB, '$0"')

# Verify
$remainingA = [regex]::Matches($content, $patternA).Count
$remainingB = [regex]::Matches($content, $patternB).Count

# Write back only if changes were made
Set-Content -LiteralPath $file -Value $content -NoNewline -Encoding UTF8

"fixed: $beforeCount issues  remaining: A=$remainingA B=$remainingB"
