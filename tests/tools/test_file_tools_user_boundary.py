"""Tests for file tools user boundary validation in gateway mode.

Regression test for security vulnerability where User A could access
User B's files by directly specifying paths outside their profile.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch
from tools.file_tools import (
    read_file_tool,
    write_file_tool,
    patch_tool,
    search_tool,
    _is_gateway_mode,
    _validate_user_boundary,
)


class TestGatewayModeDetection:
    """Test gateway mode detection logic."""

    def test_cli_mode_no_contextvar(self):
        """CLI mode: no ContextVar override."""
        from hermes_constants import _HERMES_HOME_CTX
        _HERMES_HOME_CTX.set(None)
        os.environ.pop("HERMES_GATEWAY_SESSION", None)
        assert _is_gateway_mode() is False

    def test_gateway_mode_with_contextvar(self):
        """Gateway mode: ContextVar is set."""
        from hermes_constants import _HERMES_HOME_CTX
        _HERMES_HOME_CTX.set("/tmp/user_profiles/ou_test123")
        assert _is_gateway_mode() is True
        _HERMES_HOME_CTX.set(None)  # cleanup

    def test_gateway_mode_with_env_marker(self):
        """Gateway mode: HERMES_GATEWAY_SESSION env var."""
        from hermes_constants import _HERMES_HOME_CTX
        _HERMES_HOME_CTX.set(None)
        os.environ["HERMES_GATEWAY_SESSION"] = "1"
        assert _is_gateway_mode() is True
        os.environ.pop("HERMES_GATEWAY_SESSION")


class TestUserBoundaryValidation:
    """Test user boundary validation logic."""

    def test_cli_mode_allows_any_path(self, tmp_path):
        """CLI mode: no restrictions on file access."""
        from hermes_constants import _HERMES_HOME_CTX
        _HERMES_HOME_CTX.set(None)

        outside_file = tmp_path / "outside.txt"
        error = _validate_user_boundary(str(outside_file), "read")
        assert error is None

    def test_gateway_mode_allows_within_profile(self, tmp_path):
        """Gateway mode: allow access within user's profile."""
        from hermes_constants import _HERMES_HOME_CTX
        user_profile = tmp_path / "user_profiles" / "ou_user_a"
        user_profile.mkdir(parents=True)

        _HERMES_HOME_CTX.set(str(user_profile))

        user_file = user_profile / "memories" / "test.md"
        user_file.parent.mkdir()
        user_file.write_text("content")

        error = _validate_user_boundary(str(user_file), "read")
        assert error is None

        _HERMES_HOME_CTX.set(None)  # cleanup

    def test_gateway_mode_blocks_other_user_profile(self, tmp_path):
        """Gateway mode: block access to other user's profile."""
        from hermes_constants import _HERMES_HOME_CTX

        user_a_profile = tmp_path / "user_profiles" / "ou_user_a"
        user_b_profile = tmp_path / "user_profiles" / "ou_user_b"
        user_a_profile.mkdir(parents=True)
        user_b_profile.mkdir(parents=True)

        # User A's context
        _HERMES_HOME_CTX.set(str(user_a_profile))

        # Try to access User B's file
        user_b_file = user_b_profile / "memories" / "USER.md"
        user_b_file.parent.mkdir()
        user_b_file.write_text("User B's secrets")

        error = _validate_user_boundary(str(user_b_file), "read")
        assert error is not None
        assert "Access denied" in error
        assert "outside your profile directory" in error

        _HERMES_HOME_CTX.set(None)  # cleanup

    def test_gateway_mode_blocks_traversal_attack(self, tmp_path):
        """Gateway mode: block path traversal to escape profile."""
        from hermes_constants import _HERMES_HOME_CTX

        user_profile = tmp_path / "user_profiles" / "ou_user_a"
        user_profile.mkdir(parents=True)

        _HERMES_HOME_CTX.set(str(user_profile))

        # Try to traverse up and access another user
        traversal_path = str(user_profile / ".." / "ou_user_b" / "memories" / "USER.md")

        error = _validate_user_boundary(traversal_path, "read")
        assert error is not None
        assert "Access denied" in error

        _HERMES_HOME_CTX.set(None)  # cleanup


class TestReadFileUserBoundary:
    """Test read_file_tool user boundary enforcement."""

    def test_read_file_blocks_cross_user_access(self, tmp_path):
        """read_file_tool must block access to other user's files in gateway mode."""
        from hermes_constants import _HERMES_HOME_CTX
        import json

        user_a_profile = tmp_path / "user_profiles" / "ou_user_a"
        user_b_profile = tmp_path / "user_profiles" / "ou_user_b"
        user_a_profile.mkdir(parents=True)
        user_b_profile.mkdir(parents=True)

        # User B's secret file
        user_b_secret = user_b_profile / "memories" / "USER.md"
        user_b_secret.parent.mkdir()
        user_b_secret.write_text("User B's personal info")

        # User A's context
        _HERMES_HOME_CTX.set(str(user_a_profile))

        # User A tries to read User B's file
        result = read_file_tool(str(user_b_secret))
        result_dict = json.loads(result)

        assert "error" in result_dict
        assert "Access denied" in result_dict["error"]
        assert "outside your profile directory" in result_dict["error"]

        _HERMES_HOME_CTX.set(None)  # cleanup


class TestWriteFileUserBoundary:
    """Test write_file_tool user boundary enforcement."""

    def test_write_file_blocks_cross_user_access(self, tmp_path):
        """write_file_tool must block writes to other user's files."""
        from hermes_constants import _HERMES_HOME_CTX
        import json

        user_a_profile = tmp_path / "user_profiles" / "ou_user_a"
        user_b_profile = tmp_path / "user_profiles" / "ou_user_b"
        user_a_profile.mkdir(parents=True)
        user_b_profile.mkdir(parents=True)

        # User A's context
        _HERMES_HOME_CTX.set(str(user_a_profile))

        # User A tries to write to User B's directory
        target_path = user_b_profile / "memories" / "injected.md"
        result = write_file_tool(str(target_path), "malicious content")
        result_dict = json.loads(result)

        assert "error" in result_dict
        assert "Access denied" in result_dict["error"]

        _HERMES_HOME_CTX.set(None)  # cleanup


class TestSearchFilesUserBoundary:
    """Test search_files_tool user boundary enforcement."""

    def test_search_blocks_cross_user_directory(self, tmp_path):
        """search_files_tool must block searches in other user's directories."""
        from hermes_constants import _HERMES_HOME_CTX
        import json

        user_a_profile = tmp_path / "user_profiles" / "ou_user_a"
        user_b_profile = tmp_path / "user_profiles" / "ou_user_b"
        user_a_profile.mkdir(parents=True)
        user_b_profile.mkdir(parents=True)

        # User A's context
        _HERMES_HOME_CTX.set(str(user_a_profile))

        # User A tries to search User B's directory
        result = search_tool(pattern="secret", path=str(user_b_profile))
        result_dict = json.loads(result)

        assert "error" in result_dict
        assert "Access denied" in result_dict["error"]

        _HERMES_HOME_CTX.set(None)  # cleanup


