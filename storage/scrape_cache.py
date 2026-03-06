"""
Same-day scrape cache for platform and country news data.

Caches scraped data to disk keyed by date (YYYYMMDD) so all users
share the same data without re-scraping on the same day.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from config.platforms import (
    PlatformData,
    CountryNews,
    CategoryInfo,
    MarketInfo,
    NewsItem,
    SuggestedMarket,
)

logger = logging.getLogger(__name__)


class ScrapeCache:
    """
    Manages same-day scrape result caching.

    Persists platform and country news data as JSON files named by date
    (YYYYMMDD.json) under the configured cache directory.  Multiple bot
    users share a single cache file per day, so only the first /run or
    scheduled job performs the actual scrape; subsequent calls load from
    disk instead.
    """

    def __init__(self, cache_dir: str = "./cache") -> None:
        """
        Initialize ScrapeCache.

        Args:
            cache_dir: Directory where cache files are stored.
        """
        self.cache_dir = Path(cache_dir)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def has_today_cache(self) -> bool:
        """Return True if a valid cache file exists for today."""
        return self._cache_path(self._today_key()).exists()

    def get_today_cache(
        self,
    ) -> Tuple[Optional[List[PlatformData]], Optional[List[CountryNews]]]:
        """
        Load today's cached scrape data.

        Returns:
            (platforms_data, countries_data) if cache exists, else (None, None).
        """
        cache_path = self._cache_path(self._today_key())
        if not cache_path.exists():
            return None, None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            platforms_data = [
                self._dict_to_platform(p) for p in data.get("platforms", [])
            ]
            countries_data = [
                self._dict_to_country(c) for c in data.get("countries", [])
            ]

            cached_at = data.get("cached_at", "unknown")
            logger.info(
                f"Loaded today's cache: {len(platforms_data)} platforms, "
                f"{len(countries_data)} countries (cached at {cached_at})"
            )
            return platforms_data, countries_data

        except Exception as e:
            logger.error(f"Failed to load cache from {cache_path}: {e}", exc_info=True)
            return None, None

    def save_today_cache(
        self,
        platforms_data: List[PlatformData],
        countries_data: List[CountryNews],
    ) -> bool:
        """
        Persist freshly scraped data to today's cache file.

        Args:
            platforms_data: List of scraped PlatformData objects.
            countries_data: List of scraped CountryNews objects.

        Returns:
            True if saved successfully, False otherwise.
        """
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = self._cache_path(self._today_key())

            payload = {
                "cached_at": datetime.now().isoformat(),
                "date": self._today_key(),
                "platforms": [p.to_dict() for p in platforms_data],
                "countries": [c.to_dict() for c in countries_data],
            }

            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            logger.info(
                f"Cache saved → {cache_path}  "
                f"({len(platforms_data)} platforms, {len(countries_data)} countries)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to save cache: {e}", exc_info=True)
            return False

    def get_cache_info(self) -> dict:
        """
        Return metadata about today's cache.

        Returns:
            Dict with keys: has_cache, cached_at, platform_count, country_count.
        """
        cache_path = self._cache_path(self._today_key())
        if not cache_path.exists():
            return {"has_cache": False}

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "has_cache": True,
                "cached_at": data.get("cached_at", "unknown"),
                "platform_count": len(data.get("platforms", [])),
                "country_count": len(data.get("countries", [])),
            }
        except Exception:
            return {"has_cache": False}

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _today_key(self) -> str:
        """Return today's date as YYYYMMDD string."""
        return datetime.now().strftime("%Y%m%d")

    def _cache_path(self, date_key: str) -> Path:
        """Return full path to cache file for the given date key."""
        return self.cache_dir / f"{date_key}.json"

    def _dict_to_platform(self, d: dict) -> PlatformData:
        """Reconstruct PlatformData from a plain dict."""
        scraped_at_str = d.get("scraped_at")
        scraped_at = datetime.fromisoformat(scraped_at_str) if scraped_at_str else None

        return PlatformData(
            id=d["id"],
            name=d["name"],
            url=d["url"],
            role=d["role"],
            status=d["status"],
            market_count=d.get("market_count", 0),
            category_count=d.get("category_count", 0),
            categories=[
                CategoryInfo(name=c["name"], count=c["count"])
                for c in d.get("categories", [])
            ],
            top_markets=[
                MarketInfo(
                    question=m["question"],
                    volume=m.get("volume"),
                    participants=m.get("participants"),
                )
                for m in d.get("top_markets", [])
            ],
            features=d.get("features", []),
            live_market_count=d.get("live_market_count", 0),
            trading_volume_info=d.get("trading_volume_info"),
            ui_notes=d.get("ui_notes"),
            ux_notes=d.get("ux_notes"),
            error_msg=d.get("error_msg"),
            scraped_at=scraped_at,
        )

    def _dict_to_country(self, d: dict) -> CountryNews:
        """Reconstruct CountryNews from a plain dict."""
        return CountryNews(
            id=d["id"],
            name=d["name"],
            flag=d["flag"],
            name_en=d["name_en"],
            news_items=[
                NewsItem(
                    title=n["title"],
                    summary=n["summary"],
                    source=n["source"],
                )
                for n in d.get("news_items", [])
            ],
            suggested_markets=[
                SuggestedMarket(
                    question=m["question"],
                    suitability=m["suitability"],
                    reason=m["reason"],
                )
                for m in d.get("suggested_markets", [])
            ],
        )
