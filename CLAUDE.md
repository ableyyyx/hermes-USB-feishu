# Hermes Agent - Claude Code Harness

## Startup Workflow

Before writing code:
1. Read this file (CLAUDE.md)
2. Read `AGENTS.md` for architecture, patterns, and known pitfalls
3. Run `./init.sh` to verify environment health
4. Read `feature_list.json` for current feature status
5. Read `progress.md` for session continuity context

## Working Rules

- One feature at a time. Complete and verify before moving to the next.
- Always use `get_hermes_home()` from `hermes_constants` for paths. Never hardcode `~/.hermes`.
- All tool handlers MUST return a JSON string.
- Do not break prompt caching: no mid-conversation context changes.
- Module-level caches of `get_hermes_home()` are forbidden in Gateway-loaded modules. Use dynamic `get_skills_dir()`, `get_config_path()`, etc. See "Per-User Isolation" below.
- Run the relevant test subset before claiming a change is done.

## Per-User Isolation (ContextVar Architecture)

The gateway uses `ContextVar` to isolate each Feishu user's data:

```
~/.hermes/user_profiles/{user_id}/
  memories/   skills/   sessions/   logs/   state.db   config.yaml
```

**Rules:**
- `hermes_constants.py` defines `_HERMES_HOME_CTX` ContextVar
- `set_hermes_home_ctx()` is called in `gateway/run.py:_run_agent()` before agent dispatch
- `_run_in_executor_with_context()` uses `copy_context()` to propagate to threads
- Gateway's `_hermes_home` (61 refs in `gateway/run.py`) is **shared infrastructure** (config.yaml, .env, operational files) -- do NOT convert to dynamic calls
- Only tools that access **per-user data** (memory, skills, sessions) need dynamic resolution
- Background threads (`_spawn_background_review`, `_flush_memories`) must use `copy_context()`

### Operator-Level Config Must Use Base Home

**CRITICAL**: Functions that read **operator config** (model routing, API keys, provider) must NOT be affected by the per-user ContextVar. These are shared across ALL gateway users:

| Path | Category | Must use |
|------|----------|----------|
| `config.yaml` | Model routing, API keys | Base home |
| `auth.json` | Credentials | Base home (TODO) |
| `.env` | API keys | Base home ✅ (module-level `_env_path`) |

**Pattern for operator-config functions** (see `hermes_cli/runtime_provider.py:_get_model_config()`):
```python
from hermes_constants import _HERMES_HOME_CTX, set_hermes_home_ctx
_ctx_override = _HERMES_HOME_CTX.get(None)
if _ctx_override is not None:
    set_hermes_home_ctx(None)
try:
    config = load_config()   # reads from base home
finally:
    if _ctx_override is not None:
        set_hermes_home_ctx(_ctx_override)
```

**Why this matters**: When ContextVar points to a user profile (no `config.yaml`), `load_config()` returns empty config → provider defaults to "auto" → OpenRouter → HTTP 401. This was observed in production with real Feishu users on 2026-04-17.

**All `load_config()` calls inside Gateway-mode code must use this pattern** — including AIAgent initialization (`run_agent.py:1196`) and any future config reads.

**Preferred fix** (already applied): `get_config_path()` and `get_env_path()` in `hermes_constants.py` now always bypass the ContextVar via `_get_base_hermes_home()`. Any function that calls `load_config()` automatically gets the correct base config without extra ceremony.

## Three Identity/Memory Files

| File | Path | Owner | Trigger |
|------|------|-------|---------|
| `SOUL.md` | `get_hermes_home()/SOUL.md` | Operator (setup wizard) | Created at profile init via `ensure_hermes_home()` |
| `MEMORY.md` | `get_memory_dir()/MEMORY.md` | Agent (memory tool) | Every `nudge_interval` turns (default 10), OR `/reset` after ≥4 msgs |
| `USER.md` | `get_memory_dir()/USER.md` | Agent (user_profile tool) | Same as MEMORY.md |

**To trigger MEMORY.md creation** for a new user:
1. Have a conversation of ≥4 messages, then send `/reset` — OR
2. Have a conversation of ≥10 turns (background review fires automatically)

**SOUL.md** is pre-created at profile init and is the agent's personality. It's per-user by default (each user has their own agent identity at their profile path). It does NOT require conversation — it already exists.

## Verification Commands

```bash
source .venv/bin/activate
python -m pytest tests/ -q                        # Full suite (~3000 tests)
python -m pytest tests/test_hermes_constants.py -q # Constants & ContextVar
python -m pytest tests/tools/ -q                   # Tool tests
python -m pytest tests/gateway/ -q                 # Gateway tests
python -c "import hermes_constants; print('OK')"   # Quick import check
```

## Definition of Done

A feature is done when:
- [ ] Implementation complete
- [ ] Relevant tests pass (or new tests added)
- [ ] No syntax errors across modified files (`py_compile`)
- [ ] `feature_list.json` updated
- [ ] `progress.md` updated with session summary

## End of Session

Before ending:
1. Update `progress.md` with what was done, decisions made, and open questions
2. Update `feature_list.json` status for any features worked on
3. List any blockers or risks discovered
4. Ensure all modified files pass syntax check

## Environment & Dependency Management

### Python Virtual Environment

**Location**: `/home/kevin/tongyuan/hermes-USB-feishu/.venv/`

**Package Manager**: `uv` (NOT pip)
- This is a uv-managed virtual environment
- pip is NOT installed in the venv
- Always use `uv pip install <package>` to install packages

**Common Mistakes**:
```bash
# ❌ WRONG - These will fail:
pip install qrcode[pil]
python -m pip install qrcode[pil]
pip3 install --user qrcode[pil]

# ✅ CORRECT - Use uv:
uv pip install qrcode[pil]
```

**Activation**:
```bash
source /home/kevin/tongyuan/hermes-USB-feishu/.venv/bin/activate
```

### Dashboard Startup

**Command**: `hermes dashboard` (NOT `hermes web`)

```bash
cd /home/kevin/tongyuan/hermes-USB-feishu
source .venv/bin/activate
hermes dashboard  # Correct command
```

### Frontend Build

**Build Command**:
```bash
cd /home/kevin/tongyuan/hermes-USB-feishu/web
npm run build
```

**Output Location**: Built files go to `../hermes_cli/web_dist/`

### Common Issues & Solutions

**Issue**: "No module named 'qrcode'"
- **Solution**: `uv pip install qrcode[pil]`

**Issue**: "pip: command not found" in venv
- **Solution**: Use `uv pip` instead (uv-managed venv)

**Issue**: "externally-managed-environment"
- **Solution**: Don't use system pip, activate venv and use `uv pip`

**Issue**: Polling keeps running after dialog close
- **Solution**: Use `useRef` to track and clear timeouts in React

**Issue**: QR code shows ERR_CONNECTION_RESET
- **Solution**: Generate QR as base64 image server-side

**Issue**: 401 Unauthorized on public endpoint
- **Solution**: Add endpoint to `_PUBLIC_API_PATHS` or bypass in auth middleware

For more details, see `ENVIRONMENT_NOTES.md`.
