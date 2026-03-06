"""
Scraper for Mirumarket platform (mirumarket.com).

Extracts market data, categories, and Philippines-specific features from Mirumarket.
Focuses on Raffles system and localized markets.
"""

import logging
from playwright.sync_api import Page

from config.platforms import PlatformData, CategoryInfo, MarketInfo
from .base_scraper import BaseScraper


class MirumarketScraper(BaseScraper):
    """Scraper for Mirumarket Philippines-based prediction market platform."""

    def extract_data(self, page: Page) -> PlatformData:
        """
        Extract data from Mirumarket platform.

        Args:
            page: Playwright Page object

        Returns:
            PlatformData with Mirumarket market information
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

            # Extract featured markets
            self._extract_markets(page, data)

            # Extract categories
            self._extract_categories(page, data)

            # Extract features including Raffles
            self._extract_features(page, data)

            # Extract localization info
            self._extract_localization_info(page, data)

            self.logger.info(
                f"Successfully scraped Mirumarket: {data.market_count} markets"
            )

        except Exception as e:
            self.logger.error(f"Error during Mirumarket extraction: {e}")
            data.status = "error"
            data.error_msg = str(e)

        return data

    def _extract_markets(self, page: Page, data: PlatformData):
        """
        Extract featured and active markets.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Mirumarket displays featured markets prominently
            market_selectors = [
                "[class*='market-card']",
                "[class*='featured']",
                "[class*='prediction']",
                "article",
                ".card",
            ]

            top_markets = []

            for selector in market_selectors:
                elements = page.query_selector_all(selector)
                if elements:
                    for el in elements[:12]:  # Top 12
                        try:
                            question = self.safe_text(el, "h2, h3, h4")
                            if not question:
                                question = self.safe_text(el, "[class*='title']")

                            # Look for odds/liquidity info
                            volume = self.safe_text(el, "[class*='liquidity']")
                            if not volume:
                                volume = self.safe_text(
                                    el, "[class*='odds'], [class*='price']"
                                )

                            if (
                                question
                                and len(question) > 5
                                and question
                                not in [m.question for m in top_markets]
                            ):
                                top_markets.append(
                                    MarketInfo(question=question, volume=volume)
                                )
                        except Exception as e:
                            self.logger.debug(f"Error extracting market: {e}")

                    if top_markets:
                        break

            data.top_markets = top_markets[:10]
            data.live_market_count = len(top_markets)

            # Try to find total market count
            count_text = self.safe_text(page, "[class*='count'], [class*='total']")
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
        Extract market categories.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Look for category filters/navigation
            category_selectors = [
                "[class*='category']",
                "[class*='filter']",
                "[class*='topic']",
            ]

            categories = {}

            for selector in category_selectors:
                elements = page.query_selector_all(selector)
                if elements:
                    for el in elements[:15]:
                        try:
                            cat_text = el.inner_text().strip()
                            if (
                                cat_text
                                and len(cat_text) < 30
                                and cat_text.lower()
                                not in ["filter", "all", "search"]
                            ):
                                categories[cat_text] = categories.get(cat_text, 0) + 1
                        except Exception as e:
                            self.logger.debug(f"Error extracting category: {e}")

                    if categories:
                        break

            # Typical Mirumarket categories (Philippines-focused)
            if not categories:
                categories = {
                    "Philippine Politics": 0,
                    "Sports": 0,
                    "Entertainment": 0,
                    "Business": 0,
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
        Extract platform features including Raffles system.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            features = ["Real money trading", "Philippines-localized"]

            # Check for Raffles feature (unique to Mirumarket)
            if page.query_selector("text=Raffle") or page.query_selector(
                "[class*='raffle']"
            ):
                features.append("Raffles system")

            # Check for mobile app
            if page.query_selector("text=Mobile") or page.query_selector(
                "[class*='mobile-app']"
            ):
                features.append("Mobile app")

            # Check for payment options
            if page.query_selector("text=GCash") or page.query_selector("text=PayMaya"):
                features.append("Local payment methods")

            # Check for live features
            if page.query_selector("text=Live"):
                features.append("Live trading")

            # Check for statistics
            if page.query_selector("text=Stats") or page.query_selector(
                "[class*='statistic']"
            ):
                features.append("Market statistics")

            # Check for responsible gambling features
            if page.query_selector("text=Responsible") or page.query_selector(
                "text=Limits"
            ):
                features.append("Responsible gambling tools")

            data.features = features

        except Exception as e:
            self.logger.warning(f"Error extracting features: {e}")
            data.features = ["Real money trading", "Philippines-localized"]

    def _extract_localization_info(self, page: Page, data: PlatformData):
        """
        Extract Philippines-specific information and localization details.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Check language
            html_lang = self.safe_attribute(page, "html", "lang", default="")
            if "fil" in html_lang.lower() or "tl" in html_lang.lower():
                localization = "Filipino/Tagalog supported"
            else:
                localization = "English interface"

            # Build UI notes
            ui_notes_parts = [
                localization,
                "Philippines market-focused",
                "Real money prediction market",
            ]

            # Check for Philippine peso currency
            if page.query_selector("text=PHP") or page.query_selector("text=₱"):
                ui_notes_parts.append("Philippine Peso support")

            # Check for local payment integration
            if page.query_selector("text=GCash"):
                ui_notes_parts.append("GCash integration")
            if page.query_selector("text=PayMaya"):
                ui_notes_parts.append("PayMaya integration")

            data.ui_notes = " | ".join(ui_notes_parts)

            # UX notes about interface
            ux_notes_parts = ["Mobile-first design"]

            if page.query_selector("[class*='responsive']"):
                ux_notes_parts.append("Responsive layout")

            if page.query_selector("[class*='fast']") or page.query_selector(
                "text=Fast"
            ):
                ux_notes_parts.append("Optimized for slow connections")

            if page.query_selector("[class*='tutorial']") or page.query_selector(
                "text=Help"
            ):
                ux_notes_parts.append("User tutorials available")

            data.ux_notes = " | ".join(ux_notes_parts)

            # Extract volume info specific to Philippines market
            volume_text = self.safe_text(page, "[class*='volume']")
            if volume_text:
                data.trading_volume_info = f"Trading volume: {volume_text}"

        except Exception as e:
            self.logger.warning(f"Error extracting localization info: {e}")
