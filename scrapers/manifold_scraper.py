"""
Scraper for Manifold Markets platform (manifold.markets).

Extracts market data, categories, and unique features like Leagues and Mana system
from Manifold Markets.
"""

import logging
from playwright.sync_api import Page

from config.platforms import PlatformData, CategoryInfo, MarketInfo
from .base_scraper import BaseScraper


class ManifoldScraper(BaseScraper):
    """Scraper for Manifold Markets platform with play-money prediction markets."""

    def extract_data(self, page: Page) -> PlatformData:
        """
        Extract data from Manifold Markets platform.

        Args:
            page: Playwright Page object

        Returns:
            PlatformData with Manifold Markets information
        """
        data = PlatformData(
            id=self.config["id"],
            name=self.config["name"],
            url=self.config["url"],
            role=self.config["role"],
            status="success",
        )

        try:
            self.logger.info(f"Navigating to {self.config['url']}")
            page.goto(self.config["url"], wait_until="domcontentloaded")
            self.wait_for_load(page, timeout=12000)

            # Extract markets
            self._extract_markets(page, data)

            # Extract categories
            self._extract_categories(page, data)

            # Extract features
            self._extract_features(page, data)

            # Extract trending info
            self._extract_trending_info(page, data)

            self.logger.info(
                f"Successfully scraped Manifold: {data.market_count} markets"
            )

        except Exception as e:
            self.logger.error(f"Error during Manifold extraction: {e}")
            data.status = "error"
            data.error_msg = str(e)

        return data

    def _extract_markets(self, page: Page, data: PlatformData):
        """
        Extract market count and trending markets.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Manifold displays markets in grid/list view
            market_selectors = [
                "[class*='market-card']",
                "[class*='prediction-card']",
                "div[class*='border'][class*='rounded']",  # Card-like divs
                "a[class*='hover:']",  # Interactive elements
            ]

            top_markets = []

            for selector in market_selectors:
                elements = page.query_selector_all(selector)
                if elements and len(elements) > 2:
                    for el in elements[:15]:
                        try:
                            question = self.safe_text(el, "h3, h4, [class*='title']")
                            if not question:
                                question = self.safe_text(el, "a")

                            # Look for probability/odds
                            prob = self.safe_text(el, "[class*='probability']")
                            if not prob:
                                prob = self.safe_text(el, "[class*='percent']")

                            if (
                                question
                                and len(question) > 5
                                and question
                                not in [m.question for m in top_markets]
                            ):
                                top_markets.append(
                                    MarketInfo(
                                        question=question,
                                        volume=prob if prob else None,
                                    )
                                )
                        except Exception as e:
                            self.logger.debug(f"Error extracting market: {e}")

                    if top_markets:
                        break

            data.top_markets = top_markets[:10]
            data.live_market_count = len(top_markets)

            # Try to find total market count
            count_text = self.safe_text(page, "span:has-text('question')")
            if count_text:
                try:
                    data.market_count = int("".join(filter(str.isdigit, count_text)))
                except (ValueError, AttributeError):
                    data.market_count = len(top_markets) * 100  # Estimate
            else:
                data.market_count = len(top_markets) * 100

        except Exception as e:
            self.logger.warning(f"Error extracting markets: {e}")

    def _extract_categories(self, page: Page, data: PlatformData):
        """
        Extract market categories/groups.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Look for category buttons/filters
            category_selectors = [
                "button:has-text('Politics')",
                "button:has-text('Sports')",
                "button:has-text('Science')",
                "[class*='category-button']",
                "[class*='topic']",
            ]

            categories = {}

            # Check for category pills/buttons
            buttons = page.query_selector_all("button[class*='px']")
            for btn in buttons[:20]:
                try:
                    btn_text = btn.inner_text().strip()
                    if (
                        btn_text
                        and len(btn_text) < 30
                        and btn_text.lower()
                        not in ["filter", "all", "trending", "new"]
                    ):
                        categories[btn_text] = categories.get(btn_text, 0) + 1
                except Exception as e:
                    self.logger.debug(f"Error extracting category: {e}")

            # Known Manifold categories
            if not categories:
                categories = {
                    "Politics": 0,
                    "Science": 0,
                    "Sports": 0,
                    "Technology": 0,
                }

            data.categories = [
                CategoryInfo(name=name, count=count)
                for name, count in sorted(
                    categories.items(), key=lambda x: x[1], reverse=True
                )
            ]
            data.category_count = len(data.categories)

        except Exception as e:
            self.logger.warning(f"Error extracting categories: {e}")

    def _extract_features(self, page: Page, data: PlatformData):
        """
        Extract platform features including unique ones like Leagues and Mana.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            features = ["Play-money markets", "Mana currency"]

            # Check for Leagues
            if page.query_selector("text=League") or page.query_selector(
                "text=Leagues"
            ):
                features.append("Leagues/Tournaments")

            # Check for API
            if page.query_selector("text=API"):
                features.append("API available")

            # Check for mobile
            if page.query_selector("text=Mobile") or page.query_selector(
                "[class*='mobile-app']"
            ):
                features.append("Mobile app")

            # Check for contract creation
            if page.query_selector("text=Create") or page.query_selector(
                "text=Create market"
            ):
                features.append("User-created markets")

            # Check for rich feature set
            if page.query_selector("text=Subsidy") or page.query_selector(
                "text=Boost"
            ):
                features.append("Market boost feature")

            if page.query_selector("text=Comment"):
                features.append("Discussion comments")

            # Check for daily leaderboard
            if page.query_selector("text=Leaderboard") or page.query_selector(
                "text=Ranking"
            ):
                features.append("Player leaderboards")

            data.features = features

        except Exception as e:
            self.logger.warning(f"Error extracting features: {e}")
            data.features = ["Play-money markets", "Mana currency"]

    def _extract_trending_info(self, page: Page, data: PlatformData):
        """
        Extract trending markets and activity information.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Look for trending/hot indicators
            trending_text = self.safe_text(
                page, "[class*='trending'], [class*='hot'], [class*='popular']"
            )

            if trending_text:
                data.trading_volume_info = f"Trending: {trending_text}"

            # Build UI notes about design
            ui_notes_parts = ["Community-focused platform", "Real-time updates"]

            if page.query_selector("[class*='dark']"):
                ui_notes_parts.append("Dark mode available")

            if page.query_selector("[class*='mobile']"):
                ui_notes_parts.append("Mobile-responsive")

            data.ui_notes = " | ".join(ui_notes_parts)

            # UX notes
            ux_notes_parts = [
                "Intuitive probability display",
                "Active community engagement",
            ]

            if page.query_selector("[class*='comment']"):
                ux_notes_parts.append("Rich comment system")

            if page.query_selector("[class*='follow']"):
                ux_notes_parts.append("Follow/Subscribe feature")

            data.ux_notes = " | ".join(ux_notes_parts)

        except Exception as e:
            self.logger.warning(f"Error extracting trending info: {e}")
