"""Amazon Careers scraper."""

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


class AmazonScraper(JobSiteScraper):
    """Scraper for Amazon Careers (amazon.jobs)."""

    def extract_from_amazon(self) -> List[Dict]:
        """Extract jobs from Amazon Careers site."""
        logger.info("Using Amazon extraction method")
        jobs_data: List[Dict] = []

        try:
            # Check for unavailable page
            try:
                unavailable = self.page.locator("text=page you're looking for is not available").first
                if unavailable.is_visible(timeout=3000):
                    logger.warning("Amazon page unavailable (404)")
                    return []
            except Exception:
                pass

            try:
                self.page.wait_for_selector('a[href*="/jobs/"]', timeout=10000)
            except Exception:
                logger.warning("Amazon job links not found")
                return []

            job_elements = self.page.locator('a[href*="/jobs/"]').all()
            job_links = list(dict.fromkeys([elem.get_attribute('href') for elem in job_elements]))
            job_links = [link for link in job_links if link]
            logger.info(f"Found {len(job_links)} Amazon job links")

            if not job_links:
                logger.warning("Amazon returned zero job links")
                return []

            for idx, link in enumerate(job_links, 1):
                logger.info(f"Processing Amazon job {idx}/{len(job_links)}")
                try:
                    if not link.startswith('http'):
                        link = 'https://www.amazon.jobs' + link
                    self.page.goto(link, wait_until='domcontentloaded', timeout=15000)
                    time.sleep(1)  # Politeness delay

                    title = self.safe_extract('h1.title', default='') or self.safe_extract('h1', default='')

                    location_list = self.page.locator(
                        'ul.associations li.association-wrapper ul.association-content li'
                    ).all()
                    location = ', '.join([li.text_content().strip() for li in location_list]) if location_list else ''

                    posted = ''
                    try:
                        posted_elem = self.page.locator('span[data-testid="posted-date"]').first
                        if posted_elem:
                            posted_text = posted_elem.text_content()
                            posted = posted_text.replace('Posted:', '').split('(')[0].strip()
                    except Exception:
                        pass

                    min_req = ''
                    try:
                        next_p = self.page.locator('h2:has-text("Basic Qualifications") + p').first
                        if next_p:
                            min_req = next_p.text_content().strip()
                    except Exception:
                        pass

                    good_to_have = ''
                    try:
                        next_p = self.page.locator('h2:has-text("Preferred Qualifications") + p').first
                        if next_p:
                            good_to_have = next_p.text_content().strip()
                    except Exception:
                        pass

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
                            body_text = self.page.locator('body').text_content()
                            job_description = body_text[:500] if body_text else ''
                    except Exception:
                        pass

                    combined = f"{min_req} {good_to_have} {job_description}"
                    jobs_data.append({
                        'Job ID': compute_job_id(link),
                        'Job Link': link,
                        'Title': title,
                        'Company': 'Amazon',
                        'Location': location,
                        'Posted': posted,
                        'Minimum Requirements': min_req,
                        'Good to Have': good_to_have,
                        'Job Description': job_description[:500] if job_description else '',
                        'Years of Experience': extract_years_of_experience(combined, title),
                        'Essential Keywords': extract_essential_keywords(combined, title),
                        'Salary Range': extract_salary(combined),
                        'Work Mode': detect_work_mode(combined, location),
                        'Source': 'Amazon',
                    })
                except Exception as e:
                    logger.error(f"Error extracting Amazon job {idx}: {e}")

        except Exception as e:
            logger.error(f"Error in Amazon extraction: {e}")

        return jobs_data
