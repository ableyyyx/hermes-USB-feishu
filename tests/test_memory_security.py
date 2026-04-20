"""Tests for memory file security validation in gateway mode.

Regression test for ensuring memory files (SOUL.md, MEMORY.md, USER.md)
are protected from cross-user access in multi-user gateway deployments.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch


class TestGatewayModeDetection:
    """Test gateway mode detection logic for memory files."""

    def test_cli_mode_no_contextvar(self):
        """CLI mode: no ContextVar override."""
        from hermes_constants import _HERMES_HOME_CTX
        from tools.memory_tool import _is_gateway_mode

        _HERMES_HOME_CTX.set(None)
        os.environ.pop("HERMES_GATEWAY_SESSION", None)
        assert _is_gateway_mode() is False

    def test_gateway_mode_with_contextvar(self):
        """Gateway mode: ContextVar is set."""
        from hermes_constants import _HERMES_HOME_CTX
        from tools.memory_tool import _is_gateway_mode

        _HERMES_HOME_CTX.set("/tmp/user_profiles/ou_test123")
        assert _is_gateway_mode() is True
        _HERMES_HOME_CTX.set(None)  # cleanup

    def test_gateway_mode_with_env_marker(self):
        """Gateway mode: HERMES_GATEWAY_SESSION env var."""
        from hermes_constants import _HERMES_HOME_CTX
        from tools.memory_tool import _is_gateway_mode

        _HERMES_HOME_CTX.set(None)
        os.environ["HERMES_GATEWAY_SESSION"] = "1"
        assert _is_gateway_mode() is True
        os.environ.pop("HERMES_GATEWAY_SESSION")


class TestMemoryPathValidation:
    """Test memory file path validation logic."""

    def test_cli_mode_allows_any_path(self, tmp_path):
        """CLI mode: no restrictions on memory file access."""
        from hermes_constants import _HERMES_HOME_CTX
        from tools.memory_tool import _validate_memory_path

        _HERMES_HOME_CTX.set(None)

        outside_file = tmp_path / "outside" / "MEMORY.md"
        # Should not raise in CLI mode
        _validate_memory_path(outside_file, "MEMORY")

    def test_gateway_mode_allows_within_profile(self, tmp_path):
        """Gateway mode: allow access within user's profile."""
        from hermes_constants import _HERMES_HOME_CTX
        from tools.memory_tool import _validate_memory_path

        user_profile = tmp_path / "user_profiles" / "ou_user_a"
        user_profile.mkdir(parents=True)

        _HERMES_HOME_CTX.set(str(user_profile))

        memory_file = user_profile / "memories" / "MEMORY.md"
        memory_file.parent.mkdir()

        # Should not raise
        _validate_memory_path(memory_file, "MEMORY")

        _HERMES_HOME_CTX.set(None)  # cleanup

    def test_gateway_mode_blocks_other_user_memory(self, tmp_path):
        """Gateway mode: block access to other user's memory files."""
        from hermes_constants import _HERMES_HOME_CTX
        from tools.memory_tool import _validate_memory_path, SecurityError

        user_a_profile = tmp_path / "user_profiles" / "ou_user_a"
        user_b_profile = tmp_path / "user_profiles" / "ou_user_b"
        user_a_profile.mkdir(parents=True)
        user_b_profile.mkdir(parents=True)

        # User A's context
        _HERMES_HOME_CTX.set(str(user_a_profile))

        # Try to access User B's memory file
        user_b_memory = user_b_profile / "memories" / "MEMORY.md"

        with pytest.raises(SecurityError) as exc_info:
            _validate_memory_path(user_b_memory, "MEMORY")

        assert "access denied" in str(exc_info.value).lower()
        assert "outside your profile directory" in str(exc_info.value)

        _HERMES_HOME_CTX.set(None)  # cleanup


class TestMemoryStoreValidation:
    """Test MemoryStore load/save with path validation."""

    def test_load_from_disk_validates_paths(self, tmp_path):
        """MemoryStore.load_from_disk validates paths in gateway mode."""
        from hermes_constants import _HERMES_HOME_CTX, set_hermes_home_ctx
        from tools.memory_tool import MemoryStore, SecurityError

        user_a = tmp_path / "user_profiles" / "ou_user_a"
        user_b = tmp_path / "user_profiles" / "ou_user_b"
        user_a.mkdir(parents=True)
        user_b.mkdir(parents=True)

        # Create memory files for user A
        (user_a / "memories").mkdir()
        (user_a / "memories" / "MEMORY.md").write_text("User A memory")
        (user_a / "memories" / "USER.md").write_text("User A profile")

        # User A's context - should work
        set_hermes_home_ctx(str(user_a))
        store = MemoryStore()
        store.load_from_disk()  # Should not raise

        _HERMES_HOME_CTX.set(None)  # cleanup


class TestSOULPathValidation:
    """Test SOUL.md path validation in prompt_builder."""

    def test_load_soul_md_validates_path(self, tmp_path):
        """load_soul_md validates path in gateway mode."""
        from hermes_constants import set_hermes_home_ctx, _HERMES_HOME_CTX
        from agent.prompt_builder import load_soul_md

        user_profile = tmp_path / "user_profiles" / "ou_user_a"
        user_profile.mkdir(parents=True)

        # Create SOUL.md
        soul_path = user_profile / "SOUL.md"
        soul_path.write_text("I am an AI assistant.")

        # User A's context - should work
        set_hermes_home_ctx(str(user_profile))
        result = load_soul_md()
        assert result is not None
        assert "AI assistant" in result

        _HERMES_HOME_CTX.set(None)  # cleanup


class TestAuditLogging:
    """Test security audit logging for failed access attempts."""

    def test_failed_access_logged(self, tmp_path):
        """Failed memory access attempts are logged."""
        from hermes_constants import _HERMES_HOME_CTX
        from tools.memory_tool import _validate_memory_path, SecurityError

        user_a = tmp_path / "user_profiles" / "ou_user_a"
        user_b = tmp_path / "user_profiles" / "ou_user_b"
        user_a.mkdir(parents=True)
        user_b.mkdir(parents=True)

        # User A's context
        _HERMES_HOME_CTX.set(str(user_a))

        # Create logs directory
        (user_a / "logs").mkdir()

        # Try to access User B's file (should fail and log)
        user_b_file = user_b / "memories" / "MEMORY.md"

        with pytest.raises(SecurityError):
            _validate_memory_path(user_b_file, "MEMORY")

        # Check log file exists
        log_file = user_a / "logs" / "memory_security.log"
        assert log_file.exists()

        # Check log content
        log_content = log_file.read_text()
        assert "memory_access_denied" in log_content
        assert "MEMORY" in log_content

        _HERMES_HOME_CTX.set(None)  # cleanup

