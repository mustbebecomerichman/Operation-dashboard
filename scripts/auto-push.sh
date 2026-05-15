#!/usr/bin/env bash
# Bumps delay_dashboard.html version (patch +1) when it changed,
# then commits and pushes any uncommitted work to origin/main.
#
# Invoked automatically by the Claude Code Stop hook on Mac/Linux
# (see ../.claude/settings.json) — runs once per Claude turn.
#
# Safe to run manually:
#     bash scripts/auto-push.sh
#
# Exits 0 silently if there is nothing to commit.

set -euo pipefail

# Always run relative to the repo root.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." &> /dev/null && pwd)"
cd "$REPO_ROOT"

# Anything to do?
if [[ -z "$(git status --porcelain)" ]]; then
  echo "[auto-push] clean tree — nothing to push"
  exit 0
fi

# Bump delay_dashboard.html version only if the dashboard itself is dirty.
DASHBOARD="$REPO_ROOT/delay_dashboard.html"
BUMPED_VER=""

if [[ -n "$(git status --porcelain -- 'delay_dashboard.html')" && -f "$DASHBOARD" ]]; then
  # Find version: 'X.Y.Z'  → bump Z
  if grep -qE "version:\s*'[0-9]+\.[0-9]+\.[0-9]+'" "$DASHBOARD"; then
    CUR=$(grep -oE "version:\s*'[0-9]+\.[0-9]+\.[0-9]+'" "$DASHBOARD" | head -1 | sed -E "s/.*'([0-9]+)\.([0-9]+)\.([0-9]+)'/\1.\2.\3/")
    MAJOR=$(echo "$CUR" | cut -d. -f1)
    MINOR=$(echo "$CUR" | cut -d. -f2)
    PATCH=$(echo "$CUR" | cut -d. -f3)
    PATCH=$((PATCH + 1))
    BUMPED_VER="$MAJOR.$MINOR.$PATCH"

    # In-place replacement, BSD/GNU sed compatible
    if sed --version >/dev/null 2>&1; then
      sed -i -E "0,/version:[[:space:]]*'[0-9]+\.[0-9]+\.[0-9]+'/{s/version:[[:space:]]*'[0-9]+\.[0-9]+\.[0-9]+'/version: '$BUMPED_VER'/}" "$DASHBOARD"
    else
      # BSD sed (macOS): no easy "first match only", emulate by using a temp file with awk
      awk -v new="$BUMPED_VER" '
        !done && match($0, /version:[[:space:]]*'\''[0-9]+\.[0-9]+\.[0-9]+'\''/) {
          $0 = substr($0,1,RSTART-1) "version: '\''" new "'\''" substr($0, RSTART+RLENGTH); done=1
        } { print }
      ' "$DASHBOARD" > "$DASHBOARD.tmp" && mv "$DASHBOARD.tmp" "$DASHBOARD"
    fi
    echo "[auto-push] bumped dashboard version -> $BUMPED_VER"
  else
    echo "[auto-push] dashboard changed but no version literal found — skipping bump"
  fi
fi

git add -A >/dev/null

if [[ -z "$(git diff --cached --name-only)" ]]; then
  echo "[auto-push] no staged changes after add — nothing to commit"
  exit 0
fi

# Pre-push gate: validate inline JS. Same as the GitHub Actions step.
VALIDATOR="$REPO_ROOT/scripts/validate-html-js.js"
if [[ -f "$VALIDATOR" ]]; then
  if command -v node >/dev/null 2>&1; then
    echo "[auto-push] running JS syntax validator…"
    if ! node "$VALIDATOR" 2>&1 | sed 's/^/[validator] /'; then
      echo "[auto-push] validator failed — aborting push. Fix the errors above and re-run." >&2
      exit 1
    fi
  else
    echo "[auto-push] node not found on PATH — skipping local validator (CI will still gate the push)."
  fi
fi

STAGED=$(git diff --cached --name-only | sed 's/^/  - /')
if [[ -n "$BUMPED_VER" ]]; then
  TITLE="chore(dashboard): auto v$BUMPED_VER"
else
  TITLE="chore: auto-update"
fi

MSG=$(cat <<EOF
$TITLE

Auto-pushed by Claude Code Stop hook.

Changed:
$STAGED

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)

git commit -m "$MSG" >/dev/null
git push origin main 2>&1 | sed 's/^/[auto-push] /'
echo "[auto-push] done${BUMPED_VER:+ (v$BUMPED_VER)}"
