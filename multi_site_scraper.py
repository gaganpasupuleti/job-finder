from playwright.sync_api import sync_playwright
import pandas as pd
import logging
import time
import json
import hashlib
import os
from pathlib import Path
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def retry(max_attempts: int = 3, delay: float = 1.0):
    """Retry decorator for functions that may fail temporarily"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts:
                        logger.error(f"Failed after {max_attempts} attempts: {e}")
                        raise
                    logger.warning(f"Attempt {attempt} failed: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
        return wrapper
    return decorator

class JobSiteScraper:
    """Generic job scraper that can handle multiple job websites"""
    
    def __init__(self, site_config: Dict):
        self.config = site_config
        self.browser = None
        self.context = None
        self.page = None
    
    def start_browser(self, headless=True, storage_state: Optional[str] = None):
        """Start Playwright browser (optionally load storage_state for authenticated sessions)"""
        from playwright.sync_api import sync_playwright
        self.p = sync_playwright().start()
        self.browser = self.p.chromium.launch(headless=headless)
        context_kwargs = {
            "user_agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        if storage_state:
            context_kwargs["storage_state"] = storage_state
        self.context = self.browser.new_context(**context_kwargs)
        self.page = self.context.new_page()
        logger.info(f"Browser started for {self.config['name']} (storage_state={'present' if storage_state else 'none'})")
    
    def close_browser(self):
        """Close browser"""
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.p:
            self.p.stop()
    
    @retry(max_attempts=3, delay=2.0)
    def scrape(self, url: str) -> List[Dict]:
        """Main scraping method"""
        try:
            logger.info(f"Loading {self.config['name']} job listing page...")
            nav_errors = []
            for wait_mode in ("networkidle", "domcontentloaded"):
                try:
                    self.page.goto(url, wait_until=wait_mode, timeout=20000)
                    break
                except Exception as nav_err:
                    nav_errors.append(str(nav_err))
                    logger.warning(f"Navigation with {wait_mode} failed: {nav_err}")
            else:
                raise RuntimeError(f"Navigation failed for {self.config['name']}: {nav_errors}")
            
            # Try site-specific extraction
            method_name = f"extract_from_{self.config['type']}"
            if hasattr(self, method_name):
                method = getattr(self, method_name)
                return method()
            else:
                logger.error(f"No extraction method for {self.config['type']}")
                return []
        except Exception as e:
            logger.error(f"Error scraping {self.config['name']}: {e}")
            raise
    
    @retry(max_attempts=2, delay=3.0)
    def extract_from_amazon(self) -> List[Dict]:
        """Extract jobs from Amazon Careers site"""
        logger.info("Using Amazon extraction method")
        jobs_data = []
        
        try:
            # Check for unavailable page
            try:
                unavailable = self.page.locator("text=page you're looking for is not available").first
                if unavailable.is_visible(timeout=3000):
                    logger.warning("Amazon page unavailable (404)")
                    return []
            except Exception:
                pass

            # Wait for job links to appear
            try:
                self.page.wait_for_selector('a[href*="/jobs/"]', timeout=10000)
            except Exception:
                logger.warning("Amazon job links not found")
                return []

            job_elements = self.page.locator('a[href*="/jobs/"]').all()
            job_links = list(dict.fromkeys([elem.get_attribute('href') for elem in job_elements]))
            job_links = [link for link in job_links if link]  # Filter None values
            logger.info(f"Found {len(job_links)} Amazon job links")

            if not job_links:
                logger.warning("Amazon returned zero job links")
                return []
            
            for idx, link in enumerate(job_links, 1):
                logger.info(f"Processing Amazon job {idx}/{len(job_links)}")
                try:
                    if not link.startswith("http"):
                        link = "https://www.amazon.jobs" + link
                    self.page.goto(link, wait_until="domcontentloaded", timeout=15000)
                    
                    title = self.safe_extract('h1.title', default='')
                    if not title:
                        title = self.safe_extract('h1', default='')
                    
                    location_list = self.page.locator('ul.associations li.association-wrapper ul.association-content li').all()
                    location = ', '.join([li.text_content().strip() for li in location_list]) if location_list else ''
                    
                    posted = ''
                    try:
                        posted_elem = self.page.locator('span[data-testid="posted-date"]').first
                        if posted_elem:
                            posted_text = posted_elem.text_content()
                            posted = posted_text.replace('Posted:', '').split('(')[0].strip()
                    except:
                        pass
                    
                    min_req = ''
                    try:
                        next_p = self.page.locator('h2:has-text("Basic Qualifications") + p').first
                        if next_p:
                            min_req = next_p.text_content().strip()
                    except:
                        pass
                    
                    good_to_have = ''
                    try:
                        next_p = self.page.locator('h2:has-text("Preferred Qualifications") + p').first
                        if next_p:
                            good_to_have = next_p.text_content().strip()
                    except:
                        pass
                    
                    job_description = ''
                    try:
                        desc_heading = self.page.locator('h2:has-text("Job Description"), h2:has-text("Description"), h3:has-text("Job Description")').first
                        if desc_heading:
                            # Get the next paragraph or div with content
                            next_elem = desc_heading.evaluate('(el) => el.nextElementSibling?.textContent || ""')
                            job_description = next_elem.strip() if next_elem else ''
                        if not job_description:
                            # Fallback: grab body text
                            body_text = self.page.locator('body').text_content()
                            job_description = body_text[:500] if body_text else ''
                    except:
                        pass
                    
                    jobs_data.append({
                        'Job ID': compute_job_id(link),
                        'Job Link': link,
                        'Title': title,
                        'Location': location,
                        'Posted': posted,
                        'Minimum Requirements': min_req,
                        'Good to Have': good_to_have,
                        'Job Description': job_description[:500] if job_description else '',
                        'Source': 'Amazon'
                    })
                except Exception as e:
                    logger.error(f"Error extracting Amazon job {idx}: {e}")
        
        except Exception as e:
            logger.error(f"Error in Amazon extraction: {e}")
        
        return jobs_data
    
    @retry(max_attempts=2, delay=3.0)
    def extract_from_pg_careers(self) -> List[Dict]:
        """Extract jobs from P&G Careers site"""
        logger.info("Using P&G Careers extraction method")
        jobs_data = []
        
        try:
            # Look for job links
            job_elements = self.page.locator('a[href*="/job/"]').all()
            logger.info(f"Found {len(job_elements)} P&G job links")
            
            # Get unique links
            unique_links = list(dict.fromkeys([
                elem.get_attribute('href') for elem in job_elements
            ]))
            unique_links = [link for link in unique_links if link and '/job/' in link]
            
            logger.info(f"Found {len(unique_links)} unique job links")
            
            for idx, link in enumerate(unique_links[:15], 1):  # Process up to 15 jobs
                try:
                    # Make absolute URL
                    if not link.startswith('http'):
                        link = 'https://www.pgcareers.com' + link
                    
                    logger.info(f"Processing P&G job {idx}/{len(unique_links)}: {link[:80]}")
                    
                    # Navigate to job page
                    self.page.goto(link, wait_until="domcontentloaded", timeout=15000)
                    
                    # Extract from job detail page
                    title = self.safe_extract('h1', default='')
                    if not title:
                        title = self.safe_extract('[class*="title"]', default='')
                    
                    location = self.safe_extract('[class*="location"]', default='')
                    posted = self.safe_extract('[class*="posted"], [class*="date"]', default='')
                    
                    # Try to get requirements
                    min_req = self.safe_extract('[class*="requirement"], [class*="qualification"]', default='')
                    
                    # Get full page text as fallback
                    if not min_req:
                        try:
                            page_text = self.page.locator('body').text_content()[:500]
                            min_req = page_text if page_text else ''
                        except:
                            min_req = ''
                    
                    good_to_have = ''
                    
                    # Extract Job Description
                    job_description = ''
                    try:
                        desc_heading = self.page.locator('h2:has-text("Job Description"), h2:has-text("Description"), h3:has-text("Job Description")').first
                        if desc_heading:
                            # Get the next sibling element content
                            next_elem = desc_heading.evaluate('(el) => el.nextElementSibling?.textContent || ""')
                            job_description = next_elem.strip() if next_elem else ''
                        if not job_description:
                            page_text = self.page.locator('body').text_content()
                            job_description = page_text[:500] if page_text else ''
                    except:
                        pass
                    
                    jobs_data.append({
                        'Job ID': compute_job_id(link),
                        'Job Link': link,
                        'Title': title[:100] if title else '',
                        'Location': location[:150] if location else '',
                        'Posted': posted[:50] if posted else '',
                        'Minimum Requirements': min_req[:300] if min_req else '',
                        'Good to Have': good_to_have,
                        'Job Description': job_description[:500] if job_description else '',
                        'Source': 'P&G Careers'
                    })
                    
                except Exception as e:
                    logger.error(f"Error extracting P&G job {idx}: {str(e)[:100]}")
        
        except Exception as e:
            logger.error(f"Error in P&G extraction: {e}")
        
        return jobs_data

    @retry(max_attempts=2, delay=3.0)
    def extract_from_linkedin(self) -> List[Dict]:
        """Extract jobs from LinkedIn job search pages"""
        logger.info("Using LinkedIn extraction method")
        jobs_data = []
        try:
            # Wait for job listing container
            try:
                self.page.wait_for_selector('ul.jobs-search__results-list, .jobs-search-results__list, div.jobs-search-results-list', timeout=10000)
            except Exception:
                logger.warning("LinkedIn job list not visible yet")

            # Collect job links (common LinkedIn job URL patterns)
            job_links = self.page.eval_on_selector_all(
                'a[href*="/jobs/view/"], a[href*="/jobs/"]',
                'elements => [...new Set(elements.map(e => e.href))]'
            )
            logger.info(f"Found {len(job_links)} LinkedIn job links")

            if not job_links:
                logger.warning("No LinkedIn job links found on page")
                return []

            # Limit to first 50 to avoid long runs
            for idx, link in enumerate(job_links[:50], 1):
                logger.info(f"Processing LinkedIn job {idx}/{min(len(job_links),50)}")
                try:
                    self.page.goto(link, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(1)

                    title = self.safe_extract('h1.jobs-unified-top-card__job-title, h1.topcard__title', default='')
                    company = self.safe_extract('a.jobs-unified-top-card__company-name, a.topcard__org-name-link, span.jobs-unified-top-card__company-name', default='')
                    location = self.safe_extract('span.jobs-unified-top-card__company-location, span.topcard__flavor--bullet, span.jobs-unified-top-card__bullet', default='')
                    posted = self.safe_extract('span.posted-time-ago__text, span.jobs-unified-top-card__posted-date', default='')

                    job_description = ''
                    try:
                        desc = self.page.locator('div.description__text, div.jobs-description-content__text, div.show-more-less-html__markup').first
                        if desc:
                            job_description = desc.text_content().strip()
                    except:
                        pass

                    jobs_data.append({
                        'Job ID': compute_job_id(link),
                        'Job Link': link,
                        'Title': title,
                        'Company': company,
                        'Location': location,
                        'Posted': posted,
                        'Minimum Requirements': '',
                        'Good to Have': '',
                        'Job Description': job_description[:1000] if job_description else '',
                        'Source': 'LinkedIn'
                    })
                except Exception as e:
                    logger.error(f"Error extracting LinkedIn job {idx}: {e}")
        except Exception as e:
            logger.error(f"Error in LinkedIn extraction: {e}")
        return jobs_data
    
    def safe_extract(self, selector: str, default: str = '') -> str:
        """Safely extract text from selector"""
        try:
            element = self.page.query_selector(selector)
            if element:
                return element.inner_text().strip()
        except:
            pass
        return default


def compute_job_id(link: str) -> str:
    """Stable unique ID derived from job link"""
    return hashlib.sha1(link.encode('utf-8')).hexdigest()

def validate_job_data(job: Dict) -> bool:
    """Validate job data has minimum required fields"""
    required_fields = ['Job ID', 'Job Link', 'Title']
    return all(job.get(field, '').strip() for field in required_fields)

def get_supabase_client() -> Optional[object]:
    """Initialize Supabase client from env vars. Returns None if not configured."""
    if not SUPABASE_AVAILABLE:
        logger.warning("supabase not installed; skipping DB sync. Install with: pip install supabase")
        return None
    
    # Load from .env file if available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')
    
    if not url or not key:
        logger.warning("SUPABASE_URL or SUPABASE_KEY env var not set; skipping DB sync. Set them in .env file or environment.")
        return None
    
    try:
        client = create_client(url, key)
        logger.info(f"Supabase client initialized for {url}")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        return None


def save_linkedin_storage_state(output_path: str = 'linkedin_state.json') -> bool:
    """Interactive helper: log in to LinkedIn (reads LINKEDIN_USER/LINKEDIN_PASS env vars) and save Playwright storage_state.

    Use this once to create `linkedin_state.json`, then reference that path in the site config as `storage_state`.
    """
    user = os.getenv('LINKEDIN_USER')
    pwd = os.getenv('LINKEDIN_PASS')
    if not user or not pwd:
        logger.error('Set LINKEDIN_USER and LINKEDIN_PASS environment variables before calling this helper')
        return False

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto('https://www.linkedin.com/login', wait_until='domcontentloaded')
            page.fill('input[name="session_key"]', user)
            page.fill('input[name="session_password"]', pwd)
            page.click('button[type="submit"]')
            page.wait_for_load_state('networkidle', timeout=15000)
            context.storage_state(path=output_path)
            browser.close()
        logger.info(f"Saved LinkedIn storage_state to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create LinkedIn storage state: {e}")
        return False

def upsert_jobs_to_supabase(client: object, jobs_df: pd.DataFrame) -> None:
    """Upsert jobs to Supabase table. Updates if job_id exists, inserts if new."""
    if client is None or jobs_df.empty:
        return
    
    try:
        rows = []
        for _, row in jobs_df.iterrows():
            rows.append({
                'job_id': str(row.get('Job ID', '')),
                'job_link': str(row.get('Job Link', '')),
                'title': str(row.get('Title', '')),
                'location': str(row.get('Location', '')),
                'posted': str(row.get('Posted', '')),
                'minimum_requirements': str(row.get('Minimum Requirements', '')),
                'good_to_have': str(row.get('Good to Have', '')),
                'job_description': str(row.get('Job Description', '')),
                'source': str(row.get('Source', ''))
            })
        
        response = client.table('jobs').upsert(rows, returning='minimal').execute()
        logger.info(f"Upserted {len(rows)} jobs to Supabase")
    except Exception as e:
        logger.error(f"Failed to upsert jobs to Supabase: {e}")

def run_multi_site_scraper(headless: bool = True):
    """Scrape multiple job sites
    
    Args:
        headless: Run browser in headless mode (default True)
    """
    
    sites = [
        {
            'name': 'Amazon Jobs',
            'type': 'amazon',
            'url': 'https://www.amazon.jobs/en/search?base_query=&loc_query=India&country=IND&employment_type%5B%5D=Full%20Time',
            'enabled': True
        },
        {
            'name': 'P&G Careers',
            'type': 'pg_careers',
            'url': 'https://www.pgcareers.com/global/en/search-results',
            'enabled': True
        },
        {
            'name': 'LinkedIn Jobs',
            'type': 'linkedin',
            'url': 'https://www.linkedin.com/jobs/search/?keywords=software%20engineer&location=India',
            'enabled': True,
            'storage_state': 'linkedin_state.json'  # set to your saved storage state file if you need authenticated access
        },
        ]

    all_jobs = []

    for site in sites:
        if not site.get('enabled', True):
            logger.info(f"Skipping {site['name']} (disabled)")
            continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Starting scrape for {site['name']}")
        logger.info(f"{'='*60}")
        
        scraper = JobSiteScraper(site)
        try:
            storage_state = site.get('storage_state')
            scraper.start_browser(headless=headless, storage_state=storage_state)
            jobs = scraper.scrape(site['url'])
            # Filter valid jobs
            valid_jobs = [job for job in jobs if validate_job_data(job)]
            all_jobs.extend(valid_jobs)
            logger.info(f"Successfully scraped {len(valid_jobs)} valid jobs from {site['name']}")
        except Exception as e:
            logger.error(f"Failed to scrape {site['name']}: {e}")
        finally:
            scraper.close_browser()
    
    if not all_jobs:
        logger.warning("No jobs were scraped from any site")
        return None

    new_df = pd.DataFrame(all_jobs).astype(str)
    output_file = Path('multi_site_jobs.xlsx')

    if output_file.exists():
        try:
            existing_df = pd.read_excel(output_file).astype(str)
        except Exception as e:
            logger.error(f"Failed to read existing Excel: {e}")
            existing_df = pd.DataFrame()
    else:
        existing_df = pd.DataFrame()

    # Ensure Job ID present in existing (backfill if missing)
    if not existing_df.empty:
        if 'Job ID' not in existing_df.columns:
            existing_df['Job ID'] = existing_df['Job Link'].apply(compute_job_id)
        existing_df.set_index('Job ID', inplace=True, drop=False)

    # Prepare new data
    if 'Job ID' not in new_df.columns:
        new_df['Job ID'] = new_df['Job Link'].apply(compute_job_id)
    new_df.set_index('Job ID', inplace=True, drop=False)

    # Merge: update existing rows, add new ones
    if existing_df.empty:
        merged_df = new_df
        added = len(new_df)
        updated = 0
    else:
        merged_df = existing_df.copy()
        overlap_ids = existing_df.index.intersection(new_df.index)
        added_df = new_df[~new_df.index.isin(existing_df.index)]
        updated = len(overlap_ids)
        added = len(added_df)
        # Update overlapping rows with latest scraped data
        merged_df.update(new_df.loc[overlap_ids])
        # Append new rows
        merged_df = pd.concat([merged_df, added_df])

    # Save to Excel
    merged_df.reset_index(drop=True, inplace=True)
    merged_df.to_excel(output_file, index=False)
    logger.info(f"\nSaved {len(merged_df)} total jobs to {output_file} (added {added}, updated {updated})")
    
    # Sync to Supabase
    supabase_client = get_supabase_client()
    if supabase_client:
        upsert_jobs_to_supabase(supabase_client, merged_df)
    
    return merged_df

if __name__ == "__main__":
    df = run_multi_site_scraper()
    if df is not None:
        print(f"\nTotal jobs scraped: {len(df)}")
        print(f"Sources: {df['Source'].unique()}")
        print(f"\nFirst few rows:")
        print(df.head())
