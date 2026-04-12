"""LinkedIn Jobs scraper."""

import logging
import os
import random
from typing import Dict, List
from urllib.parse import urlencode

import requests

from scrapers.base import JobSiteScraper
from utils.experience import extract_years_of_experience
from utils.keywords import extract_essential_keywords, build_boolean_query_from_user_input
from utils.job_utils import compute_job_id, JOB_SCHEMA
from utils.salary import extract_salary
from utils.work_mode import detect_work_mode

logger = logging.getLogger(__name__)

# Titles that indicate the user hit a login/CAPTCHA wall
_INVALID_TITLES = {
    'sign up', 'join now', 'log in', 'linkedin', 'linkedin login',
    'linkedin: log in or sign up',
}

# Phrases in page text that indicate a login wall
_LOGIN_WALL_PHRASES = [
    'join linkedin', 'sign in to linkedin', 'create your free account',
    'see who you know', 'sign up and see',
]


class LinkedInScraper(JobSiteScraper):
    """Scraper for LinkedIn job search pages."""

    def _to_standard_schema(
        self,
        *,
        link: str,
        title: str,
        company: str,
        location: str,
        posted: str,
        minimum_requirements: str,
        job_description: str,
    ) -> Dict:
        combined = f"{minimum_requirements} {job_description}".strip()
        job_id_source = link or f"{title}|{company}|{location}|{posted}"
        row = {key: '' for key in JOB_SCHEMA}
        row.update({
            'Job ID': compute_job_id(job_id_source),
            'Job Link': str(link or '').strip(),
            'Title': str(title or '').strip(),
            'Company': str(company or '').strip(),
            'Location': str(location or '').strip(),
            'Posted': str(posted or '').strip(),
            'Minimum Requirements': str(minimum_requirements or '').strip()[:350],
            'Good to Have': '',
            'Job Description': str(job_description or '').strip()[:1000],
            'Years of Experience': extract_years_of_experience(combined, title),
            'Essential Keywords': extract_essential_keywords(job_description, title),
            'Salary Range': extract_salary(combined),
            'Work Mode': detect_work_mode(combined, location),
            'Source': 'LinkedIn',
        })
        return row

    def _is_login_wall(self) -> bool:
        try:
            page_title = (self.page.title() or '').strip().lower()
            body_text = (self.page.locator('body').text_content() or '').lower()
            return page_title in _INVALID_TITLES or any(
                phrase in body_text for phrase in _LOGIN_WALL_PHRASES
            )
        except Exception:
            return False

    def _refresh_storage_state_from_env(self, output_path: str) -> bool:
        user = os.getenv('LINKEDIN_USER')
        pwd = os.getenv('LINKEDIN_PASS')
        if not user or not pwd:
            logger.warning(
                'Login wall detected but LINKEDIN_USER / LINKEDIN_PASS are not set; '
                'cannot auto-refresh storage state.'
            )
            return False

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False, slow_mo=120)
                context = browser.new_context()
                page = context.new_page()
                try:
                    from playwright_stealth import stealth_sync
                    stealth_sync(page)
                except Exception:
                    pass
                page.goto('https://www.linkedin.com/login', wait_until='domcontentloaded')
                page.fill('input[name="session_key"]', user)
                page.fill('input[name="session_password"]', pwd)
                page.click('button[type="submit"]')
                page.wait_for_timeout(random.randint(2000, 5000))
                context.storage_state(path=output_path)
                browser.close()
            logger.info(f"Refreshed LinkedIn storage_state at {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to auto-refresh LinkedIn storage state: {e}")
            return False

    def _human_pause(self, low_ms: int = 250, high_ms: int = 1000) -> None:
        self.page.wait_for_timeout(random.randint(low_ms, high_ms))

    def _human_like_scroll_and_mouse(self) -> None:
        try:
            width = self.page.viewport_size.get('width', 1200) if self.page.viewport_size else 1200
            height = self.page.viewport_size.get('height', 800) if self.page.viewport_size else 800
            start_x = random.randint(50, max(60, width - 50))
            start_y = random.randint(50, max(60, height - 50))
            self.page.mouse.move(start_x, start_y, steps=random.randint(6, 15))
            for _ in range(random.randint(2, 5)):
                dx = random.randint(-120, 120)
                dy = random.randint(-80, 80)
                jitter_x = max(1, min(width - 1, start_x + dx))
                jitter_y = max(1, min(height - 1, start_y + dy))
                self.page.mouse.move(jitter_x, jitter_y, steps=random.randint(4, 12))
                start_x, start_y = jitter_x, jitter_y
                self._human_pause(80, 220)
        except Exception:
            pass

    def _extract_jobs_list_from_api_response(self, payload: object) -> List[Dict]:
        """Best-effort extraction of jobs list from variable API response shapes."""
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if not isinstance(payload, dict):
            return []

        candidate_keys = [
            'data', 'jobs', 'results', 'response', 'items',
            'job_postings', 'jobPosts', 'jobPostings',
        ]

        for key in candidate_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = self._extract_jobs_list_from_api_response(value)
                if nested:
                    return nested

        # Fallback: first list-of-dicts value found anywhere at root.
        for value in payload.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value

        return []

    def _map_api_job_to_schema(self, raw: Dict) -> Dict:
        """Map API job object to internal output schema."""
        link = str(
            raw.get('job_url')
            or raw.get('jobUrl')
            or raw.get('url')
            or raw.get('link')
            or raw.get('applyUrl')
            or ''
        ).strip()

        title = str(
            raw.get('title')
            or raw.get('job_title')
            or raw.get('jobTitle')
            or raw.get('position')
            or ''
        ).strip()

        company = str(
            raw.get('company')
            or raw.get('company_name')
            or raw.get('companyName')
            or ''
        ).strip()

        location = str(
            raw.get('location')
            or raw.get('job_location')
            or raw.get('jobLocation')
            or ''
        ).strip()

        posted = str(
            raw.get('posted')
            or raw.get('posted_at')
            or raw.get('postedAt')
            or raw.get('date_posted')
            or raw.get('datePosted')
            or ''
        ).strip()

        description = str(
            raw.get('description')
            or raw.get('job_description')
            or raw.get('jobDescription')
            or raw.get('summary')
            or ''
        ).strip()

        min_req = str(
            raw.get('minimum_requirements')
            or raw.get('minimumRequirements')
            or raw.get('requirements')
            or ''
        ).strip()

        return self._to_standard_schema(
            link=link,
            title=title,
            company=company,
            location=location,
            posted=posted,
            minimum_requirements=min_req,
            job_description=description,
        )

    def extract_from_linkedin_rapidapi(self) -> List[Dict]:
        """Extract jobs using a RapidAPI LinkedIn endpoint."""
        api_key = os.getenv('RAPIDAPI_KEY')
        api_host = os.getenv('RAPIDAPI_HOST', 'linkedin-data-api.p.rapidapi.com')
        endpoint = os.getenv('RAPIDAPI_LINKEDIN_ENDPOINT', 'https://linkedin-data-api.p.rapidapi.com/search-jobs')
        method = os.getenv('RAPIDAPI_LINKEDIN_METHOD', 'GET').upper().strip()
        api_pages = max(1, int(self.config.get('api_pages', 1)))
        max_jobs = int(self.config.get('max_jobs', 50))

        self.config['_api_low_credits'] = False
        self.config['_api_failed'] = False

        if not api_key:
            logger.warning('RAPIDAPI_KEY missing. API-first mode will fall back to browser.')
            self.config['_api_failed'] = True
            return []

        headers = {
            'x-rapidapi-key': api_key,
            'x-rapidapi-host': api_host,
            'Content-Type': 'application/json',
        }

        raw_keywords = str(self.config.get('keywords', 'software engineer'))
        keywords = build_boolean_query_from_user_input(raw_keywords) or raw_keywords
        location = str(self.config.get('location', 'India'))

        # Credit conservation: use one API request with a combined boolean query.
        api_pages = 1

        jobs: List[Dict] = []
        seen_ids = set()
        min_credits = max(0, int(os.getenv('RAPIDAPI_MIN_CREDITS', '5')))
        received_any_payload = False

        for page in range(1, api_pages + 1):
            params = {
                'keywords': keywords,
                'location': location,
                'page': page,
            }

            try:
                if method == 'POST':
                    response = requests.post(endpoint, headers=headers, json=params, timeout=45)
                else:
                    query = urlencode(params)
                    response = requests.get(f"{endpoint}?{query}", headers=headers, timeout=45)

                if response.status_code >= 400:
                    logger.error(
                        f"RapidAPI request failed (page={page}, status={response.status_code}): "
                        f"{response.text[:400]}"
                    )
                    if response.status_code == 429:
                        self.config['_api_low_credits'] = True
                    continue

                remaining = (
                    response.headers.get('x-ratelimit-requests-remaining')
                    or response.headers.get('X-RateLimit-Requests-Remaining')
                    or response.headers.get('x-ratelimit-remaining')
                    or response.headers.get('X-RateLimit-Remaining')
                )
                if remaining and str(remaining).isdigit() and int(remaining) <= min_credits:
                    self.config['_api_low_credits'] = True

                payload = response.json()
                raw_jobs = self._extract_jobs_list_from_api_response(payload)
                logger.info(f"RapidAPI page {page}: received {len(raw_jobs)} raw jobs")
                received_any_payload = True

                if not raw_jobs:
                    # Stop paging when endpoint returns no more data.
                    break

                for raw in raw_jobs:
                    mapped = self._map_api_job_to_schema(raw)
                    job_id = mapped.get('Job ID', '')
                    if not mapped.get('Title') or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    jobs.append(mapped)
                    if len(jobs) >= max_jobs:
                        return jobs

            except Exception as e:
                logger.error(f"RapidAPI LinkedIn extraction error on page {page}: {e}")

        if not jobs and not received_any_payload:
            self.config['_api_failed'] = True

        return jobs

    def _extract_from_linkedin_browser(self) -> List[Dict]:
        jobs_data: List[Dict] = []
        max_jobs = int(self.config.get('max_jobs', 50))
        search_url = self.config.get('url')
        storage_state_path = str(self.config.get('storage_state', 'linkedin_state.json'))

        if search_url:
            nav_errors = []
            for wait_mode in ('networkidle', 'domcontentloaded'):
                try:
                    self.page.goto(search_url, wait_until=wait_mode, timeout=22000)
                    break
                except Exception as nav_err:
                    nav_errors.append(str(nav_err))
            else:
                raise RuntimeError(f"LinkedIn navigation failed: {nav_errors}")

        if self._is_login_wall():
            logger.warning('LinkedIn login wall detected. Attempting session refresh...')
            if self._refresh_storage_state_from_env(storage_state_path):
                self.close_browser()
                self.start_browser(
                    headless=bool(getattr(self, '_runtime_headless', True)),
                    storage_state=storage_state_path,
                )
                if search_url:
                    self.page.goto(search_url, wait_until='domcontentloaded', timeout=22000)

        if self._is_login_wall():
            logger.warning(
                'LinkedIn login/CAPTCHA wall still present after refresh. '
                'Try running with --headful or --save-linkedin.'
            )
            raise RuntimeError('captcha/login wall detected on LinkedIn')

        def _normalize_link(link: str) -> str:
            if not link:
                return ''
            value = link.strip()
            if value.startswith('/'):
                value = 'https://www.linkedin.com' + value
            if '/jobs/view/' not in value:
                return ''
            return value.split('?')[0]

        def _collect_links(target_count: int) -> List[str]:
            selectors = [
                'a.job-card-container__link',
                'a.base-card__full-link',
                'a[href*="/jobs/view/"]',
            ]
            collected: List[str] = []
            stagnant_rounds = 0
            max_rounds = max(8, min(30, target_count // 5 + 8))

            for _ in range(max_rounds):
                before_count = len(collected)
                for selector in selectors:
                    try:
                        extracted = self.page.eval_on_selector_all(
                            selector,
                            'elements => [...new Set(elements.map(e => e.href || e.getAttribute("href") || "").filter(Boolean))]',
                        )
                        for link in extracted:
                            normalized = _normalize_link(str(link))
                            if normalized and normalized not in collected:
                                collected.append(normalized)
                    except Exception:
                        continue

                if len(collected) >= target_count:
                    break

                try:
                    scroll_by = random.randint(300, 1400)
                    self.page.evaluate('(distance) => window.scrollBy({ top: distance, behavior: "smooth" })', scroll_by)
                except Exception:
                    pass
                self._human_like_scroll_and_mouse()

                try:
                    btn = self.page.locator(
                        'button.infinite-scroller__show-more-button, '
                        'button:has-text("See more jobs"), '
                        'button[aria-label*="See more jobs"]'
                    ).first
                    if btn and btn.is_visible(timeout=1500):
                        btn.click(timeout=3000)
                except Exception:
                    pass

                self._human_pause(800, 1700)

                if len(collected) == before_count:
                    stagnant_rounds += 1
                else:
                    stagnant_rounds = 0

                if stagnant_rounds >= 4:
                    break

            return collected[:target_count]

        try:
            try:
                self.page.wait_for_selector(
                    'ul.jobs-search__results-list, .jobs-search-results__list, '
                    'div.jobs-search-results-list, a[href*="/jobs/view/"]',
                    timeout=12000,
                )
            except Exception:
                logger.warning('LinkedIn job list not visible yet')

            job_links = _collect_links(max_jobs)
            logger.info(f"Found {len(job_links)} LinkedIn job links")

            if not job_links:
                logger.warning('No LinkedIn job links found on page')
                return []

            for idx, link in enumerate(job_links[:max_jobs], 1):
                logger.info(f"Processing LinkedIn job {idx}/{min(len(job_links), max_jobs)}")
                try:
                    self.page.goto(link, wait_until='domcontentloaded', timeout=15000)
                    self._human_pause(550, 1350)
                    self._human_like_scroll_and_mouse()

                    title = self.safe_extract(
                        'h1.jobs-unified-top-card__job-title, h1.topcard__title', default=''
                    )
                    if not title:
                        title = (self.page.title() or '').split('|')[0].strip()

                    if not title or title.strip().lower() in _INVALID_TITLES:
                        logger.warning('LinkedIn login wall detected on job page.')
                        raise RuntimeError('captcha/login wall detected on LinkedIn job page')

                    company = self.safe_extract(
                        'a.jobs-unified-top-card__company-name, '
                        'a.topcard__org-name-link, '
                        'span.jobs-unified-top-card__company-name',
                        default='',
                    )
                    if not company:
                        company = self.safe_extract(
                            'span.topcard__flavor, '
                            'div.job-details-jobs-unified-top-card__company-name',
                            default='',
                        )

                    location = self.safe_extract(
                        'span.jobs-unified-top-card__company-location, '
                        'span.topcard__flavor--bullet, '
                        'span.jobs-unified-top-card__bullet',
                        default='',
                    )
                    posted = self.safe_extract(
                        'span.posted-time-ago__text, span.jobs-unified-top-card__posted-date',
                        default='',
                    )

                    job_description = ''
                    try:
                        desc = self.page.locator(
                            'div.description__text, '
                            'div.jobs-description-content__text, '
                            'div.show-more-less-html__markup'
                        ).first
                        if desc:
                            job_description = (desc.text_content() or '').strip()
                    except Exception:
                        pass
                    if not job_description:
                        try:
                            body_text = self.page.locator('body').text_content() or ''
                            job_description = ' '.join(body_text.split())[:1200]
                        except Exception:
                            pass

                    min_req = self.extract_section_from_body([
                        'minimum qualifications',
                        'basic qualifications',
                        'requirements',
                        'what you will need',
                        'must have',
                        'what you need',
                        'who you are',
                        "what we're looking for",
                    ], window=1200)

                    jobs_data.append(self._to_standard_schema(
                        link=link,
                        title=title,
                        company=company,
                        location=location,
                        posted=posted,
                        minimum_requirements=min_req,
                        job_description=job_description,
                    ))
                except Exception as e:
                    logger.error(f"Error extracting LinkedIn job {idx}: {e}")

        except Exception as e:
            logger.error(f"Error in LinkedIn browser extraction: {e}")
            raise

        return jobs_data

    def extract_from_linkedin(self) -> List[Dict]:
        """Extract jobs from LinkedIn job search pages."""
        source_mode = str(self.config.get('source_mode', 'hybrid')).lower().strip()
        if source_mode == 'rapidapi':
            logger.info('Using LinkedIn RapidAPI extraction mode')
            return self.extract_from_linkedin_rapidapi()

        if source_mode == 'hybrid':
            logger.info('Using LinkedIn hybrid mode (API first, browser fallback)')
            api_jobs = self.extract_from_linkedin_rapidapi()
            if api_jobs:
                return api_jobs
            if self.config.get('_api_low_credits'):
                logger.warning('RapidAPI credits low. Switching to browser mode.')
            else:
                logger.warning('RapidAPI returned no usable jobs. Switching to browser mode.')

        logger.info('Using LinkedIn browser extraction mode')
        return self._extract_from_linkedin_browser()
