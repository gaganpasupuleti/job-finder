"""P&G Careers scraper."""

import logging
import time
from typing import Dict, List
from urllib.parse import unquote

from scrapers.base import JobSiteScraper
from utils.experience import extract_years_of_experience
from utils.keywords import extract_essential_keywords
from utils.job_utils import compute_job_id
from utils.salary import extract_salary
from utils.work_mode import detect_work_mode

logger = logging.getLogger(__name__)


class PGScraper(JobSiteScraper):
    """Scraper for P&G Careers (pgcareers.com)."""

    def extract_from_pg_careers(self) -> List[Dict]:
        """Extract jobs from P&G Careers site."""
        logger.info("Using P&G Careers extraction method")
        jobs_data: List[Dict] = []

        try:
            job_elements = self.page.locator('a[href*="/job/"]').all()
            logger.info(f"Found {len(job_elements)} P&G job links")

            unique_links = list(dict.fromkeys([
                elem.get_attribute('href') for elem in job_elements
            ]))
            unique_links = [link for link in unique_links if link and '/job/' in link]
            logger.info(f"Found {len(unique_links)} unique job links")

            for idx, link in enumerate(unique_links[:15], 1):
                try:
                    if not link.startswith('http'):
                        link = 'https://www.pgcareers.com' + link

                    logger.info(f"Processing P&G job {idx}/{len(unique_links)}: {link[:80]}")
                    self.page.goto(link, wait_until='domcontentloaded', timeout=15000)
                    time.sleep(1)  # Politeness delay
                    try:
                        self.page.wait_for_selector('h1, title, meta[property="og:title"]', timeout=5000)
                    except Exception:
                        pass

                    title = self.safe_extract('h1', default='')
                    if not title:
                        title = self.safe_extract('[class*="title"]', default='')
                    if not title:
                        title = self.page.eval_on_selector('meta[property="og:title"]', 'el => el.content') or ''
                    if not title:
                        title = self.page.title() or ''
                    if title:
                        title = title.split('|')[0].split('- P&G Careers')[0].strip()
                    if not title:
                        slug = unquote(link.rstrip('/').split('/')[-1])
                        title = slug.replace('-', ' ').strip()

                    location = self.safe_extract('[class*="location"]', default='')
                    posted = self.safe_extract('[class*="posted"], [class*="date"]', default='')

                    min_req = self.safe_extract('[class*="requirement"], [class*="qualification"]', default='')
                    if not min_req:
                        min_req = self.extract_section_from_body([
                            'job qualifications',
                            'qualifications',
                            'must have',
                            'what we are looking for',
                            'requirements',
                            'minimum qualifications',
                        ])
                    if not min_req:
                        try:
                            page_text = self.page.locator('body').text_content()[:500]
                            min_req = page_text if page_text else ''
                        except Exception:
                            min_req = ''

                    good_to_have = self.extract_section_from_body([
                        'preferred qualifications',
                        'nice to have',
                        'good to have',
                    ])

                    job_description = ''
                    try:
                        desc_heading = self.page.locator(
                            'h2:has-text("Job Description"), h2:has-text("Description"), h3:has-text("Job Description")'
                        ).first
                        if desc_heading:
                            next_elem = desc_heading.evaluate(
                                '(el) => el.nextElementSibling?.textContent || ""'
                            )
                            job_description = next_elem.strip() if next_elem else ''
                        if not job_description:
                            page_text = self.page.locator('body').text_content()
                            job_description = page_text[:500] if page_text else ''
                    except Exception:
                        pass

                    combined = f"{min_req} {job_description}"
                    years_of_experience = extract_years_of_experience(combined, title)

                    jobs_data.append({
                        'Job ID': compute_job_id(link),
                        'Job Link': link,
                        'Title': title[:100] if title else '',
                        'Company': 'P&G',
                        'Location': location[:150] if location else '',
                        'Posted': posted[:50] if posted else '',
                        'Minimum Requirements': min_req[:300] if min_req else '',
                        'Good to Have': good_to_have[:300] if good_to_have else '',
                        'Job Description': job_description[:500] if job_description else '',
                        'Years of Experience': years_of_experience,
                        'Essential Keywords': extract_essential_keywords(combined, title),
                        'Salary Range': extract_salary(combined),
                        'Work Mode': detect_work_mode(combined, location),
                        'Source': 'P&G Careers',
                    })

                except Exception as e:
                    logger.error(f"Error extracting P&G job {idx}: {str(e)[:100]}")

        except Exception as e:
            logger.error(f"Error in P&G extraction: {e}")

        return jobs_data
