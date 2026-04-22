"""Tests for WeChat multi-bot coordinator and per-bot isolation."""

import asyncio
import json
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from gateway.config import PlatformConfig, Platform


@pytest.fixture
def tmp_hermes_home(tmp_path):
    """Create a temporary HERMES_HOME with user_profiles structure."""
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    return hermes_home


def _create_bot_profile(hermes_home: Path, account_id: str, token: str = "test_token"):
    """Helper to create a bot profile with credentials."""
    profile_dir = hermes_home / "user_profiles" / f"wx_{account_id}"
    accounts_dir = profile_dir / "weixin" / "accounts"
    accounts_dir.mkdir(parents=True, exist_ok=True)

    for subdir in ("memories", "skills", "sessions", "logs"):
        (profile_dir / subdir).mkdir(parents=True, exist_ok=True)

    creds = {
        "account_id": account_id,
        "token": token,
        "base_url": "https://ilinkai.weixin.qq.com",
        "user_id": f"user_{account_id}",
    }
    (accounts_dir / f"{account_id}.json").write_text(json.dumps(creds))
    return profile_dir


class TestWeixinMultiBotCoordinator:
    """Tests for WeixinMultiBotCoordinator."""

    def test_coordinator_init(self, tmp_hermes_home):
        from gateway.platforms.weixin_multi_user import WeixinMultiBotCoordinator

        gateway_mock = MagicMock()
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_hermes_home)}):
            coordinator = WeixinMultiBotCoordinator(gateway_mock)
        assert coordinator.get_bot_count() == 0

    def test_load_no_profiles(self, tmp_hermes_home):
        from gateway.platforms.weixin_multi_user import WeixinMultiBotCoordinator

        gateway_mock = MagicMock()
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_hermes_home)}):
            coordinator = WeixinMultiBotCoordinator(gateway_mock)
            loaded = asyncio.get_event_loop().run_until_complete(
                coordinator.load_existing_bots()
            )
        assert loaded == 0

    def test_load_skips_non_wx_profiles(self, tmp_hermes_home):
        from gateway.platforms.weixin_multi_user import WeixinMultiBotCoordinator

        (tmp_hermes_home / "user_profiles" / "ou_abc123").mkdir(parents=True)

        gateway_mock = MagicMock()
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_hermes_home)}):
            coordinator = WeixinMultiBotCoordinator(gateway_mock)
            loaded = asyncio.get_event_loop().run_until_complete(
                coordinator.load_existing_bots()
            )
        assert loaded == 0

    def test_load_existing_bot(self, tmp_hermes_home):
        from gateway.platforms.weixin_multi_user import WeixinMultiBotCoordinator

        _create_bot_profile(tmp_hermes_home, "bot1", "token1")

        gateway_mock = MagicMock()
        gateway_mock._adapters = {}

        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_hermes_home)}), \
             patch("gateway.platforms.weixin_multi_user.WeixinAdapter") as MockAdapter:
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock(return_value=True)
            MockAdapter.return_value = mock_instance

            coordinator = WeixinMultiBotCoordinator(gateway_mock)
            loaded = asyncio.get_event_loop().run_until_complete(
                coordinator.load_existing_bots()
            )

        assert loaded == 1
        assert coordinator.get_bot_count() == 1

    def test_load_multiple_bots(self, tmp_hermes_home):
        from gateway.platforms.weixin_multi_user import WeixinMultiBotCoordinator

        _create_bot_profile(tmp_hermes_home, "bot1", "token1")
        _create_bot_profile(tmp_hermes_home, "bot2", "token2")

        gateway_mock = MagicMock()
        gateway_mock._adapters = {}

        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_hermes_home)}), \
             patch("gateway.platforms.weixin_multi_user.WeixinAdapter") as MockAdapter:
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock(return_value=True)
            MockAdapter.return_value = mock_instance

            coordinator = WeixinMultiBotCoordinator(gateway_mock)
            loaded = asyncio.get_event_loop().run_until_complete(
                coordinator.load_existing_bots()
            )

        assert loaded == 2
        assert coordinator.get_bot_count() == 2

    def test_disconnect_all(self, tmp_hermes_home):
        from gateway.platforms.weixin_multi_user import WeixinMultiBotCoordinator

        _create_bot_profile(tmp_hermes_home, "bot1", "token1")

        gateway_mock = MagicMock()
        gateway_mock._adapters = {}

        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_hermes_home)}), \
             patch("gateway.platforms.weixin_multi_user.WeixinAdapter") as MockAdapter:
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock(return_value=True)
            mock_instance.disconnect = AsyncMock()
            MockAdapter.return_value = mock_instance

            coordinator = WeixinMultiBotCoordinator(gateway_mock)
            loop = asyncio.get_event_loop()
            loop.run_until_complete(coordinator.load_existing_bots())
            assert coordinator.get_bot_count() == 1

            loop.run_until_complete(coordinator.disconnect_all())
            assert coordinator.get_bot_count() == 0
            mock_instance.disconnect.assert_called_once()

    def test_failed_connect_not_counted(self, tmp_hermes_home):
        from gateway.platforms.weixin_multi_user import WeixinMultiBotCoordinator

        _create_bot_profile(tmp_hermes_home, "bot_fail", "bad_token")

        gateway_mock = MagicMock()
        gateway_mock._adapters = {}

        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_hermes_home)}), \
             patch("gateway.platforms.weixin_multi_user.WeixinAdapter") as MockAdapter:
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock(return_value=False)
            MockAdapter.return_value = mock_instance

            coordinator = WeixinMultiBotCoordinator(gateway_mock)
            loaded = asyncio.get_event_loop().run_until_complete(
                coordinator.load_existing_bots()
            )

        assert loaded == 0
        assert coordinator.get_bot_count() == 0


class TestPerBotIsolation:
    """Tests for per-bot data isolation."""

    def test_wx_profile_directory_structure(self, tmp_hermes_home):
        profile_dir = _create_bot_profile(tmp_hermes_home, "test_bot")
        assert (profile_dir / "memories").is_dir()
        assert (profile_dir / "skills").is_dir()
        assert (profile_dir / "sessions").is_dir()
        assert (profile_dir / "logs").is_dir()
        assert (profile_dir / "weixin" / "accounts" / "test_bot.json").is_file()

    def test_wx_credentials_stored_correctly(self, tmp_hermes_home):
        _create_bot_profile(tmp_hermes_home, "test_bot", "my_token")
        creds_path = tmp_hermes_home / "user_profiles" / "wx_test_bot" / "weixin" / "accounts" / "test_bot.json"
        creds = json.loads(creds_path.read_text())
        assert creds["account_id"] == "test_bot"
        assert creds["token"] == "my_token"
        assert creds["base_url"] == "https://ilinkai.weixin.qq.com"


class TestPathSanitization:
    """Tests for wx_ path sanitization in hermes_constants."""

    def test_wx_user_id_sanitized(self):
        import re
        path = "/home/user/.hermes/user_profiles/wx_abc123/memories/MEMORY.md"
        sanitized = re.sub(r'\b(ou|wx)_[a-zA-Z0-9]+\b', '<your-profile>', path)
        assert "wx_abc123" not in sanitized
        assert "<your-profile>" in sanitized

    def test_ou_user_id_still_sanitized(self):
        import re
        path = "/home/user/.hermes/user_profiles/ou_xyz789/skills/"
        sanitized = re.sub(r'\b(ou|wx)_[a-zA-Z0-9]+\b', '<your-profile>', path)
        assert "ou_xyz789" not in sanitized
        assert "<your-profile>" in sanitized

    def test_non_user_paths_not_sanitized(self):
        import re
        path = "/home/user/.hermes/config.yaml"
        sanitized = re.sub(r'\b(ou|wx)_[a-zA-Z0-9]+\b', '<your-profile>', path)
        assert sanitized == path
