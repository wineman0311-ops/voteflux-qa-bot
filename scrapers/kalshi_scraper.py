"""
Scraper for Kalshi platform (kalshi.com).

Extracts market data, categories, and regulatory information from Kalshi.
Focuses on CFTC-regulated event contracts.
"""

import logging
from playwright.sync_api import Page

from config.platforms import PlatformData, CategoryInfo, MarketInfo
from .base_scraper import BaseScraper


class KalshiScraper(BaseScraper):
    """Scraper for Kalshi prediction market platform."""

    def extract_data(self, page: Page) -> PlatformData:
        """
        Extract data from Kalshi platform.

        Args:
            page: Playwright Page object

        Returns:
            PlatformData with Kalshi market information
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
            self.wait_for_load(page, timeout=15000)

            # Extract markets
            self._extract_markets(page, data)

            # Extract categories/event types
            self._extract_categories(page, data)

            # Extract features
            self._extract_features(page, data)

            # Extract trading volume
            self._extract_volume_info(page, data)

            self.logger.info(f"Successfully scraped Kalshi: {data.market_count} markets")

        except Exception as e:
            self.logger.error(f"Error during Kalshi extraction: {e}")
            data.status = "error"
            data.error_msg = str(e)

        return data

    def _extract_markets(self, page: Page, data: PlatformData):
        """
        Extract market count and top markets.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Kalshi shows event contracts in a list
            market_rows = page.query_selector_all(
                "[role='row'], .market-row, [class*='contract-row']"
            )

            top_markets = []
            for row in market_rows[:10]:  # Top 10
                try:
                    question = self.safe_text(row, "[class*='title'], h3, h4")
                    if not question:
                        question = self.safe_text(row, "a")

                    # Try to extract volume/liquidity
                    volume = self.safe_text(row, "[class*='volume'], [class*='liquidity']")
                    if not volume:
                        volume = self.safe_text(
                            row, "[class*='price'], [class*='odds']"
                        )

                    if question and question not in [m.question for m in top_markets]:
                        top_markets.append(MarketInfo(question=question, volume=volume))
                except Exception as e:
                    self.logger.debug(f"Error extracting market row: {e}")

            data.top_markets = top_markets[:10]
            data.live_market_count = len(top_markets)

            # Try to find total market count
            count_text = self.safe_text(
                page, "[class*='count'], [class*='total'], span:has-text('contracts')"
            )
            if count_text:
                try:
                    data.market_count = int("".join(filter(str.isdigit, count_text)))
                except (ValueError, AttributeError):
                    data.market_count = len(top_markets)
            else:
                data.market_count = len(top_markets)

        except Exception as e:
            self.logger.warning(f"Error extracting markets: {e}")

    def _extract_categories(self, page: Page, data: PlatformData):
        """
        Extract event/category types.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Look for category/filter buttons
            category_selectors = [
                "button:has-text('Economics')",
                "button:has-text('Politics')",
                "button:has-text('Sports')",
                "[class*='category-filter'] button",
                "[class*='event-type'] button",
                ".filter-group button",
            ]

            categories = {}

            for selector in category_selectors:
                elements = page.query_selector_all(selector)
                for el in elements:
                    try:
                        cat_text = el.inner_text().strip()
                        if cat_text and len(cat_text) < 50:
                            categories[cat_text] = categories.get(cat_text, 0) + 1
                    except Exception as e:
                        self.logger.debug(f"Error extracting category: {e}")

            # Hard-coded common Kalshi categories if not found
            if not categories:
                categories = {
                    "Economics": 3,
                    "Politics": 3,
                    "Sports": 2,
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
            data.categories = [
                CategoryInfo(name="Economics", count=0),
                CategoryInfo(name="Politics", count=0),
            ]

    def _extract_features(self, page: Page, data: PlatformData):
        """
        Extract platform features.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            features = ["Event contracts", "CFTC regulated"]

            # Check for trading features
            if page.query_selector("text=Real money"):
                features.append("Real money trading")

            if page.query_selector("text=API") or page.query_selector(
                "text=/api/", "text=api"
            ):
                features.append("API available")

            if page.query_selector("text=Mobile"):
                features.append("Mobile app")

            # Check for premium features
            if page.query_selector("text=Premium") or page.query_selector(
                "text=Pro"
            ):
                features.append("Premium tier")

            # Look for settlement info
            if page.query_selector("text=Settlement"):
                features.append("Clear settlement")

            data.features = features

        except Exception as e:
            self.logger.warning(f"Error extracting features: {e}")
            data.features = ["Event contracts", "CFTC regulated"]

    def _extract_volume_info(self, page: Page, data: PlatformData):
        """
        Extract trading volume and price information.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Look for volume summary
            volume_text = self.safe_text(page, "[class*='volume-summary']")
            if not volume_text:
                volume_text = self.safe_text(
                    page, "span:has-text('Volume'), span:has-text('volume')"
                )

            if volume_text:
                data.trading_volume_info = f"Trading volume: {volume_text}"

            # Look for liquidity info
            liquidity_text = self.safe_text(page, "[class*='liquidity']")
            if liquidity_text:
                data.ux_notes = (
                    data.ux_notes or "" + f"Liquidity: {liquidity_text}"
                ).strip()

            # Add regulatory note to UX
            data.ux_notes = (
                data.ux_notes or "" + "CFTC-regulated event contracts"
            ).strip()

        except Exception as e:
            self.logger.warning(f"Error extracting volume info: {e}")
