"""
Base scraper class shared by all site-specific scrapers.

Provides browser lifecycle management, safe DOM extraction, section-body
extraction, and the retry-wrapped ``scrape`` entrypoint.
"""

import logging
from typing import Any, Dict, List, Optional

from utils.retry import retry

logger = logging.getLogger(__name__)

# Full modern Chrome 124 User-Agent string
_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/124.0.0.0 Safari/537.36'
)

# Heading tokens that signal the *start* of a new section (used as stop markers)
_SECTION_STOP_HEADINGS = [
    'responsibilities', 'what you will do', 'about the role', 'about the team',
    'about us', 'who we are', 'benefits', 'perks', 'compensation', 'salary',
    'equal opportunity', 'diversity', 'apply now', 'how to apply',
]


class JobSiteScraper:
    """Generic job scraper that can handle multiple job websites.

    Subclass-specific logic lives in ``extract_from_<type>`` methods that are
    dispatched automatically by :meth:`scrape`.
    """

    def __init__(self, site_config: Dict):
        self.config = site_config
        self.browser = None
        self.context = None
        self.page = None
        self.p = None  # Playwright instance — kept to avoid AttributeError in close_browser
        self._runtime_headless = True

    def start_browser(self, headless: bool = True, storage_state: Optional[str] = None) -> None:
        """Start Playwright browser, optionally with a saved auth state.

        Args:
            headless: Run without a visible window (default ``True``).
            storage_state: Path to a Playwright storage-state JSON file.
        """
        from playwright.sync_api import sync_playwright

        self._runtime_headless = headless
        self.p = sync_playwright().start()

        launch_kwargs: Dict[str, Any] = {
            'headless': headless,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--no-default-browser-check',
                '--disable-dev-shm-usage',
            ],
        }
        slow_mo = int(self.config.get('slow_mo_ms', 0) or 0)
        if slow_mo > 0:
            launch_kwargs['slow_mo'] = slow_mo

        self.browser = self.p.chromium.launch(**launch_kwargs)
        context_kwargs: Dict[str, Any] = {'user_agent': _USER_AGENT}
        if storage_state:
            context_kwargs['storage_state'] = storage_state
        self.context = self.browser.new_context(**context_kwargs)
        self.page = self.context.new_page()

        # Best-effort stealth hardening for bot-detection-heavy sites.
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(self.page)
        except Exception as e:
            logger.debug(f"playwright-stealth not applied: {e}")

        logger.info(
            f"Browser started for {self.config['name']} "
            f"(storage_state={'present' if storage_state else 'none'})"
        )

    def close_browser(self) -> None:
        """Close all Playwright resources.

        Each resource is closed individually so that a failure in one does not
        prevent the others from being released.
        """
        try:
            if self.page:
                self.page.close()
        except Exception as e:
            logger.warning(f"Error closing page: {e}")
        try:
            if self.context:
                self.context.close()
        except Exception as e:
            logger.warning(f"Error closing context: {e}")
        try:
            if self.browser:
                self.browser.close()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
        try:
            if self.p:
                self.p.stop()
        except Exception as e:
            logger.warning(f"Error stopping Playwright: {e}")

    @retry(max_attempts=3, delay=2.0)
    def scrape(self, url: str) -> List[Dict]:
        """Navigate to *url* and dispatch to the site-specific extractor.

        Args:
            url: Landing / search-results page for the site.

        Returns:
            List of raw job dicts.
        """
        try:
            if self.config.get('type') == 'linkedin':
                source_mode = str(self.config.get('source_mode', 'hybrid')).lower().strip()
                if source_mode in {'rapidapi', 'hybrid'}:
                    logger.info(f"LinkedIn pre-navigation mode active: {source_mode}")
                    return self.extract_from_linkedin()

            logger.info(f"Loading {self.config['name']} job listing page...")
            nav_errors = []
            for wait_mode in ('networkidle', 'domcontentloaded'):
                try:
                    self.page.goto(url, wait_until=wait_mode, timeout=20000)
                    break
                except Exception as nav_err:
                    nav_errors.append(str(nav_err))
                    logger.warning(f"Navigation with {wait_mode} failed: {nav_err}")
            else:
                raise RuntimeError(f"Navigation failed for {self.config['name']}: {nav_errors}")

            method_name = f"extract_from_{self.config['type']}"
            if hasattr(self, method_name):
                return getattr(self, method_name)()
            else:
                logger.error(f"No extraction method for {self.config['type']}")
                return []
        except Exception as e:
            logger.error(f"Error scraping {self.config['name']}: {e}")
            raise

    def safe_extract(self, selector: str, default: str = '') -> str:
        """Safely extract the inner text of the first matching DOM element.

        Args:
            selector: CSS selector.
            default: Value to return when the selector matches nothing.

        Returns:
            Trimmed inner-text string or *default*.
        """
        try:
            element = self.page.query_selector(selector)
            if element:
                return element.inner_text().strip()
        except Exception:
            pass
        return default

    def extract_section_from_body(
        self,
        headings: List[str],
        window: int = 1800,
    ) -> str:
        """Extract a focused section from body text using heading keywords.

        The heading line itself is *excluded* from the returned text so that
        callers receive only the content that follows the heading.  Extraction
        stops at the next recognised section heading to avoid running into
        unrelated content.

        Args:
            headings: List of heading keywords to search for (case-insensitive).
            window: Maximum number of characters to return (safety cap).

        Returns:
            Extracted section text, or ``""`` when nothing is found.
        """
        try:
            body_text = self.page.locator('body').text_content() or ''
            if not body_text:
                return ''

            normalized = ' '.join(body_text.split())
            lower_text = normalized.lower()

            for heading in headings:
                idx = lower_text.find(heading.lower())
                if idx == -1:
                    continue

                # Skip past the heading itself
                content_start = idx + len(heading)
                # Skip any leading punctuation / whitespace after the heading
                while content_start < len(normalized) and normalized[content_start] in ' \t\n\r:.':
                    content_start += 1

                # Find the next section stop to avoid overrunning
                content_lower = lower_text[content_start:content_start + window]
                stop_idx = window
                for stop_heading in _SECTION_STOP_HEADINGS:
                    pos = content_lower.find(stop_heading)
                    if 0 < pos < stop_idx:
                        stop_idx = pos

                return normalized[content_start:content_start + stop_idx].strip()
        except Exception:
            pass

        return ''
