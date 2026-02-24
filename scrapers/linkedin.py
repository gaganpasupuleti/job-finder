"""LinkedIn Jobs scraper."""

import logging
import time
from typing import Dict, List

from scrapers.base import JobSiteScraper
from utils.experience import extract_years_of_experience
from utils.keywords import extract_essential_keywords
from utils.job_utils import compute_job_id
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

    def extract_from_linkedin(self) -> List[Dict]:
        """Extract jobs from LinkedIn job search pages."""
        logger.info("Using LinkedIn extraction method")
        jobs_data: List[Dict] = []
        max_jobs = int(self.config.get('max_jobs', 50))

        # --- CAPTCHA / login wall detection ---
        try:
            page_title = (self.page.title() or '').strip().lower()
            body_text = (self.page.locator('body').text_content() or '').lower()
            if page_title in _INVALID_TITLES or any(
                phrase in body_text for phrase in _LOGIN_WALL_PHRASES
            ):
                logger.warning(
                    "LinkedIn login/CAPTCHA wall detected. "
                    "To scrape LinkedIn you must authenticate first:\n"
                    "  1. Run: python main.py --save-linkedin\n"
                    "  2. Then re-run with: python main.py --enable-linkedin "
                    "--linkedin-storage-state linkedin_state.json"
                )
                return []
        except Exception:
            pass

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
                    self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                except Exception:
                    pass

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

                self.page.wait_for_timeout(1200)

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
                logger.warning("LinkedIn job list not visible yet")

            job_links = _collect_links(max_jobs)
            logger.info(f"Found {len(job_links)} LinkedIn job links")

            if not job_links:
                logger.warning("No LinkedIn job links found on page")
                return []

            for idx, link in enumerate(job_links[:max_jobs], 1):
                logger.info(f"Processing LinkedIn job {idx}/{min(len(job_links), max_jobs)}")
                try:
                    self.page.goto(link, wait_until='domcontentloaded', timeout=15000)
                    time.sleep(1)  # Politeness delay

                    title = self.safe_extract(
                        'h1.jobs-unified-top-card__job-title, h1.topcard__title', default=''
                    )
                    if not title:
                        title = (self.page.title() or '').split('|')[0].strip()

                    # Login wall check per-page
                    if not title or title.strip().lower() in _INVALID_TITLES:
                        logger.warning(
                            "LinkedIn login wall detected on job page. "
                            "Authenticate first with --save-linkedin."
                        )
                        continue

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
                            job_description = desc.text_content().strip()
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

                    combined = f"{min_req} {job_description}"
                    years_of_experience = extract_years_of_experience(combined, title)

                    jobs_data.append({
                        'Job ID': compute_job_id(link),
                        'Job Link': link,
                        'Title': title,
                        'Company': company,
                        'Location': location,
                        'Posted': posted,
                        'Minimum Requirements': min_req[:350] if min_req else '',
                        'Good to Have': '',
                        'Job Description': job_description[:1000] if job_description else '',
                        'Years of Experience': years_of_experience,
                        'Essential Keywords': extract_essential_keywords(job_description, title),
                        'Salary Range': extract_salary(combined),
                        'Work Mode': detect_work_mode(combined, location),
                        'Source': 'LinkedIn',
                    })
                except Exception as e:
                    logger.error(f"Error extracting LinkedIn job {idx}: {e}")

        except Exception as e:
            logger.error(f"Error in LinkedIn extraction: {e}")

        return jobs_data
