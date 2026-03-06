"""
Data models for platform analysis and country news.

Defines dataclasses for storing structured data about prediction markets,
country-specific news, and analysis results.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional


@dataclass
class CategoryInfo:
    """Information about a market category."""

    name: str
    count: int


@dataclass
class MarketInfo:
    """Information about a top market."""

    question: str
    volume: Optional[str] = None
    participants: Optional[int] = None


@dataclass
class PlatformData:
    """Comprehensive data about a prediction market platform."""

    id: str
    name: str
    url: str
    role: str
    status: str  # "success", "error", or "skipped"
    market_count: int = 0
    category_count: int = 0
    categories: List[CategoryInfo] = field(default_factory=list)
    top_markets: List[MarketInfo] = field(default_factory=list)
    features: List[str] = field(default_factory=list)
    live_market_count: int = 0
    trading_volume_info: Optional[str] = None
    ui_notes: Optional[str] = None
    ux_notes: Optional[str] = None
    error_msg: Optional[str] = None
    scraped_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert PlatformData to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "role": self.role,
            "status": self.status,
            "market_count": self.market_count,
            "category_count": self.category_count,
            "categories": [
                {"name": c.name, "count": c.count} for c in self.categories
            ],
            "top_markets": [
                {
                    "question": m.question,
                    "volume": m.volume,
                    "participants": m.participants,
                }
                for m in self.top_markets
            ],
            "features": self.features,
            "live_market_count": self.live_market_count,
            "trading_volume_info": self.trading_volume_info,
            "ui_notes": self.ui_notes,
            "ux_notes": self.ux_notes,
            "error_msg": self.error_msg,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }


@dataclass
class NewsItem:
    """A news item related to a country."""

    title: str
    summary: str
    source: str


@dataclass
class SuggestedMarket:
    """A market suggestion based on country news."""

    question: str
    suitability: str  # e.g., "high", "medium", "low"
    reason: str


@dataclass
class CountryNews:
    """News and market suggestions for a specific country."""

    id: str
    name: str
    flag: str
    name_en: str
    news_items: List[NewsItem] = field(default_factory=list)
    suggested_markets: List[SuggestedMarket] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert CountryNews to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "flag": self.flag,
            "name_en": self.name_en,
            "news_items": [
                {"title": item.title, "summary": item.summary, "source": item.source}
                for item in self.news_items
            ],
            "suggested_markets": [
                {
                    "question": market.question,
                    "suitability": market.suitability,
                    "reason": market.reason,
                }
                for market in self.suggested_markets
            ],
        }


@dataclass
class AnalysisResult:
    """Complete analysis result for a QA run."""

    version: str
    date: datetime
    platforms: List[PlatformData] = field(default_factory=list)
    countries: List[CountryNews] = field(default_factory=list)
    scores: Dict[str, Any] = field(default_factory=dict)
    alerts: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert AnalysisResult to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "date": self.date.isoformat(),
            "platforms": [p.to_dict() for p in self.platforms],
            "countries": [c.to_dict() for c in self.countries],
            "scores": self.scores,
            "alerts": self.alerts,
            "recommendations": self.recommendations,
        }
