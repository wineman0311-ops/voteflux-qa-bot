"""
Scraper for YesNo Markets platform (app.yesnomarkets.com).

Extracts market data, categories, and features from YesNo Markets.
This is a newer platform - captures comprehensive data including all available features.
"""

import logging
from playwright.sync_api import Page

from config.platforms import PlatformData, CategoryInfo, MarketInfo
from .base_scraper import BaseScraper


class YesNoScraper(BaseScraper):
    """Scraper for YesNo Markets prediction market platform."""

    def extract_data(self, page: Page) -> PlatformData:
        """
        Extract comprehensive data from YesNo Markets platform.

        Args:
            page: Playwright Page object

        Returns:
            PlatformData with YesNo Markets information
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

            # Extract all market data
            self._extract_markets(page, data)

            # Extract categories
            self._extract_categories(page, data)

            # Extract comprehensive feature list
            self._extract_features(page, data)

            # Extract market mechanics and info
            self._extract_market_info(page, data)

            self.logger.info(
                f"Successfully scraped YesNo Markets: {data.market_count} markets"
            )

        except Exception as e:
            self.logger.error(f"Error during YesNo Markets extraction: {e}")
            data.status = "error"
            data.error_msg = str(e)

        return data

    def _extract_markets(self, page: Page, data: PlatformData):
        """
        Extract market count and available markets.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # YesNo Markets displays markets in various formats
            market_selectors = [
                "[class*='market-card']",
                "[class*='market-row']",
                "[class*='prediction-card']",
                "div[class*='border']",
                "[role='row']",
            ]

            top_markets = []
            found_markets = False

            for selector in market_selectors:
                elements = page.query_selector_all(selector)
                if elements and len(elements) > 2:
                    self.logger.debug(
                        f"Found {len(elements)} elements with selector {selector}"
                    )

                    for el in elements[:20]:  # Top 20
                        try:
                            # Extract question/title
                            question = self.safe_text(el, "h2, h3, h4, [class*='title']")
                            if not question:
                                question = self.safe_text(el, "a")

                            if question and len(question) > 3:
                                # Extract volume/odds
                                volume = self.safe_text(
                                    el, "[class*='odds'], [class*='price'], [class*='probability']"
                                )
                                if not volume:
                                    volume = self.safe_text(
                                        el, "[class*='volume'], [class*='liquidity']"
                                    )

                                # Extract participant count if available
                                participants_text = self.safe_text(
                                    el, "[class*='participants'], [class*='traders']"
                                )
                                participants = None
                                if participants_text:
                                    try:
                                        participants = int(
                                            "".join(
                                                filter(str.isdigit, participants_text)
                                            )
                                        )
                                    except (ValueError, AttributeError):
                                        pass

                                if question not in [m.question for m in top_markets]:
                                    top_markets.append(
                                        MarketInfo(
                                            question=question,
                                            volume=volume,
                                            participants=participants,
                                        )
                                    )
                        except Exception as e:
                            self.logger.debug(f"Error extracting market: {e}")

                    if top_markets:
                        found_markets = True
                        break

            data.top_markets = top_markets[:15]
            data.live_market_count = len(top_markets)

            # Extract total market count
            count_text = self.safe_text(
                page, "[class*='market-count'], span:has-text('market')"
            )
            if count_text:
                try:
                    data.market_count = int("".join(filter(str.isdigit, count_text)))
                except (ValueError, AttributeError):
                    data.market_count = len(top_markets)
            else:
                data.market_count = len(top_markets)

            if found_markets:
                self.logger.info(
                    f"Extracted {len(top_markets)} markets from YesNo Markets"
                )

        except Exception as e:
            self.logger.warning(f"Error extracting markets: {e}")

    def _extract_categories(self, page: Page, data: PlatformData):
        """
        Extract comprehensive category information.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Look for category navigation/filters
            category_selectors = [
                "[class*='category']",
                "[class*='filter']",
                "[class*='tag']",
                "[class*='topic']",
                "button[class*='category']",
            ]

            categories = {}

            for selector in category_selectors:
                elements = page.query_selector_all(selector)
                if elements:
                    self.logger.debug(
                        f"Found {len(elements)} category elements with selector {selector}"
                    )

                    for el in elements[:25]:
                        try:
                            cat_text = el.inner_text().strip()
                            if (
                                cat_text
                                and 3 < len(cat_text) < 40
                                and cat_text.lower()
                                not in [
                                    "filter",
                                    "all",
                                    "clear",
                                    "search",
                                    "trending",
                                ]
                            ):
                                categories[cat_text] = categories.get(cat_text, 0) + 1
                        except Exception as e:
                            self.logger.debug(f"Error extracting category: {e}")

                    if categories:
                        break

            # Common YesNo Markets categories
            if not categories:
                categories = {
                    "Politics": 0,
                    "Sports": 0,
                    "Finance": 0,
                    "Technology": 0,
                    "Entertainment": 0,
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
        Extract comprehensive feature list from YesNo Markets.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            features = ["Binary prediction markets", "Yes/No format"]

            # Check for real money trading
            if page.query_selector("text=Real money") or page.query_selector(
                "text=cash"
            ):
                features.append("Real money trading")

            # Check for play money
            if page.query_selector("text=Virtual") or page.query_selector(
                "text=Play money"
            ):
                features.append("Play money markets")

            # Check for API/integration
            if page.query_selector("text=API"):
                features.append("API available")

            # Check for mobile experience
            if page.query_selector("text=Mobile") or page.query_selector(
                "[class*='mobile-app']"
            ):
                features.append("Mobile app")

            # Check for live trading
            if page.query_selector("text=Live") or page.query_selector(
                "[class*='live']"
            ):
                features.append("Live trading")

            # Check for notifications/alerts
            if page.query_selector("text=Alert") or page.query_selector(
                "text=Notification"
            ):
                features.append("Price alerts")

            # Check for social features
            if page.query_selector("text=Follow") or page.query_selector(
                "[class*='social']"
            ):
                features.append("Social features")

            # Check for leaderboards
            if page.query_selector("text=Leaderboard") or page.query_selector(
                "text=Ranking"
            ):
                features.append("Player rankings")

            # Check for market creation
            if page.query_selector("text=Create") or page.query_selector(
                "text=New market"
            ):
                features.append("User-created markets")

            # Check for advanced features
            if page.query_selector("text=Advanced") or page.query_selector(
                "[class*='advanced']"
            ):
                features.append("Advanced trading tools")

            # Check for charting
            if page.query_selector("[class*='chart']") or page.query_selector(
                "text=Chart"
            ):
                features.append("Price charts")

            # Check for analysis tools
            if page.query_selector("text=Analysis") or page.query_selector(
                "[class*='analytics']"
            ):
                features.append("Market analytics")

            # Check for portfolio tracking
            if page.query_selector("text=Portfolio") or page.query_selector(
                "[class*='portfolio']"
            ):
                features.append("Portfolio tracking")

            data.features = features if features else ["Binary prediction markets"]

        except Exception as e:
            self.logger.warning(f"Error extracting features: {e}")
            data.features = ["Binary prediction markets", "Yes/No format"]

    def _extract_market_info(self, page: Page, data: PlatformData):
        """
        Extract trading volume, market mechanics, and user experience info.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Extract trading volume information
            volume_text = self.safe_text(
                page, "[class*='volume'], [class*='liquidity'], span:has-text('$')"
            )
            if volume_text:
                data.trading_volume_info = f"Trading volume: {volume_text}"

            # Build UI notes
            ui_notes_parts = ["Binary market format", "Real-time price updates"]

            # Check for market resolution info
            if page.query_selector("text=Resolution") or page.query_selector(
                "text=Settled"
            ):
                ui_notes_parts.append("Clear settlement mechanism")

            # Check for commission/fee display
            if page.query_selector("text=Fee") or page.query_selector("text=Commission"):
                ui_notes_parts.append("Transparent fee structure")

            # Check for odds/probability display
            if page.query_selector("text=Odds") or page.query_selector(
                "[class*='probability']"
            ):
                ui_notes_parts.append("Clear odds display")

            if page.query_selector("[class*='dark']"):
                ui_notes_parts.append("Dark mode available")

            if page.query_selector("[class*='responsive']"):
                ui_notes_parts.append("Mobile responsive")

            data.ui_notes = " | ".join(ui_notes_parts)

            # Build UX notes
            ux_notes_parts = ["Intuitive binary selection", "Quick market navigation"]

            # Check for help/tutorials
            if page.query_selector("text=Help") or page.query_selector(
                "[class*='tutorial']"
            ):
                ux_notes_parts.append("User guides available")

            # Check for account setup simplicity
            if page.query_selector("text=Sign up") or page.query_selector(
                "text=Quick"
            ):
                ux_notes_parts.append("Simple account creation")

            # Check for sorting/filtering
            if page.query_selector("[class*='sort']") or page.query_selector(
                "[class*='filter']"
            ):
                ux_notes_parts.append("Market filtering options")

            # Check for search functionality
            if page.query_selector("input[type='search']") or page.query_selector(
                "[class*='search']"
            ):
                ux_notes_parts.append("Market search available")

            data.ux_notes = " | ".join(ux_notes_parts)

        except Exception as e:
            self.logger.warning(f"Error extracting market info: {e}")
