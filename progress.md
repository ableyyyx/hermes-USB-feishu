# Session Progress Log

## Session: 2026-04-17 (Hotfix: Operator Config + ContextVar Scope)

### Completed
- **feat-005**: Fix `_get_model_config()` reading from user profile (HTTP 401 bug)
  - **Root cause**: ContextVar → `load_config()` → `get_config_path()` → user profile (no config.yaml) → empty config → provider="auto" → OpenRouter → 401
  - **Fix**: `hermes_cli/runtime_provider.py:_get_model_config()` temporarily clears ContextVar before `load_config()`
  - **Documented**: New pitfall in AGENTS.md, new rule in CLAUDE.md "Operator-Level Config Must Use Base Home"
  - **Lesson**: ContextVar scope must be limited to PER-USER DATA only. Operator config (model routing, API keys) is always shared and must use base home.
  - Observed with real Feishu users: ou_0e9710d3c71ae6a6b89a640460e845d1, ou_2ff2be6c69f565f4f9a6c51730c053cf, ou_e35410f852dacadaced24f89d5743de1

### Open Questions / Future Work
- `auth.json` is also per-user (written to user profile by `ensure_hermes_home()`). Currently OK because user profile auth.json inherits credentials on creation. But if credentials change, user profiles won't auto-update. Consider making auth.json use base home too.
- Other files in user profile that shouldn't be there: `SOUL.md`, `models_dev_cache.json`, `cron/`. These are side effects of `ensure_hermes_home()` running with ContextVar set. Non-critical for now.

---

## Session: 2026-04-17 (Per-User Isolation + Harness Setup)

### Completed
- **feat-001**: Per-user isolation via ContextVar in `hermes_constants.py`
  - Added `_HERMES_HOME_CTX` ContextVar with `set_hermes_home_ctx()` setter
  - Modified `get_hermes_home()` to check ContextVar first (priority: ContextVar > env var > default)
  - Eliminated module-level caches in 6 tool/state files (skills_tool, skill_manager_tool, skills_hub, skills_sync, hermes_state, session_search_tool)
  - Gateway integration: ContextVar set in `_run_agent()`, per-user SessionDB cache, cleanup in finally block
  - Background task propagation: `copy_context()` for flush memories, background review thread
  - **Key decision**: 61 `_hermes_home` refs in gateway/run.py are shared infrastructure (config, .env, operational files) -- left untouched
  - 12 files changed, ~208 lines added, ~111 removed

- **feat-002**: Harness infrastructure (CLAUDE.md, feature_list.json, progress.md, init.sh)

### Key Decisions
- ContextVar approach (Plan B) chosen over memory-only subdirectories (Plan A) or multi-process (Plan C) for balance of isolation strength and operational simplicity
- `.env` and API keys remain shared (not per-user) -- loaded from base profile
- CLI and Cron modes unaffected (ContextVar defaults to None, falls back to env var)

### Open Questions
- Should `config.yaml` be copied per-user, or should users inherit from base profile?
- Need integration test with real Feishu gateway to verify end-to-end isolation
- Should per-user `state.db` connections be cleaned up on session expiry?

### Next Steps
- Update AGENTS.md to document the new module-level cache prohibition for Gateway modules (done)
- Real-world testing with live Feishu gateway deployment
- Consider adding per-user `config.yaml` copy on profile creation

---

## Session: 2026-04-17 (Tests for Per-User Isolation)

### Completed
- **feat-003**: 23 unit tests in `tests/test_per_user_isolation.py`
  - ContextVar lifecycle (set/get/clear/Path-object/None)
  - Dynamic path resolution (skills_dir, config_path, env_path, memory_dir, skills_hub, state.db)
  - Async task isolation (2 tasks, parent leak check, 10 concurrent tasks)
  - Thread propagation (copy_context vs plain thread)
  - SessionDB isolation (per-user path, two separate DBs, ContextVar-aware default)
  - Profile directory structure and memory writes
  - CLI/Cron fallback behavior
  - Updated `tests/conftest.py` to clear ContextVar in `_isolate_hermes_home` fixture

- **feat-004**: 10 integration tests in `tests/gateway/test_per_user_gateway_isolation.py`
  - Profile directory creation with subdirs
  - Two users get separate dirs
  - ContextVar set/clear lifecycle
  - Concurrent users isolated (async gather)
  - User A cannot see User B's memory
  - Per-user SessionDB cache
  - Session data isolation (get_session cross-check)
  - copy_context thread propagation
  - asyncio.create_task inherits context
  - Shared infrastructure (.env) unaffected

### Test Results
- 32 passed, 1 skipped (httpx not in system Python), 0 failed
