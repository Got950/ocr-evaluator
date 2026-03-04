#!/bin/bash
# Checks for common secret patterns before committing
echo "Checking for secrets..."
echo ""

echo "=== API keys (sk-) ==="
grep -rn "sk-" . --include="*.py" --exclude-dir=".git" --exclude-dir="venv" --exclude-dir=".venv" || echo "  (none found)"

echo ""
echo "=== Hardcoded passwords ==="
grep -rn "password\s*=\s*['\"][^'\"]\+['\"]" . --include="*.py" --exclude-dir=".git" --exclude-dir="venv" --exclude-dir=".venv" || echo "  (none found)"

echo ""
echo "=== Hardcoded secrets ==="
grep -rn "secret\s*=\s*['\"][^'\"]\+['\"]" . --include="*.py" --exclude-dir=".git" --exclude-dir="venv" --exclude-dir=".venv" || echo "  (none found)"

echo ""
echo "=== Hardcoded API keys ==="
grep -rn "api_key\s*=\s*['\"][^'\"]\+['\"]" . --include="*.py" --exclude-dir=".git" --exclude-dir="venv" --exclude-dir=".venv" || echo "  (none found)"

echo ""
echo "=== AWS credentials ==="
grep -rn "AKIA[0-9A-Z]\{16\}" . --include="*.py" --exclude-dir=".git" --exclude-dir="venv" --exclude-dir=".venv" || echo "  (none found)"

echo ""
echo "=== .env file check ==="
if [ -f ".env" ]; then
    echo "  WARNING: .env file exists — make sure it's in .gitignore"
else
    echo "  OK: no .env file found (good for commits)"
fi

echo ""
echo "Done. Review any matches above before pushing."
