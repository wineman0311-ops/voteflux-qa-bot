"""
Dynamic platform management store.

Supports adding/removing platforms at runtime via TG commands.
Platforms are persisted in a JSON file and can be initialized from
the PLATFORMS_JSON environment variable.
"""

import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Default platforms (used if no JSON file and no env var)
DEFAULT_PLATFORMS: List[Dict[str, str]] = [
    {
        "id": "voteflux",
        "name": "VoteFlux",
        "url": "https://voteflux.com",
        "role": "主體平台",
    },
    {
        "id": "kalshi",
        "name": "Kalshi",
        "url": "https://kalshi.com",
        "role": "美國合規競品（CFTC 監管）",
    },
    {
        "id": "polymarket",
        "name": "Polymarket",
        "url": "https://polymarket.com",
        "role": "全球最大區塊鏈預測市場",
    },
    {
        "id": "manifold",
        "name": "Manifold Markets",
        "url": "https://manifold.markets",
        "role": "社群驅動型競品",
    },
    {
        "id": "mirumarket",
        "name": "Mirumarket",
        "url": "https://mirumarket.com",
        "role": "東南亞本地化競品",
    },
    {
        "id": "glint",
        "name": "Glint",
        "url": "https://glint.trade",
        "role": "新興競品",
    },
    {
        "id": "yesno",
        "name": "YesNo Markets",
        "url": "https://app.yesnomarkets.com",
        "role": "新興競品",
    },
]


class PlatformStore:
    """
    Manages the list of platforms for competitive analysis.

    Platforms are persisted in a JSON file. On first init, platforms
    are loaded from PLATFORMS_JSON env var (if set), or fall back
    to DEFAULT_PLATFORMS.

    Usage:
        store = PlatformStore()
        platforms = store.get_platforms()
        store.add_platform("newplatform", "New Platform", "https://new.com", "新興競品")
        store.remove_platform("newplatform")
    """

    def __init__(self, storage_path: str = "./platforms.json"):
        self.storage_path = Path(storage_path)
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Initialize platform store from env var, file, or defaults."""
        if self.storage_path.exists():
            logger.info(f"Loading platforms from {self.storage_path}")
            return

        # Try loading from PLATFORMS_JSON env var
        env_json = os.environ.get("PLATFORMS_JSON", "")
        if env_json:
            try:
                platforms = json.loads(env_json)
                if isinstance(platforms, list) and len(platforms) > 0:
                    self._save(platforms)
                    logger.info(f"Initialized {len(platforms)} platforms from PLATFORMS_JSON env var")
                    return
            except json.JSONDecodeError:
                logger.warning("PLATFORMS_JSON env var contains invalid JSON, using defaults")

        # Fall back to defaults
        self._save(DEFAULT_PLATFORMS)
        logger.info(f"Initialized {len(DEFAULT_PLATFORMS)} default platforms")

    def _save(self, platforms: List[Dict[str, str]]) -> None:
        """Save platforms to JSON file."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "platforms": platforms,
                    "updated_at": datetime.now().isoformat(),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def _load(self) -> List[Dict[str, str]]:
        """Load platforms from JSON file."""
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("platforms", DEFAULT_PLATFORMS)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Failed to load platforms: {e}")
            return DEFAULT_PLATFORMS.copy()

    def get_platforms(self) -> List[Dict[str, str]]:
        """
        Get current list of platforms.

        Returns:
            List of platform dicts with id, name, url, role
        """
        return self._load()

    def get_platform(self, platform_id: str) -> Optional[Dict[str, str]]:
        """
        Get a specific platform by ID.

        Args:
            platform_id: Platform identifier

        Returns:
            Platform dict or None if not found
        """
        platforms = self._load()
        return next((p for p in platforms if p["id"] == platform_id), None)

    def add_platform(
        self, platform_id: str, name: str, url: str, role: str = "競品"
    ) -> tuple:
        """
        Add a new platform.

        Args:
            platform_id: Unique identifier (lowercase, no spaces)
            name: Display name
            url: Platform URL
            role: Platform role description

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Validate inputs
        if not platform_id or not name or not url:
            return False, "平台 ID、名稱、網址不可為空"

        # Sanitize ID
        platform_id = platform_id.lower().strip().replace(" ", "_")

        # Check URL format
        if not url.startswith("http"):
            url = f"https://{url}"

        platforms = self._load()

        # Check for duplicate
        if any(p["id"] == platform_id for p in platforms):
            return False, f"平台 ID '{platform_id}' 已存在"

        if any(p["url"] == url for p in platforms):
            existing = next(p for p in platforms if p["url"] == url)
            return False, f"網址已被 '{existing['name']}' 使用"

        # Add platform
        new_platform = {
            "id": platform_id,
            "name": name,
            "url": url,
            "role": role,
        }
        platforms.append(new_platform)
        self._save(platforms)

        logger.info(f"Added platform: {name} ({platform_id}) - {url}")
        return True, f"已新增平台: {name}"

    def remove_platform(self, platform_id: str) -> tuple:
        """
        Remove a platform by ID.

        Args:
            platform_id: Platform identifier to remove

        Returns:
            Tuple of (success: bool, message: str)
        """
        platform_id = platform_id.lower().strip()
        platforms = self._load()

        # Find platform
        platform = next((p for p in platforms if p["id"] == platform_id), None)
        if not platform:
            return False, f"找不到平台 ID: '{platform_id}'"

        # Prevent removing VoteFlux (our own platform)
        if platform_id == "voteflux":
            return False, "無法移除 VoteFlux（主體平台）"

        # Remove
        platforms = [p for p in platforms if p["id"] != platform_id]
        self._save(platforms)

        logger.info(f"Removed platform: {platform['name']} ({platform_id})")
        return True, f"已移除平台: {platform['name']}"

    def update_platform(
        self,
        platform_id: str,
        name: Optional[str] = None,
        url: Optional[str] = None,
        role: Optional[str] = None,
    ) -> tuple:
        """
        Update an existing platform's details.

        Args:
            platform_id: Platform ID to update
            name: New name (optional)
            url: New URL (optional)
            role: New role (optional)

        Returns:
            Tuple of (success: bool, message: str)
        """
        platform_id = platform_id.lower().strip()
        platforms = self._load()

        idx = next((i for i, p in enumerate(platforms) if p["id"] == platform_id), None)
        if idx is None:
            return False, f"找不到平台 ID: '{platform_id}'"

        if name:
            platforms[idx]["name"] = name
        if url:
            if not url.startswith("http"):
                url = f"https://{url}"
            platforms[idx]["url"] = url
        if role:
            platforms[idx]["role"] = role

        self._save(platforms)
        logger.info(f"Updated platform: {platform_id}")
        return True, f"已更新平台: {platforms[idx]['name']}"

    def count(self) -> int:
        """Return number of platforms."""
        return len(self._load())
