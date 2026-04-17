#!/bin/bash
set -e

echo "=== Hermes Agent — Environment Verification ==="
echo ""

# Check Python venv
if [ -d ".venv" ]; then
    PYTHON=".venv/bin/python"
elif [ -d "venv" ]; then
    PYTHON="venv/bin/python"
else
    PYTHON="python3"
fi

if ! command -v "$PYTHON" &>/dev/null; then
    echo "FAIL: Python not found ($PYTHON)"
    exit 1
fi
echo "OK: Python — $($PYTHON --version)"

# Syntax check on critical files
echo ""
echo "=== Syntax Check (critical files) ==="
CRITICAL_FILES=(
    hermes_constants.py
    hermes_state.py
    run_agent.py
    gateway/run.py
    tools/skills_tool.py
    tools/skill_manager_tool.py
    tools/skills_hub.py
    tools/skills_sync.py
)

FAIL=0
for f in "${CRITICAL_FILES[@]}"; do
    if [ -f "$f" ]; then
        if $PYTHON -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
            echo "  OK: $f"
        else
            echo "  FAIL: $f"
            FAIL=1
        fi
    fi
done

if [ $FAIL -ne 0 ]; then
    echo ""
    echo "FAIL: Syntax errors detected"
    exit 1
fi

# Import check
echo ""
echo "=== Import Check ==="
$PYTHON -c "
import hermes_constants
from hermes_constants import get_hermes_home, set_hermes_home_ctx, get_skills_dir
print('  OK: hermes_constants')

import hermes_state
print('  OK: hermes_state')

import tools.skills_tool
print('  OK: tools.skills_tool')

import tools.skill_manager_tool
print('  OK: tools.skill_manager_tool')

import tools.skills_hub
print('  OK: tools.skills_hub')

import tools.skills_sync
print('  OK: tools.skills_sync')
"

# ContextVar isolation smoke test
echo ""
echo "=== ContextVar Isolation Test ==="
$PYTHON -c "
from hermes_constants import get_hermes_home, set_hermes_home_ctx, get_skills_dir
import asyncio

# Default
default = str(get_hermes_home())

# Override
set_hermes_home_ctx('/tmp/test_isolation')
override = str(get_hermes_home())
skills = str(get_skills_dir())

# Clear
set_hermes_home_ctx(None)
cleared = str(get_hermes_home())

assert override == '/tmp/test_isolation', f'Override failed: {override}'
assert skills == '/tmp/test_isolation/skills', f'Skills failed: {skills}'
assert cleared == default, f'Clear failed: {cleared} != {default}'
print('  OK: ContextVar override + clear works')

# Async isolation
async def test():
    async def a():
        set_hermes_home_ctx('/tmp/a')
        await asyncio.sleep(0)
        return str(get_hermes_home())
    async def b():
        set_hermes_home_ctx('/tmp/b')
        await asyncio.sleep(0)
        return str(get_hermes_home())
    ra, rb = await asyncio.gather(a(), b())
    assert ra == '/tmp/a' and rb == '/tmp/b', f'Async isolation failed: {ra}, {rb}'
    print('  OK: Async task isolation works')
asyncio.run(test())
set_hermes_home_ctx(None)
"

echo ""
echo "=== Verification Complete ==="
