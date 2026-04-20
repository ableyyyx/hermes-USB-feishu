"""Tests for path disclosure prevention in agent responses.

Regression test for vulnerability where agent revealed other users'
absolute paths, enabling cross-user enumeration and access.
"""

import pytest
from pathlib import Path
from hermes_constants import display_hermes_home, _HERMES_HOME_CTX


class TestPathDisclosurePrevention:
    """Test that user IDs are sanitized in displayed paths."""

    def test_cli_mode_shows_normal_path(self, tmp_path):
        """CLI mode: show normal path without sanitization."""
        _HERMES_HOME_CTX.set(None)
        # In real CLI mode, would show ~/.hermes
        # This test just verifies no crash
        result = display_hermes_home()
        assert result is not None

    def test_gateway_mode_hides_user_id(self, tmp_path):
        """Gateway mode: sanitize user ID from displayed path."""
        user_profile = tmp_path / "user_profiles" / "ou_e35410f852dacadaced24f89d5743de1"
        user_profile.mkdir(parents=True)

        _HERMES_HOME_CTX.set(str(user_profile))

        result = display_hermes_home()

        # User ID should be replaced with generic placeholder
        assert "ou_e35410f852dacadaced24f89d5743de1" not in result
        assert "<your-profile>" in result
        assert "user_profiles" in result

        _HERMES_HOME_CTX.set(None)  # cleanup

    def test_multiple_user_ids_all_sanitized(self, tmp_path):
        """Ensure all user IDs in path are sanitized."""
        # Edge case: path contains multiple user ID patterns
        complex_path = tmp_path / "user_profiles" / "ou_abc123" / "backups" / "ou_def456"
        complex_path.mkdir(parents=True)

        _HERMES_HOME_CTX.set(str(complex_path))

        result = display_hermes_home()

        # Both user IDs should be sanitized
        assert "ou_abc123" not in result
        assert "ou_def456" not in result
        assert "<your-profile>" in result

        _HERMES_HOME_CTX.set(None)  # cleanup
