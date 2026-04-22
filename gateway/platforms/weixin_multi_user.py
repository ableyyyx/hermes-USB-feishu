"""Multi-bot coordinator for WeChat/Weixin platform."""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional
import os

from gateway.config import PlatformConfig, Platform
from gateway.platforms.weixin import WeixinAdapter, load_weixin_account

logger = logging.getLogger(__name__)


class WeixinMultiBotCoordinator:
    """Manages multiple WeixinAdapter instances (one per bot account)."""

    def __init__(self, gateway_runner):
        self._gateway = gateway_runner
        self._adapters: Dict[str, WeixinAdapter] = {}  # account_id -> adapter
        self._base_home = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))

    async def load_existing_bots(self) -> int:
        """Load and connect adapters for all previously authorized bot accounts.

        Returns:
            Number of bots loaded
        """
        user_profiles_dir = self._base_home / "user_profiles"
        if not user_profiles_dir.exists():
            return 0

        loaded_count = 0
        for user_dir in user_profiles_dir.iterdir():
            if not user_dir.is_dir() or not user_dir.name.startswith("wx_"):
                continue

            weixin_accounts_dir = user_dir / "weixin" / "accounts"
            if not weixin_accounts_dir.exists():
                continue

            # Load all accounts in this profile (usually just one)
            for account_file in weixin_accounts_dir.glob("*.json"):
                account_id = account_file.stem
                credentials = load_weixin_account(str(user_dir), account_id)

                if credentials and credentials.get("token"):
                    try:
                        success = await self._create_adapter_for_bot(
                            account_id=account_id,
                            credentials=credentials,
                            profile_dir=user_dir,
                        )
                        if success:
                            loaded_count += 1
                            logger.info(f"Loaded WeChat bot: {account_id}")
                    except Exception as exc:
                        logger.error(f"Failed to load WeChat bot {account_id}: {exc}")

        return loaded_count

    async def _create_adapter_for_bot(
        self,
        account_id: str,
        credentials: Dict[str, str],
        profile_dir: Path,
    ) -> bool:
        """Create and start a WeixinAdapter for a specific bot account.

        Returns True if the adapter connected successfully.
        """

        config = PlatformConfig(
            enabled=True,
            token=credentials["token"],
            extra={
                "account_id": account_id,
                "base_url": credentials.get("base_url", "https://ilinkai.weixin.qq.com"),
                "dm_policy": "open",
                "group_policy": "disabled",
            }
        )

        adapter = WeixinAdapter(
            config=config,
            hermes_home=str(profile_dir),
        )

        success = await adapter.connect()
        if success:
            self._adapters[account_id] = adapter
            if hasattr(self._gateway, '_adapters'):
                self._gateway._adapters[Platform.WEIXIN] = adapter
            return True
        else:
            logger.error(f"Failed to connect WeChat bot {account_id}")
            return False

    async def disconnect_all(self) -> None:
        """Disconnect all bot adapters."""
        for account_id, adapter in list(self._adapters.items()):
            try:
                await adapter.disconnect()
            except Exception as exc:
                logger.error(f"Error disconnecting bot {account_id}: {exc}")
        self._adapters.clear()

    def get_bot_count(self) -> int:
        """Return number of active bots."""
        return len(self._adapters)
