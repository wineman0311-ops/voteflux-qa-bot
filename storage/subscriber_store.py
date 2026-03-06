"""
Subscriber Store - manages Telegram subscriber list with JSON persistence.
Users can subscribe/unsubscribe via TG commands.
"""
import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SubscriberStore:
    """Manages the list of subscribed Telegram chat IDs."""

    def __init__(self, storage_path: str = "./subscribers.json"):
        self.storage_path = storage_path
        self._data: Dict[str, dict] = {}
        self._load()

    def _load(self):
        """Load subscribers from JSON file."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info(f"Loaded {len(self._data)} subscribers from {self.storage_path}")
            except Exception as e:
                logger.error(f"Failed to load subscribers: {e}")
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        """Persist subscribers to JSON file."""
        try:
            os.makedirs(os.path.dirname(self.storage_path) or ".", exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save subscribers: {e}")

    def subscribe(self, chat_id: int, username: str = "", first_name: str = "") -> tuple[bool, str]:
        """
        Subscribe a chat_id.
        Returns (success, message).
        """
        key = str(chat_id)
        if key in self._data:
            return False, "你已經訂閱了！使用 /mystatus 查看訂閱狀態。"

        self._data[key] = {
            "chat_id": chat_id,
            "username": username,
            "first_name": first_name,
            "subscribed_at": datetime.now().isoformat(),
        }
        self._save()
        return True, f"✅ 訂閱成功！你將會收到 VoteFlux QA 競品分析報告。\n使用 /unsubscribe 可取消訂閱。"

    def unsubscribe(self, chat_id: int) -> tuple[bool, str]:
        """
        Unsubscribe a chat_id.
        Returns (success, message).
        """
        key = str(chat_id)
        if key not in self._data:
            return False, "你尚未訂閱。使用 /subscribe 開始訂閱。"

        del self._data[key]
        self._save()
        return True, "✅ 已取消訂閱。如需重新訂閱請使用 /subscribe。"

    def is_subscribed(self, chat_id: int) -> bool:
        """Check if a chat_id is subscribed."""
        return str(chat_id) in self._data

    def get_subscriber(self, chat_id: int) -> Optional[dict]:
        """Get subscriber info."""
        return self._data.get(str(chat_id))

    def get_all_chat_ids(self) -> List[int]:
        """Get all subscribed chat IDs."""
        return [v["chat_id"] for v in self._data.values()]

    def count(self) -> int:
        """Return total subscriber count."""
        return len(self._data)

    def list_subscribers(self) -> List[dict]:
        """Return all subscriber info."""
        return list(self._data.values())
