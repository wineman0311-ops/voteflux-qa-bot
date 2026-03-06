"""
Abstract base class for all platform scrapers.

Provides common functionality for web scraping with Playwright, error handling,
and safe element selection.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional
import logging

from playwright.sync_api import sync_playwright, Page, Browser
from config.platforms import PlatformData


class BaseScraper(ABC):
    """Abstract base class for platform scrapers."""

    def __init__(self, platform_config: dict):
        """
        Initialize scraper with platform configuration.

        Args:
            platform_config: Dictionary containing platform configuration with
                           keys: id, name, url, role
        """
        self.config = platform_config
        self.logger = logging.getLogger(f"scraper.{platform_config['id']}")
        self.timeout = 30000  # 30 seconds default

    def scrape(self) -> PlatformData:
        """
        Main entry point: launch browser, scrape data, return structured data.

        Returns:
            PlatformData with extracted information or error status
        """
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                )
                page = context.new_page()
                page.set_default_timeout(self.timeout)

                # Extract data
                data = self.extract_data(page)

                # Clean up
                browser.close()
                data.scraped_at = datetime.now()
                return data

        except Exception as e:
            self.logger.error(f"Scraping {self.config['name']} failed: {e}")
            return PlatformData(
                id=self.config["id"],
                name=self.config["name"],
                url=self.config["url"],
                role=self.config["role"],
                status="error",
                error_msg=str(e),
                scraped_at=datetime.now(),
            )

    @abstractmethod
    def extract_data(self, page: Page) -> PlatformData:
        """
        Extract data from the platform page.

        Must be implemented by subclasses.

        Args:
            page: Playwright Page object

        Returns:
            PlatformData with extracted information
        """
        pass

    def safe_text(self, page: Page, selector: str, default: str = "") -> str:
        """
        Safely extract text from element selector.

        Args:
            page: Playwright Page object
            selector: CSS selector
            default: Default value if extraction fails

        Returns:
            Extracted text or default value
        """
        try:
            el = page.query_selector(selector)
            if el:
                text = el.inner_text()
                return text.strip() if text else default
            return default
        except Exception as e:
            self.logger.debug(f"Error extracting text from {selector}: {e}")
            return default

    def safe_count(self, page: Page, selector: str) -> int:
        """
        Count elements matching selector.

        Args:
            page: Playwright Page object
            selector: CSS selector

        Returns:
            Number of matching elements
        """
        try:
            return len(page.query_selector_all(selector))
        except Exception as e:
            self.logger.debug(f"Error counting elements {selector}: {e}")
            return 0

    def safe_all_texts(self, page: Page, selector: str) -> List[str]:
        """
        Get all text contents from matching selectors.

        Args:
            page: Playwright Page object
            selector: CSS selector

        Returns:
            List of extracted text strings
        """
        try:
            elements = page.query_selector_all(selector)
            texts = []
            for el in elements:
                text = el.inner_text()
                if text:
                    stripped = text.strip()
                    if stripped:
                        texts.append(stripped)
            return texts
        except Exception as e:
            self.logger.debug(f"Error extracting all texts from {selector}: {e}")
            return []

    def safe_attribute(
        self, page: Page, selector: str, attribute: str, default: str = ""
    ) -> str:
        """
        Safely extract attribute from element selector.

        Args:
            page: Playwright Page object
            selector: CSS selector
            attribute: Attribute name to extract
            default: Default value if extraction fails

        Returns:
            Attribute value or default
        """
        try:
            el = page.query_selector(selector)
            if el:
                value = el.get_attribute(attribute)
                return value if value else default
            return default
        except Exception as e:
            self.logger.debug(
                f"Error extracting attribute {attribute} from {selector}: {e}"
            )
            return default

    def wait_for_load(self, page: Page, timeout: int = 10000):
        """
        Wait for page to load completely.

        Args:
            page: Playwright Page object
            timeout: Timeout in milliseconds
        """
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception as e:
            self.logger.debug(f"Network idle timeout: {e}")
            # Continue anyway - page might be functional
