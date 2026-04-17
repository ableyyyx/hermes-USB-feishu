# Session Progress Log

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
- feat-003: Write pytest tests for ContextVar isolation
- feat-004: Integration test with Feishu gateway
- Update AGENTS.md to document the new module-level cache prohibition for Gateway modules
