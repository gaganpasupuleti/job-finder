"""Generic career-site scraper."""

import logging
import time
from typing import Dict, List
from urllib.parse import unquote, urlparse

from scrapers.base import JobSiteScraper
from utils.experience import extract_years_of_experience
from utils.keywords import extract_essential_keywords
from utils.job_utils import compute_job_id
from utils.salary import extract_salary
from utils.work_mode import detect_work_mode
from utils.filters import DEFAULT_GENERIC_FILTERS

logger = logging.getLogger(__name__)


class GenericScraper(JobSiteScraper):
    """Generic extractor for external career sites loaded from files."""

    def extract_from_generic(self) -> List[Dict]:
        """Extract jobs from an arbitrary career site."""
        logger.info("Using generic extraction method")
        jobs_data: List[Dict] = []

        try:
            self.page.wait_for_timeout(2500)

            candidate_selectors = [
                'a[href*="/job"]',
                'a[href*="/jobs"]',
                'a[href*="/search"]',
                'a[href*="/careers"]',
                'a[href*="greenhouse.io"]',
                'a[href*="lever.co"]',
                'a[href*="workday"]',
            ]

            links: List[str] = []
            for selector in candidate_selectors:
                try:
                    extracted = self.page.eval_on_selector_all(
                        selector,
                        'elements => [...new Set(elements.map(e => e.href).filter(Boolean))]',
                    )
                    links.extend(extracted)
                except Exception:
                    continue

            unique_links: List[str] = []
            for link in links:
                if not isinstance(link, str):
                    continue
                normalized = link.strip()
                if not normalized.startswith('http'):
                    continue
                if normalized not in unique_links:
                    unique_links.append(normalized)

            logger.info(f"Found {len(unique_links)} generic job links")

            filters = self.config.get('filters')
            # Default to False — only infer filters when explicitly enabled
            if not filters and self.config.get('auto_analyze_filters', False):
                filters = self._infer_filters(unique_links)
                self.config['filters'] = filters
                self.config['inferred_filters'] = filters
                logger.info(
                    f"Inferred filters for {self.config.get('name', 'site')}: "
                    f"include={filters.get('include_patterns', [])}, "
                    f"exclude={filters.get('exclude_patterns', [])}, "
                    f"max_jobs={filters.get('max_jobs', 20)}"
                )

            filtered_links = self._apply_filters(unique_links, filters)
            logger.info(f"Filtered generic links: {len(filtered_links)} (from {len(unique_links)} candidates)")

            expanded_links = self._expand_listing_links(filtered_links)
            scrape_links = expanded_links if expanded_links else filtered_links
            if expanded_links:
                logger.info(f"Expanded to {len(expanded_links)} job-detail links from listing pages")

            for idx, link in enumerate(scrape_links, 1):
                try:
                    logger.info(f"Processing generic job {idx}/{len(scrape_links)}")
                    self.page.goto(link, wait_until='domcontentloaded', timeout=15000)
                    time.sleep(1)  # Politeness delay

                    title = self.safe_extract('h1', default='')
                    if not title:
                        page_title = self.page.title() or ''
                        title = page_title.split('|')[0].split('-')[0].strip()
                    if not title:
                        title = unquote(link.rstrip('/').split('/')[-1]).replace('-', ' ').strip()

                    location = self.safe_extract('[class*="location"], [data-testid*="location"]', default='')
                    posted = self.safe_extract('[class*="posted"], [class*="date"], time', default='')

                    min_req = self.extract_section_from_body([
                        'minimum qualifications',
                        'basic qualifications',
                        'requirements',
                        'must have',
                        'job qualifications',
                        'what you need',
                        'skills required',
                        'who you are',
                    ])

                    job_description = ''
                    try:
                        body_text = self.page.locator('body').text_content() or ''
                        job_description = ' '.join(body_text.split())[:800]
                    except Exception:
                        pass

                    combined = f"{min_req} {job_description}"
                    years_of_experience = extract_years_of_experience(combined, title)

                    jobs_data.append({
                        'Job ID': compute_job_id(link),
                        'Job Link': link,
                        'Title': title[:120] if title else '',
                        'Company': self.config.get('name', 'External Company').replace(' Careers', ''),
                        'Location': location[:150] if location else '',
                        'Posted': posted[:60] if posted else '',
                        'Minimum Requirements': min_req[:350] if min_req else '',
                        'Good to Have': '',
                        'Job Description': job_description,
                        'Years of Experience': years_of_experience,
                        'Essential Keywords': extract_essential_keywords(combined, title),
                        'Salary Range': extract_salary(combined),
                        'Work Mode': detect_work_mode(combined, location),
                        'Source': self.config.get('name', 'External Careers'),
                    })
                except Exception as e:
                    logger.error(f"Error extracting generic job {idx}: {str(e)[:100]}")

        except Exception as e:
            logger.error(f"Error in generic extraction: {e}")

        return jobs_data

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _infer_filters(self, links: List[str]) -> Dict:
        """Infer site-specific link filters from first-run link candidates."""
        include_hints = [
            '/job/', '/jobs/', '/job?', '/jobs?',
            '/search/', '/search?',
            'workdayjobs', 'greenhouse.io', 'lever.co', 'smartrecruiters', 'icims.com',
        ]
        include_patterns: List[str] = []
        links_lower = [link.lower() for link in links]
        for hint in include_hints:
            if any(hint in link for link in links_lower):
                include_patterns.append(hint)

        return {
            'include_patterns': include_patterns or DEFAULT_GENERIC_FILTERS['include_patterns'],
            'exclude_patterns': list(DEFAULT_GENERIC_FILTERS['exclude_patterns']),
            'title_must_contain': [],
            'max_jobs': DEFAULT_GENERIC_FILTERS['max_jobs'],
        }

    def _apply_filters(self, links: List[str], filters: Dict) -> List[str]:
        """Apply per-site include/exclude filters to candidate links."""
        if not links:
            return []

        effective = filters or DEFAULT_GENERIC_FILTERS
        include_patterns = [str(p).lower() for p in effective.get('include_patterns', []) if str(p).strip()]
        exclude_patterns = [str(p).lower() for p in effective.get('exclude_patterns', []) if str(p).strip()]
        try:
            max_jobs = int(effective.get('max_jobs', DEFAULT_GENERIC_FILTERS['max_jobs']))
        except Exception:
            max_jobs = DEFAULT_GENERIC_FILTERS['max_jobs']

        filtered: List[str] = []
        for link in links:
            lower_link = link.lower()
            if include_patterns and not any(p in lower_link for p in include_patterns):
                continue
            if exclude_patterns and any(p in lower_link for p in exclude_patterns):
                continue
            path = urlparse(link).path.strip().lower()
            if path in ('', '/', '/careers', '/jobs'):
                continue
            if link not in filtered:
                filtered.append(link)

        return filtered[:max_jobs]

    def _expand_listing_links(self, links: List[str]) -> List[str]:
        """Open listing/search links and extract concrete job-detail links."""
        if not links:
            return []

        listing_tokens = ['/search', '/jobs', '/careers', '/opportunities']
        job_tokens = ['/job/', '/jobs/view/', '/position/', '/requisition', 'greenhouse.io', 'lever.co']

        listing_links = [
            link for link in links
            if any(token in link.lower() for token in listing_tokens) and '/job/' not in link.lower()
        ][:5]

        expanded: List[str] = []
        for listing_link in listing_links:
            try:
                self.page.goto(listing_link, wait_until='domcontentloaded', timeout=15000)
                self.page.wait_for_timeout(2500)
                anchors = self.page.eval_on_selector_all(
                    'a[href]',
                    'els => [...new Set(els.map(e => e.href).filter(Boolean))]',
                )
                for anchor in anchors:
                    if not isinstance(anchor, str) or not anchor.startswith('http'):
                        continue
                    if any(token in anchor.lower() for token in job_tokens):
                        if anchor not in expanded:
                            expanded.append(anchor)
            except Exception:
                continue

        max_jobs = int((self.config.get('filters') or {}).get('max_jobs', DEFAULT_GENERIC_FILTERS['max_jobs']))
        return expanded[:max_jobs]
