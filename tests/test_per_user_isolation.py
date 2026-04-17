"""Tests for per-user isolation via ContextVar HERMES_HOME override.

Covers:
- ContextVar set/get/clear lifecycle
- Async task isolation (two concurrent tasks see different paths)
- Thread propagation via copy_context()
- Dynamic path resolution for skills, memory, config, state.db
- SessionDB isolation per user
- CLI/Cron fallback (ContextVar not set → env var)
"""

import asyncio
import contextvars
import os
import threading
from pathlib import Path

import pytest

from hermes_constants import (
    get_hermes_home,
    get_skills_dir,
    get_config_path,
    get_env_path,
    set_hermes_home_ctx,
    _HERMES_HOME_CTX,
)


# ---------------------------------------------------------------------------
# ContextVar basic lifecycle
# ---------------------------------------------------------------------------

class TestContextVarLifecycle:
    """Basic set / get / clear behavior."""

    def test_default_returns_env_var(self, tmp_path, monkeypatch):
        """When ContextVar is not set, get_hermes_home() reads HERMES_HOME env var."""
        fake = tmp_path / "env_home"
        fake.mkdir()
        monkeypatch.setenv("HERMES_HOME", str(fake))
        set_hermes_home_ctx(None)
        assert get_hermes_home() == fake

    def test_contextvar_overrides_env(self, tmp_path, monkeypatch):
        """ContextVar takes priority over HERMES_HOME env var."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / "env"))
        ctx_path = tmp_path / "ctx_user"
        set_hermes_home_ctx(str(ctx_path))
        try:
            assert get_hermes_home() == ctx_path
        finally:
            set_hermes_home_ctx(None)

    def test_clear_restores_env(self, tmp_path, monkeypatch):
        """Setting ContextVar to None restores env-var behavior."""
        env_path = tmp_path / "env_home"
        env_path.mkdir()
        monkeypatch.setenv("HERMES_HOME", str(env_path))
        set_hermes_home_ctx(str(tmp_path / "override"))
        set_hermes_home_ctx(None)
        assert get_hermes_home() == env_path

    def test_accepts_path_object(self, tmp_path):
        """set_hermes_home_ctx() accepts Path objects."""
        set_hermes_home_ctx(tmp_path / "from_path")
        try:
            assert get_hermes_home() == tmp_path / "from_path"
        finally:
            set_hermes_home_ctx(None)

    def test_none_clears_override(self):
        """Passing None explicitly clears the override."""
        set_hermes_home_ctx("/tmp/something")
        set_hermes_home_ctx(None)
        assert _HERMES_HOME_CTX.get(None) is None


# ---------------------------------------------------------------------------
# Dynamic path resolution
# ---------------------------------------------------------------------------

class TestDynamicPathResolution:
    """All path helpers follow the ContextVar override."""

    def test_get_skills_dir_follows_ctx(self, tmp_path):
        set_hermes_home_ctx(str(tmp_path / "user_x"))
        try:
            assert get_skills_dir() == tmp_path / "user_x" / "skills"
        finally:
            set_hermes_home_ctx(None)

    def test_get_config_path_follows_ctx(self, tmp_path):
        set_hermes_home_ctx(str(tmp_path / "user_x"))
        try:
            assert get_config_path() == tmp_path / "user_x" / "config.yaml"
        finally:
            set_hermes_home_ctx(None)

    def test_get_env_path_follows_ctx(self, tmp_path):
        set_hermes_home_ctx(str(tmp_path / "user_x"))
        try:
            assert get_env_path() == tmp_path / "user_x" / ".env"
        finally:
            set_hermes_home_ctx(None)

    def test_memory_dir_follows_ctx(self, tmp_path):
        from tools.memory_tool import get_memory_dir
        set_hermes_home_ctx(str(tmp_path / "user_x"))
        try:
            assert get_memory_dir() == tmp_path / "user_x" / "memories"
        finally:
            set_hermes_home_ctx(None)

    def test_skills_hub_paths_follow_ctx(self, tmp_path):
        try:
            from tools.skills_hub import _hub_dir, _lock_file, _taps_file
        except ImportError:
            pytest.skip("skills_hub dependencies not available")
        set_hermes_home_ctx(str(tmp_path / "user_x"))
        try:
            assert _hub_dir() == tmp_path / "user_x" / "skills" / ".hub"
            assert _lock_file() == tmp_path / "user_x" / "skills" / ".hub" / "lock.json"
            assert _taps_file() == tmp_path / "user_x" / "skills" / ".hub" / "taps.json"
        finally:
            set_hermes_home_ctx(None)

    def test_default_db_path_follows_ctx(self, tmp_path):
        from hermes_state import _default_db_path
        set_hermes_home_ctx(str(tmp_path / "user_x"))
        try:
            assert _default_db_path() == tmp_path / "user_x" / "state.db"
        finally:
            set_hermes_home_ctx(None)


# ---------------------------------------------------------------------------
# Async task isolation
# ---------------------------------------------------------------------------

class TestAsyncIsolation:
    """Each asyncio Task gets its own ContextVar value."""

    def test_two_tasks_isolated(self):
        """Two concurrent asyncio tasks see different HERMES_HOME values."""
        results = {}

        async def task(name, path):
            set_hermes_home_ctx(path)
            await asyncio.sleep(0)  # yield to other task
            results[name] = str(get_hermes_home())

        async def run():
            await asyncio.gather(
                task("a", "/tmp/user_a"),
                task("b", "/tmp/user_b"),
            )

        asyncio.run(run())
        set_hermes_home_ctx(None)
        assert results["a"] == "/tmp/user_a"
        assert results["b"] == "/tmp/user_b"

    def test_task_does_not_leak_to_parent(self):
        """ContextVar set in a child task does not affect the parent."""
        async def run():
            set_hermes_home_ctx(None)
            parent_before = _HERMES_HOME_CTX.get(None)

            async def child():
                set_hermes_home_ctx("/tmp/child")

            await asyncio.create_task(child())
            parent_after = _HERMES_HOME_CTX.get(None)
            return parent_before, parent_after

        before, after = asyncio.run(run())
        set_hermes_home_ctx(None)
        assert before is None
        assert after is None

    def test_many_concurrent_tasks(self):
        """10 concurrent tasks each see their own isolated path."""
        results = {}

        async def task(i):
            path = f"/tmp/user_{i}"
            set_hermes_home_ctx(path)
            await asyncio.sleep(0)
            results[i] = str(get_hermes_home())

        async def run():
            await asyncio.gather(*(task(i) for i in range(10)))

        asyncio.run(run())
        set_hermes_home_ctx(None)
        for i in range(10):
            assert results[i] == f"/tmp/user_{i}"


# ---------------------------------------------------------------------------
# Thread propagation via copy_context()
# ---------------------------------------------------------------------------

class TestThreadPropagation:
    """copy_context() correctly propagates ContextVar to threads."""

    def test_copy_context_propagates(self, tmp_path):
        """Thread launched with copy_context().run() sees the ContextVar."""
        result = {}

        set_hermes_home_ctx(str(tmp_path / "user_thread"))
        ctx = contextvars.copy_context()

        def worker():
            result["home"] = str(get_hermes_home())
            result["skills"] = str(get_skills_dir())

        t = threading.Thread(target=ctx.run, args=(worker,))
        t.start()
        t.join()
        set_hermes_home_ctx(None)

        assert result["home"] == str(tmp_path / "user_thread")
        assert result["skills"] == str(tmp_path / "user_thread" / "skills")

    def test_plain_thread_does_not_see_ctx(self, tmp_path, monkeypatch):
        """A plain thread (no copy_context) does NOT see the ContextVar."""
        env_home = tmp_path / "env_home"
        env_home.mkdir()
        monkeypatch.setenv("HERMES_HOME", str(env_home))
        result = {}

        set_hermes_home_ctx(str(tmp_path / "should_not_see"))

        def worker():
            result["home"] = str(get_hermes_home())

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        set_hermes_home_ctx(None)

        # Plain thread starts with empty ContextVar → falls back to env var
        assert result["home"] == str(env_home)


# ---------------------------------------------------------------------------
# SessionDB isolation
# ---------------------------------------------------------------------------

class TestSessionDBIsolation:
    """Each user gets an independent state.db."""

    def test_per_user_db_path(self, tmp_path):
        from hermes_state import SessionDB
        user_dir = tmp_path / "user_profiles" / "user_a"
        user_dir.mkdir(parents=True)
        db = SessionDB(db_path=user_dir / "state.db")
        assert db.db_path == user_dir / "state.db"
        assert db.db_path.exists()

    def test_two_users_separate_dbs(self, tmp_path):
        from hermes_state import SessionDB
        dir_a = tmp_path / "user_a"
        dir_a.mkdir()
        dir_b = tmp_path / "user_b"
        dir_b.mkdir()
        db_a = SessionDB(db_path=dir_a / "state.db")
        db_b = SessionDB(db_path=dir_b / "state.db")
        assert db_a.db_path != db_b.db_path
        assert db_a.db_path.exists()
        assert db_b.db_path.exists()

    def test_default_db_respects_contextvar(self, tmp_path):
        """SessionDB() without explicit path uses ContextVar-aware default."""
        from hermes_state import SessionDB
        user_dir = tmp_path / "user_ctx"
        user_dir.mkdir()
        set_hermes_home_ctx(str(user_dir))
        try:
            db = SessionDB()
            assert db.db_path == user_dir / "state.db"
        finally:
            set_hermes_home_ctx(None)


# ---------------------------------------------------------------------------
# Profile directory structure
# ---------------------------------------------------------------------------

class TestProfileDirectory:
    """User profile directory creation logic."""

    def test_create_profile_subdirs(self, tmp_path):
        """Verify the profile directory structure matches the plan."""
        user_profile = tmp_path / "user_profiles" / "ou_abc123"
        for subdir in ("memories", "skills", "sessions", "logs"):
            (user_profile / subdir).mkdir(parents=True, exist_ok=True)

        assert (user_profile / "memories").is_dir()
        assert (user_profile / "skills").is_dir()
        assert (user_profile / "sessions").is_dir()
        assert (user_profile / "logs").is_dir()

    def test_memory_writes_to_user_profile(self, tmp_path):
        """When ContextVar is set, memory_tool writes to the user's directory."""
        from tools.memory_tool import get_memory_dir
        user_dir = tmp_path / "user_profiles" / "ou_abc123"
        user_dir.mkdir(parents=True)
        (user_dir / "memories").mkdir()

        set_hermes_home_ctx(str(user_dir))
        try:
            mem_dir = get_memory_dir()
            assert mem_dir == user_dir / "memories"
            # Write a test file
            (mem_dir / "MEMORY.md").write_text("test memory")
            assert (user_dir / "memories" / "MEMORY.md").read_text() == "test memory"
        finally:
            set_hermes_home_ctx(None)


# ---------------------------------------------------------------------------
# CLI/Cron fallback (no ContextVar)
# ---------------------------------------------------------------------------

class TestFallbackBehavior:
    """When ContextVar is not set, everything falls back to env var."""

    def test_cli_uses_env_var(self, tmp_path, monkeypatch):
        """CLI mode: ContextVar is None, HERMES_HOME env var is used."""
        cli_home = tmp_path / "cli_home"
        cli_home.mkdir()
        monkeypatch.setenv("HERMES_HOME", str(cli_home))
        set_hermes_home_ctx(None)
        assert get_hermes_home() == cli_home
        assert get_skills_dir() == cli_home / "skills"

    def test_default_without_env_var(self, tmp_path, monkeypatch):
        """No ContextVar, no HERMES_HOME → defaults to ~/.hermes."""
        monkeypatch.delenv("HERMES_HOME", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        set_hermes_home_ctx(None)
        assert get_hermes_home() == tmp_path / ".hermes"
