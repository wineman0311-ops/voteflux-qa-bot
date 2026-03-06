"""
News scraper using Google News RSS feeds.

Fetches current news for countries and generates prediction market suggestions
based on trending topics and events.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime
import feedparser

import requests

from config.platforms import CountryNews, NewsItem, SuggestedMarket


class NewsScraper:
    """Scraper for country-specific news from Google News RSS feeds."""

    # Google News CEID mappings for major countries
    COUNTRY_CEID_MAP = {
        "US": "US:en",
        "UK": "GB:en",
        "CA": "CA:en",
        "AU": "AU:en",
        "JP": "JP:ja",
        "DE": "DE:de",
        "FR": "FR:fr",
        "IN": "IN:en",
        "BR": "BR:pt",
        "MX": "MX:es",
        "PH": "PH:en",
        "SG": "SG:en",
        "HK": "HK:en",
        "KR": "KR:ko",
        "CN": "CN:zh",
    }

    def __init__(self, timeout: int = 10):
        """
        Initialize news scraper.

        Args:
            timeout: Request timeout in seconds
        """
        self.logger = logging.getLogger("scraper.news")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
        )

    def scrape_country(self, country_config: Dict[str, Any]) -> CountryNews:
        """
        Scrape news for a specific country.

        Args:
            country_config: Dictionary with keys: id, name, flag, name_en

        Returns:
            CountryNews with news items and market suggestions
        """
        country_news = CountryNews(
            id=country_config["id"],
            name=country_config.get("name", ""),
            flag=country_config.get("flag", ""),
            name_en=country_config.get("name_en", ""),
        )

        try:
            self.logger.info(f"Scraping news for {country_config['name']}")

            # Fetch news items
            news_items = self._fetch_country_news(country_config)
            country_news.news_items = news_items

            # Generate market suggestions based on news
            suggestions = self._generate_market_suggestions(news_items)
            country_news.suggested_markets = suggestions

            self.logger.info(
                f"Found {len(news_items)} news items and {len(suggestions)} market suggestions"
            )

        except Exception as e:
            self.logger.error(f"Error scraping news for {country_config['name']}: {e}")

        return country_news

    def scrape_all_countries(
        self, countries: List[Dict[str, Any]]
    ) -> List[CountryNews]:
        """
        Scrape news for multiple countries.

        Args:
            countries: List of country configuration dictionaries

        Returns:
            List of CountryNews objects
        """
        results = []
        for country_config in countries:
            try:
                country_news = self.scrape_country(country_config)
                results.append(country_news)
            except Exception as e:
                self.logger.error(
                    f"Error scraping {country_config.get('name', 'unknown')}: {e}"
                )

        return results

    def _fetch_country_news(self, country_config: Dict[str, Any]) -> List[NewsItem]:
        """
        Fetch news items for a country using Google News RSS.

        Args:
            country_config: Country configuration dictionary

        Returns:
            List of NewsItem objects
        """
        news_items = []

        try:
            country_id = country_config["id"]

            # Get CEID for this country
            ceid = self.COUNTRY_CEID_MAP.get(country_id, f"{country_id}:en")

            # Build Google News RSS URL
            url = f"https://news.google.com/rss?hl=en&gl={country_id}&ceid={ceid}"

            self.logger.debug(f"Fetching news from {url}")

            # Fetch RSS feed
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            # Parse RSS
            feed = feedparser.parse(response.content)

            if feed.bozo:
                self.logger.warning(f"Feed parsing error for {country_id}: {feed.bozo_exception}")

            # Extract top 3 news items
            for entry in feed.entries[:3]:
                try:
                    news_item = NewsItem(
                        title=entry.get("title", ""),
                        summary=entry.get(
                            "summary",
                            entry.get("description", "")[:200],
                        ),
                        source=entry.get("source", {}).get(
                            "title", "Google News"
                        ),
                    )

                    if news_item.title:
                        news_items.append(news_item)
                except Exception as e:
                    self.logger.debug(f"Error processing news entry: {e}")

        except requests.Timeout:
            self.logger.warning(f"Timeout fetching news for {country_id}")
        except requests.RequestException as e:
            self.logger.warning(f"Request error fetching news for {country_id}: {e}")
        except Exception as e:
            self.logger.error(f"Error fetching news for {country_config.get('name')}: {e}")

        return news_items

    def _generate_market_suggestions(
        self, news_items: List[NewsItem]
    ) -> List[SuggestedMarket]:
        """
        Generate market suggestions based on news topics.

        Args:
            news_items: List of current news items

        Returns:
            List of SuggestedMarket objects
        """
        suggestions = []

        # Define market suggestion rules
        suggestion_rules = [
            {
                "keywords": [
                    "election",
                    "election",
                    "vote",
                    "poll",
                    "campaign",
                ],
                "suggestion_template": "Will {} occur in the next {period}?",
                "suitability": "high",
            },
            {
                "keywords": [
                    "economic",
                    "inflation",
                    "gdp",
                    "recession",
                    "interest rate",
                ],
                "suggestion_template": "Will {} impact the economy?",
                "suitability": "high",
            },
            {
                "keywords": [
                    "sports",
                    "championship",
                    "tournament",
                    "match",
                    "game",
                ],
                "suggestion_template": "Will {} win the match/tournament?",
                "suitability": "medium",
            },
            {
                "keywords": [
                    "disaster",
                    "earthquake",
                    "hurricane",
                    "flood",
                    "storm",
                ],
                "suggestion_template": "Will {} occur?",
                "suitability": "medium",
            },
            {
                "keywords": [
                    "technology",
                    "ai",
                    "product launch",
                    "company",
                    "startup",
                ],
                "suggestion_template": "Will {} happen?",
                "suitability": "medium",
            },
            {
                "keywords": ["crypto", "bitcoin", "ethereum", "blockchain"],
                "suggestion_template": "Will {} reach a certain price?",
                "suitability": "high",
            },
        ]

        try:
            for news_item in news_items[:3]:
                title_lower = news_item.title.lower()
                summary_lower = news_item.summary.lower()
                content = f"{title_lower} {summary_lower}"

                for rule in suggestion_rules:
                    # Check if any keywords match
                    if any(keyword in content for keyword in rule["keywords"]):
                        # Create market suggestion
                        market_question = f"Will {news_item.title} impact markets in the next 90 days?"

                        # Make question more concise if too long
                        if len(market_question) > 100:
                            market_question = (
                                f"Will the event in '{news_item.title[:50]}...' impact markets?"
                            )

                        suggestion = SuggestedMarket(
                            question=market_question,
                            suitability=rule["suitability"],
                            reason=f"Based on current news: {news_item.source}",
                        )

                        suggestions.append(suggestion)
                        break

            # Sort by suitability
            suitability_score = {"high": 3, "medium": 2, "low": 1}
            suggestions.sort(
                key=lambda x: suitability_score.get(x.suitability, 0),
                reverse=True,
            )

            # Return top 5 suggestions
            suggestions = suggestions[:5]

        except Exception as e:
            self.logger.error(f"Error generating market suggestions: {e}")

        return suggestions
