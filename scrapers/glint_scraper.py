"""
Scraper for Glint platform (glint.trade).

Extracts market data, categories, and interface design characteristics from Glint.
Focuses on market information and user experience design.
"""

import logging
from playwright.sync_api import Page

from config.platforms import PlatformData, CategoryInfo, MarketInfo
from .base_scraper import BaseScraper


class GlintScraper(BaseScraper):
    """Scraper for Glint prediction market platform."""

    def extract_data(self, page: Page) -> PlatformData:
        """
        Extract data from Glint platform.

        Args:
            page: Playwright Page object

        Returns:
            PlatformData with Glint market information
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

            # Extract categories
            self._extract_categories(page, data)

            # Extract features
            self._extract_features(page, data)

            # Extract design/UX information
            self._extract_design_info(page, data)

            self.logger.info(f"Successfully scraped Glint: {data.market_count} markets")

        except Exception as e:
            self.logger.error(f"Error during Glint extraction: {e}")
            data.status = "error"
            data.error_msg = str(e)

        return data

    def _extract_markets(self, page: Page, data: PlatformData):
        """
        Extract market information and counts.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Look for market listings
            market_selectors = [
                "[class*='market']",
                "[class*='prediction']",
                "[class*='card']",
                "[role='row']",
                "article",
            ]

            top_markets = []

            for selector in market_selectors:
                elements = page.query_selector_all(selector)
                if elements and len(elements) > 2:
                    for el in elements[:15]:
                        try:
                            question = self.safe_text(el, "h2, h3, h4")
                            if not question:
                                question = self.safe_text(el, "[class*='title']")
                            if not question:
                                question = self.safe_text(el, "a")

                            # Extract volume/liquidity
                            volume = self.safe_text(
                                el, "[class*='volume'], [class*='liquidity']"
                            )
                            if not volume:
                                volume = self.safe_text(
                                    el, "[class*='price'], [class*='odds']"
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
            count_text = self.safe_text(page, "[class*='count'], span:has-text('market')")
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
        Extract market categories and tags.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Look for category/filter elements
            category_selectors = [
                "[class*='category']",
                "[class*='filter']",
                "[class*='tag']",
                "button[class*='filter']",
            ]

            categories = {}

            for selector in category_selectors:
                elements = page.query_selector_all(selector)
                if elements:
                    for el in elements[:20]:
                        try:
                            cat_text = el.inner_text().strip()
                            if (
                                cat_text
                                and len(cat_text) < 40
                                and cat_text.lower()
                                not in ["filter", "all", "clear", "search"]
                            ):
                                categories[cat_text] = categories.get(cat_text, 0) + 1
                        except Exception as e:
                            self.logger.debug(f"Error extracting category: {e}")

                    if categories:
                        break

            # Default categories if none found
            if not categories:
                categories = {
                    "Finance": 0,
                    "Technology": 0,
                    "Politics": 0,
                    "Sports": 0,
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
        Extract platform features.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            features = ["Prediction markets"]

            # Check for real money
            if page.query_selector("text=Real money") or page.query_selector(
                "text=cash"
            ):
                features.append("Real money trading")

            # Check for API
            if page.query_selector("text=API"):
                features.append("API available")

            # Check for mobile
            if page.query_selector("text=Mobile") or page.query_selector(
                "[class*='mobile']"
            ):
                features.append("Mobile app")

            # Check for live markets
            if page.query_selector("text=Live"):
                features.append("Live markets")

            # Check for charting
            if page.query_selector("[class*='chart']") or page.query_selector(
                "text=Chart"
            ):
                features.append("Price charts")

            # Check for wallet/account features
            if page.query_selector("text=Wallet") or page.query_selector(
                "[class*='wallet']"
            ):
                features.append("Integrated wallet")

            # Check for notifications
            if page.query_selector("text=Alert") or page.query_selector(
                "[class*='notification']"
            ):
                features.append("Price alerts")

            data.features = features if features else ["Prediction markets"]

        except Exception as e:
            self.logger.warning(f"Error extracting features: {e}")
            data.features = ["Prediction markets"]

    def _extract_design_info(self, page: Page, data: PlatformData):
        """
        Extract UI/UX design characteristics.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            ui_notes_parts = []

            # Check for color scheme
            if page.query_selector("[class*='dark']"):
                ui_notes_parts.append("Dark mode available")
            else:
                ui_notes_parts.append("Light theme")

            # Check for design system characteristics
            if page.query_selector("[class*='shadow']"):
                ui_notes_parts.append("Elevated card design")

            if page.query_selector("[class*='border-radius']"):
                ui_notes_parts.append("Rounded components")

            # Check for layout
            if page.query_selector("[class*='grid']"):
                ui_notes_parts.append("Grid layout")
            elif page.query_selector("[class*='flex']"):
                ui_notes_parts.append("Flexbox layout")

            # Check for typography
            if page.query_selector("[class*='sans-serif']"):
                ui_notes_parts.append("Modern sans-serif typography")

            if ui_notes_parts:
                data.ui_notes = " | ".join(ui_notes_parts)
            else:
                data.ui_notes = "Standard market interface"

            # UX notes about interaction design
            ux_notes_parts = []

            # Check for responsiveness
            if page.query_selector("[class*='responsive']"):
                ux_notes_parts.append("Responsive design")

            # Check for interactions
            if page.query_selector("[class*='hover']"):
                ux_notes_parts.append("Interactive hover states")

            if page.query_selector("[class*='tooltip']"):
                ux_notes_parts.append("Contextual tooltips")

            # Check for accessibility
            if page.query_selector("[role='button']") or page.query_selector(
                "[aria-label]"
            ):
                ux_notes_parts.append("Accessible interactive elements")

            # Check for smooth animations
            if page.query_selector("[class*='transition']") or page.query_selector(
                "[class*='animate']"
            ):
                ux_notes_parts.append("Smooth transitions")

            if ux_notes_parts:
                data.ux_notes = " | ".join(ux_notes_parts)
            else:
                data.ux_notes = "Functional user experience"

            # Extract volume information
            volume_text = self.safe_text(page, "[class*='volume'], [class*='liquidity']")
            if volume_text:
                data.trading_volume_info = f"Volume: {volume_text}"

        except Exception as e:
            self.logger.warning(f"Error extracting design info: {e}")
