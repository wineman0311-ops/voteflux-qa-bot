"""
Scraper for Polymarket platform (polymarket.com).

Extracts market data, trends, and blockchain information from Polymarket.
Focuses on DeFi-based prediction markets with USDC settlement.
"""

import logging
from playwright.sync_api import Page

from config.platforms import PlatformData, CategoryInfo, MarketInfo
from .base_scraper import BaseScraper


class PolymarketScraper(BaseScraper):
    """Scraper for Polymarket blockchain-based prediction market platform."""

    def extract_data(self, page: Page) -> PlatformData:
        """
        Extract data from Polymarket platform.

        Args:
            page: Playwright Page object

        Returns:
            PlatformData with Polymarket market information
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

            # Extract trending/featured markets
            self._extract_markets(page, data)

            # Extract categories/tags
            self._extract_categories(page, data)

            # Extract features
            self._extract_features(page, data)

            # Extract volume and blockchain info
            self._extract_volume_blockchain_info(page, data)

            self.logger.info(
                f"Successfully scraped Polymarket: {data.market_count} markets"
            )

        except Exception as e:
            self.logger.error(f"Error during Polymarket extraction: {e}")
            data.status = "error"
            data.error_msg = str(e)

        return data

    def _extract_markets(self, page: Page, data: PlatformData):
        """
        Extract trending and popular markets.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Look for market cards - Polymarket uses various card structures
            market_selectors = [
                "[class*='market-card']",
                "[class*='prediction-card']",
                "article",
                "[class*='market-tile']",
                ".card",
            ]

            top_markets = []
            found_markets = False

            for selector in market_selectors:
                elements = page.query_selector_all(selector)
                if elements and len(elements) > 0:
                    for el in elements[:15]:  # Top 15
                        try:
                            question = self.safe_text(el, "h2, h3, h4")
                            if not question:
                                question = self.safe_text(el, "[class*='title']")

                            # Extract volume/odds info
                            volume = self.safe_text(el, "[class*='volume']")
                            if not volume:
                                volume = self.safe_text(
                                    el, "[class*='liquidity'], [class*='odds']"
                                )
                            if not volume:
                                volume = self.safe_text(
                                    el, "span:has-text('$'), span:has-text('USDC')"
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
                        found_markets = True
                        break

            data.top_markets = top_markets[:10]
            data.live_market_count = len(top_markets)

            # Try to find total market count
            count_text = self.safe_text(
                page, "[class*='market-count'], span:has-text('markets')"
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
        Extract market categories and tags.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Look for category/tag filters
            tag_selectors = [
                "[class*='tag']",
                "[class*='category']",
                "button[class*='filter']",
                ".category-button",
            ]

            categories = {}

            for selector in tag_selectors:
                elements = page.query_selector_all(selector)
                if elements:
                    for el in elements[:20]:
                        try:
                            tag_text = el.inner_text().strip()
                            if (
                                tag_text
                                and len(tag_text) < 30
                                and tag_text.lower()
                                not in ["filter", "all", "trending"]
                            ):
                                categories[tag_text] = categories.get(tag_text, 0) + 1
                        except Exception as e:
                            self.logger.debug(f"Error extracting tag: {e}")

                    if categories:
                        break

            # If no categories found, look for common ones
            if not categories:
                common_categories = ["Politics", "Crypto", "Sports", "Finance"]
                for cat in common_categories:
                    if page.query_selector(f"text={cat}"):
                        categories[cat] = 1

            data.categories = [
                CategoryInfo(name=name, count=count)
                for name, count in sorted(
                    categories.items(), key=lambda x: x[1], reverse=True
                )[:10]
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
            features = ["Blockchain-based", "USDC settlement"]

            # Check for key features
            if page.query_selector("text=API") or page.query_selector(
                "[class*='api']"
            ):
                features.append("API available")

            if page.query_selector("text=Mobile") or page.query_selector(
                "[class*='mobile']"
            ):
                features.append("Mobile app")

            if page.query_selector("text=Ethereum") or page.query_selector(
                "text=Polygon"
            ):
                features.append("Multi-chain support")

            if page.query_selector("text=NFT"):
                features.append("NFT integration")

            if page.query_selector("text=Liquidity mining") or page.query_selector(
                "text=rewards"
            ):
                features.append("Liquidity rewards")

            # Check for orderbook
            if page.query_selector("text=Orderbook") or page.query_selector(
                "[class*='orderbook']"
            ):
                features.append("Orderbook trading")

            data.features = features

        except Exception as e:
            self.logger.warning(f"Error extracting features: {e}")
            data.features = ["Blockchain-based", "USDC settlement"]

    def _extract_volume_blockchain_info(self, page: Page, data: PlatformData):
        """
        Extract trading volume and blockchain information.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Look for volume information
            volume_text = self.safe_text(page, "[class*='volume'], [class*='liquidity']")
            if volume_text:
                data.trading_volume_info = f"24h Volume: {volume_text}"

            # Build UI/UX notes
            ui_notes_parts = ["Blockchain-based prediction market", "USDC settlement"]

            # Check if on-chain data is prominently displayed
            if page.query_selector("[class*='chain'], [class*='ethereum']"):
                ui_notes_parts.append("On-chain data visible")

            # Check for AMM or orderbook UX
            if page.query_selector("text=AMM") or page.query_selector(
                "[class*='amm']"
            ):
                ui_notes_parts.append("AMM-based pricing")

            if page.query_selector("text=Orderbook"):
                ui_notes_parts.append("Orderbook interface available")

            data.ui_notes = " | ".join(ui_notes_parts)

            # UX notes about interface design
            ux_notes_parts = []
            if page.query_selector("[class*='dark-mode'], [class*='dark']"):
                ux_notes_parts.append("Dark mode available")

            if page.query_selector("[class*='responsive']"):
                ux_notes_parts.append("Responsive design")

            ux_notes_parts.append("Real-time price updates")

            if ux_notes_parts:
                data.ux_notes = " | ".join(ux_notes_parts)

        except Exception as e:
            self.logger.warning(f"Error extracting volume/blockchain info: {e}")
