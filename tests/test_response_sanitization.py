"""Tests for response sanitization to prevent path disclosure.

Regression test for feat-010: ensures agent responses do not leak
user IDs, directory structures, or specific file paths.
"""

import os
import pytest
from pathlib import Path


class TestResponseSanitization:
    """Test that paths are completely hidden in agent responses."""

    def test_hide_user_id(self):
        """User IDs should be hidden."""
        from gateway.run import _sanitize_response_content

        response = "Your profile is ou_abc123"
        sanitized = _sanitize_response_content(response)
        assert "ou_abc123" not in sanitized
        assert "<user-profile>" in sanitized

    def test_hide_skills_path_with_user_id(self):
        """Skills paths with user IDs should be hidden."""
        from gateway.run import _sanitize_response_content

        response = "Your skills are at ~/.hermes/user_profiles/ou_abc123/skills/"
        sanitized = _sanitize_response_content(response)
        assert "ou_abc123" not in sanitized
        assert "user_profiles" not in sanitized
        assert "your skills directory" in sanitized

    def test_hide_absolute_path(self):
        """Absolute paths should be hidden."""
        from gateway.run import _sanitize_response_content

        response = "Check /home/user/.hermes/user_profiles/ou_abc123/skills/"
        sanitized = _sanitize_response_content(response)
        assert "/home/user" not in sanitized
        assert "ou_abc123" not in sanitized
        assert "your skills directory" in sanitized

    def test_hide_multiple_paths(self):
        """Multiple paths in same response should all be hidden."""
        from gateway.run import _sanitize_response_content

        response = (
            "Your skills are at ~/.hermes/user_profiles/ou_abc123/skills/ "
            "and memories at ~/.hermes/user_profiles/ou_abc123/memories/"
        )
        sanitized = _sanitize_response_content(response)
        assert "ou_abc123" not in sanitized
        assert "your skills directory" in sanitized
        assert "your memories directory" in sanitized

    def test_hide_generic_hermes_paths(self):
        """Generic ~/.hermes paths should be hidden."""
        from gateway.run import _sanitize_response_content

        response = "Check ~/.hermes/skills/ and ~/.hermes/memories/"
        sanitized = _sanitize_response_content(response)
        assert "your skills directory" in sanitized
        assert "your memories directory" in sanitized

    def test_multiple_user_ids_all_hidden(self):
        """Multiple user IDs should all be hidden."""
        from gateway.run import _sanitize_response_content

        response = "User ou_abc123 and ou_def456 both have skills"
        sanitized = _sanitize_response_content(response)
        assert "ou_abc123" not in sanitized
        assert "ou_def456" not in sanitized
        assert "<user-profile>" in sanitized


class TestDisplayFunctions:
    """Test display_skills_dir() and display_memory_dir() functions."""

    def test_cli_mode_shows_paths(self):
        """CLI mode should show actual paths."""
        from hermes_constants import _HERMES_HOME_CTX, display_skills_dir

        _HERMES_HOME_CTX.set(None)

        result = display_skills_dir()
        # Should show actual path, not generic description
        assert "your skills directory" not in result
        assert "skills" in result

    def test_gateway_mode_hides_paths(self):
        """Gateway mode should hide paths."""
        from hermes_constants import _HERMES_HOME_CTX, set_hermes_home_ctx, display_skills_dir

        set_hermes_home_ctx("/tmp/user_profiles/ou_test123")

        result = display_skills_dir()
        assert result == "your skills directory"
        assert "ou_test123" not in result
        assert "/tmp" not in result

        _HERMES_HOME_CTX.set(None)  # cleanup

    def test_display_memory_dir_gateway_mode(self):
        """display_memory_dir() should hide paths in gateway mode."""
        from hermes_constants import _HERMES_HOME_CTX, set_hermes_home_ctx, display_memory_dir

        set_hermes_home_ctx("/tmp/user_profiles/ou_test123")

        result = display_memory_dir()
        assert result == "your memories directory"
        assert "ou_test123" not in result

        _HERMES_HOME_CTX.set(None)  # cleanup

    def test_display_memory_dir_cli_mode(self):
        """display_memory_dir() should show paths in CLI mode."""
        from hermes_constants import _HERMES_HOME_CTX, display_memory_dir

        _HERMES_HOME_CTX.set(None)

        result = display_memory_dir()
        assert "your memories directory" not in result
        assert "memories" in result

    def test_gateway_mode_detection_with_contextvar(self):
        """_is_gateway_mode() should detect ContextVar."""
        from hermes_constants import _HERMES_HOME_CTX, set_hermes_home_ctx, _is_gateway_mode

        _HERMES_HOME_CTX.set(None)
        assert _is_gateway_mode() is False

        set_hermes_home_ctx("/tmp/user_profiles/ou_test123")
        assert _is_gateway_mode() is True

        _HERMES_HOME_CTX.set(None)  # cleanup

    def test_gateway_mode_detection_with_env_var(self):
        """_is_gateway_mode() should detect HERMES_GATEWAY_SESSION env var."""
        from hermes_constants import _HERMES_HOME_CTX, _is_gateway_mode

        _HERMES_HOME_CTX.set(None)
        os.environ.pop("HERMES_GATEWAY_SESSION", None)
        assert _is_gateway_mode() is False

        os.environ["HERMES_GATEWAY_SESSION"] = "1"
        assert _is_gateway_mode() is True

        os.environ.pop("HERMES_GATEWAY_SESSION")  # cleanup


class TestRealWorldScenarios:
    """Test real-world scenarios from the original vulnerability."""

    def test_original_vulnerability_scenario(self):
        """Test the original vulnerability: '你的技能检索的路径'"""
        from gateway.run import _sanitize_response_content

        # Original problematic response
        response = (
            "我的技能检索路径是：\n"
            "~/.hermes/user_profiles/ou_2ff2be6c69f565f4f9a6c51730c053cf/skills/\n"
            "常见结构：\n"
            "SKILL.md：技能主文件\n"
            "references/：参考资料"
        )

        sanitized = _sanitize_response_content(response)

        # Should not contain user ID
        assert "ou_2ff2be6c69f565f4f9a6c51730c053cf" not in sanitized
        # Should not contain specific path structure
        assert "user_profiles" not in sanitized
        # Should contain generic description
        assert "your skills directory" in sanitized

    def test_error_message_with_path(self):
        """Error messages should not leak paths."""
        from gateway.run import _sanitize_response_content

        response = "Error: Cannot access /home/user/.hermes/user_profiles/ou_abc123/skills/test.py"
        sanitized = _sanitize_response_content(response)

        assert "ou_abc123" not in sanitized
        assert "/home/user" not in sanitized
        assert "your skills directory" in sanitized

    def test_mixed_content_with_paths(self):
        """Mixed content with paths should be sanitized."""
        from gateway.run import _sanitize_response_content

        response = (
            "你可以在 ~/.hermes/user_profiles/ou_abc123/skills/ 找到技能，"
            "记忆存储在 ~/.hermes/user_profiles/ou_abc123/memories/ 中。"
            "用户ID是 ou_abc123。"
        )

        sanitized = _sanitize_response_content(response)

        assert "ou_abc123" not in sanitized
        assert "your skills directory" in sanitized
        assert "your memories directory" in sanitized
        assert "<user-profile>" in sanitized
