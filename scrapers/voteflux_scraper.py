"""
Scraper for VoteFlux platform (voteflux.com).

Extracts market data, categories, and platform features from VoteFlux.
Handles authentication with optional Google login support.
"""

import os
import logging
from typing import Optional
from playwright.sync_api import Page

from config.platforms import PlatformData, CategoryInfo, MarketInfo
from .base_scraper import BaseScraper


class VoteFluxScraper(BaseScraper):
    """Scraper for VoteFlux prediction market platform."""

    def __init__(self, platform_config: dict):
        """Initialize VoteFlux scraper."""
        super().__init__(platform_config)
        self.email = os.getenv("VF_EMAIL", "")
        self.password = os.getenv("VF_PASSWORD", "")

    def extract_data(self, page: Page) -> PlatformData:
        """
        Extract data from VoteFlux platform.

        Args:
            page: Playwright Page object

        Returns:
            PlatformData with VoteFlux market information
        """
        data = PlatformData(
            id=self.config["id"],
            name=self.config["name"],
            url=self.config["url"],
            role=self.config["role"],
            status="success",
        )

        try:
            # Navigate to platform
            self.logger.info(f"Navigating to {self.config['url']}")
            page.goto(self.config["url"], wait_until="domcontentloaded")
            self.wait_for_load(page)

            # Check for login wall
            login_wall_detected = self._check_login_wall(page)
            if login_wall_detected:
                data.ui_notes = "Login wall detected on homepage"
                self.logger.warning("Login wall detected - attempting authentication")

                if self.email and self.password:
                    try:
                        self._attempt_google_login(page)
                        data.ui_notes = "Authenticated via Google login"
                    except Exception as e:
                        self.logger.warning(f"Google login failed: {e}")
                        data.ui_notes = (
                            "Login wall present - Google login failed, returning limited data"
                        )
                        data.status = "error"
                        data.error_msg = "Authentication required but failed"
                        return data
                else:
                    self.logger.info("No credentials provided for VoteFlux authentication")
                    data.ui_notes = "Login wall present - no credentials provided"
                    data.status = "skipped"
                    return data

            # Extract markets
            self._extract_markets(page, data)

            # Extract categories
            self._extract_categories(page, data)

            # Extract features
            self._extract_features(page, data)

            # Extract trading info
            self._extract_trading_info(page, data)

            self.logger.info(
                f"Successfully scraped VoteFlux: {data.market_count} markets"
            )

        except Exception as e:
            self.logger.error(f"Error during VoteFlux extraction: {e}")
            data.status = "error"
            data.error_msg = str(e)

        return data

    def _check_login_wall(self, page: Page) -> bool:
        """
        Check if login wall is present.

        Args:
            page: Playwright Page object

        Returns:
            True if login wall detected
        """
        try:
            # Look for common login indicators
            login_indicators = [
                "text=Sign in",
                "text=Sign up",
                "button:has-text('Sign in')",
                "[aria-label*='Sign in']",
                ".login-wall",
            ]

            for selector in login_indicators:
                el = page.query_selector(selector)
                if el:
                    self.logger.debug(f"Login indicator found: {selector}")
                    return True

            return False
        except Exception as e:
            self.logger.debug(f"Error checking login wall: {e}")
            return False

    def _attempt_google_login(self, page: Page):
        """
        Attempt to authenticate via Google.

        Args:
            page: Playwright Page object

        Raises:
            Exception if login fails
        """
        self.logger.info("Attempting Google login")

        # Look for Google login button
        google_button = page.query_selector("button:has-text('Google')")
        if not google_button:
            google_button = page.query_selector("button:has-text('Sign in with Google')")

        if google_button:
            google_button.click()
            page.wait_for_timeout(1000)

            # Handle Google login popup/redirect
            page.fill('input[type="email"]', self.email)
            page.click("button:has-text('Next')")
            page.wait_for_timeout(1000)

            page.fill('input[type="password"]', self.password)
            page.click("button:has-text('Next')")
            page.wait_for_timeout(2000)

            self.wait_for_load(page)
            self.logger.info("Google login completed")
        else:
            raise Exception("Google login button not found")

    def _extract_markets(self, page: Page, data: PlatformData):
        """
        Extract market count and top markets.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            # Try to find market count
            market_count_text = self.safe_text(page, "[class*='market-count']")
            if not market_count_text:
                market_count_text = self.safe_text(page, "[class*='total-markets']")

            if market_count_text:
                try:
                    data.market_count = int("".join(filter(str.isdigit, market_count_text)))
                except (ValueError, AttributeError):
                    pass

            # Extract top markets
            market_selectors = [
                ".market-item",
                "[class*='market-card']",
                "[class*='prediction-card']",
                "article[class*='market']",
            ]

            top_markets = []
            for selector in market_selectors:
                elements = page.query_selector_all(selector)
                if elements:
                    for el in elements[:5]:  # Top 5
                        try:
                            question = self.safe_text(el, "[class*='question']")
                            if not question:
                                question = self.safe_text(el, "h3")
                            if not question:
                                question = self.safe_text(el, "h4")

                            volume = self.safe_text(el, "[class*='volume']")
                            participants = None

                            if question:
                                top_markets.append(
                                    MarketInfo(question=question, volume=volume)
                                )
                        except Exception as e:
                            self.logger.debug(f"Error extracting market: {e}")

                    break

            data.top_markets = top_markets[:5]
            data.live_market_count = len(top_markets)

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
            category_selectors = [
                "[class*='category']",
                "[class*='tag']",
                ".filter-option",
            ]

            categories = {}
            for selector in category_selectors:
                elements = page.query_selector_all(selector)
                if elements:
                    for el in elements:
                        try:
                            cat_text = el.inner_text()
                            if cat_text and len(cat_text) < 50:
                                cat_name = cat_text.strip()
                                categories[cat_name] = categories.get(cat_name, 0) + 1
                        except Exception as e:
                            self.logger.debug(f"Error processing category: {e}")

                if categories:
                    break

            # Convert to CategoryInfo objects
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
            features = []

            # Check for various features
            if page.query_selector("text=Real money") or page.query_selector(
                "text=real money"
            ):
                features.append("Real money trading")

            if page.query_selector("text=Live markets") or page.query_selector(
                "[class*='live']"
            ):
                features.append("Live markets")

            if page.query_selector("text=API") or page.query_selector("[class*='api']"):
                features.append("API available")

            if page.query_selector("text=Mobile") or page.query_selector(
                "[class*='mobile-app']"
            ):
                features.append("Mobile app")

            # Check for regulatory info
            if page.query_selector("text=Regulated") or page.query_selector(
                "text=SEC"
            ):
                features.append("Regulated")

            if page.query_selector("text=Bitcoin") or page.query_selector("text=crypto"):
                features.append("Crypto support")

            data.features = features if features else ["Prediction markets"]

        except Exception as e:
            self.logger.warning(f"Error extracting features: {e}")
            data.features = ["Prediction markets"]

    def _extract_trading_info(self, page: Page, data: PlatformData):
        """
        Extract trading volume and liquidity information.

        Args:
            page: Playwright Page object
            data: PlatformData to update
        """
        try:
            volume_text = self.safe_text(page, "[class*='volume']")
            if not volume_text:
                volume_text = self.safe_text(page, "[class*='liquidity']")

            if volume_text:
                data.trading_volume_info = volume_text

            # Look for fee information
            fee_text = self.safe_text(page, "[class*='fee']")
            if fee_text:
                data.ux_notes = (
                    data.ux_notes or "" + f"Fees: {fee_text}"
                ).strip()

        except Exception as e:
            self.logger.warning(f"Error extracting trading info: {e}")
