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
