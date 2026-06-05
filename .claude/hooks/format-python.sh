#!/usr/bin/env bash
# Stop hook: auto-format all modified Python files with ruff at end of generation.

set -euo pipefail

cd "$CLAUDE_PROJECT_DIR" || exit 0

# Find all modified/added Python files (staged + unstaged + untracked)
MODIFIED_FILES=$(git diff --name-only --diff-filter=ACMR HEAD -- '*.py' 2>/dev/null || true)
UNSTAGED_FILES=$(git diff --name-only --diff-filter=ACMR -- '*.py' 2>/dev/null || true)
UNTRACKED_FILES=$(git ls-files --others --exclude-standard -- '*.py' 2>/dev/null || true)

ALL_FILES=$(echo -e "${MODIFIED_FILES}\n${UNSTAGED_FILES}\n${UNTRACKED_FILES}" | sort -u | grep -v '^$' || true)

[[ -z "$ALL_FILES" ]] && exit 0

while IFS= read -r file; do
    [[ -f "$file" ]] || continue
    uv run ruff check --fix "$file" 2>/dev/null || true
    uv run ruff format "$file" 2>/dev/null || true
done <<< "$ALL_FILES"

exit 0
