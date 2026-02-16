from playwright.sync_api import sync_playwright
import pandas as pd
import logging
import time
import json
import hashlib
import os
from urllib.parse import unquote
from pathlib import Path
from functools import wraps
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
import traceback
import re
from urllib.parse import urlparse

FILTER_PROFILE_CACHE_FILE = 'site_filter_profiles.json'

DEFAULT_GENERIC_FILTERS = {
    'include_patterns': ['/job', '/jobs', '/search', 'workdayjobs', 'greenhouse.io', 'lever.co'],
    'exclude_patterns': ['/about', '/blog', '/news', '/event', '/privacy', '/terms', '/contact', '/investor'],
    'title_must_contain': [],
    'max_jobs': 20
}

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

# Standard job schema to ensure consistency across all scrapers
JOB_SCHEMA = ['Job ID', 'Job Link', 'Title', 'Company', 'Location', 'Posted', 
              'Minimum Requirements', 'Good to Have', 'Job Description', 
              'Years of Experience', 'Essential Keywords', 'Source']

def extract_years_of_experience(text: str) -> str:
    """Extract minimum numeric years of experience from job text"""
    import re
    if not text:
        return ''

    normalized = re.sub(r'\s+', ' ', text.lower())

    # Prefer explicit ranges tied to experience context (return minimum numeric value)
    range_match = re.search(
        r'(\d{1,2})\s*\+?\s*(?:to|\-|–)\s*(\d{1,2})\s*\+?\s*years?\s*(?:of\s*)?(?:relevant\s*)?(?:professional\s*)?(?:work\s*)?(?:experience|exp)',
        normalized
    )
    if range_match:
        return str(int(range_match.group(1)))

    # Match expressions like "minimum of 3+ years of experience", "at least 5 yrs exp"
    single_patterns = [
        r'(?:minimum(?:\s+of)?|at\s+least|over|more\s+than)?\s*(\d{1,2})\s*\+?\s*years?\s*(?:of\s*)?(?:relevant\s*)?(?:professional\s*)?(?:work\s*)?(?:experience|exp)',
        r'(\d{1,2})\s*\+?\s*yrs?\s*(?:of\s*)?(?:relevant\s*)?(?:professional\s*)?(?:work\s*)?(?:experience|exp)',
        r'(?:experience|exp)\s*(?:of\s*)?(\d{1,2})\s*\+?\s*years?'
    ]

    for pattern in single_patterns:
        for match in re.finditer(pattern, normalized):
            value = int(match.group(1))
            if 0 < value <= 40:
                return str(value)

    return ''

def extract_essential_keywords(text: str, title: str = '') -> str:
    """Extract essential technical keywords and skills from job description"""
    import re
    if not text:
        return ''
    
    # Combine text sources
    combined_text = f"{title} {text}".lower()
    
    # Common technical keywords and skills to look for
    tech_keywords = [
        # Programming languages
        'python', 'java', 'javascript', 'typescript', 'c\\+\\+', 'c#', 'ruby', 'go', 'rust', 'php', 'swift', 'kotlin',
        # Frameworks/Libraries
        'react', 'angular', 'vue', 'node\\.?js', 'django', 'flask', 'spring', 'express', 'fastapi',
        # Databases
        'sql', 'mysql', 'postgresql', 'mongodb', 'redis', 'dynamodb', 'oracle', 'cassandra',
        # Cloud/DevOps
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'jenkins', 'ci/cd', 'terraform', 'ansible',
        # Data/AI/ML
        'machine learning', 'deep learning', 'ai', 'data science', 'tensorflow', 'pytorch', 'pandas', 'numpy',
        # Other skills
        'agile', 'scrum', 'git', 'rest api', 'graphql', 'microservices', 'linux', 'bash',
    ]
    
    found_keywords = []
    for keyword in tech_keywords:
        if re.search(r'\b' + keyword + r'\b', combined_text):
            # Capitalize properly
            clean_keyword = keyword.replace('\\', '').replace('.', '').replace('?', '')
            found_keywords.append(clean_keyword.upper() if len(clean_keyword) <= 4 else clean_keyword.title())
    
    # Remove duplicates and return comma-separated
    unique_keywords = list(dict.fromkeys(found_keywords))
    return ', '.join(unique_keywords[:15])  # Limit to top 15 keywords


def normalize_site_type(site_type: str) -> str:
    """Normalize site type and fallback unsupported types to generic."""
    supported = {'amazon', 'pg_careers', 'linkedin', 'generic'}
    normalized = (site_type or '').strip().lower()
    return normalized if normalized in supported else 'generic'


def derive_name_from_url(url: str) -> str:
    """Build a readable site name from URL host."""
    host = urlparse(url).netloc.lower().replace('www.', '')
    if not host:
        return 'External Careers'

    parts = host.split('.')
    base_part = parts[0] if parts else host
    if base_part in ('careers', 'career', 'jobs', 'job') and len(parts) > 1:
        base_part = parts[1]

    root = base_part.replace('-', ' ').replace('_', ' ').strip()
    return root.title() + ' Careers'


def extract_urls_from_pdf(pdf_path: str) -> List[str]:
    """Extract unique career-site URLs from a PDF file."""
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed; cannot parse PDF sites file. Install with: pip install pypdf")
        return []

    try:
        reader = PdfReader(pdf_path)
        text_chunks = []
        for page in reader.pages:
            text_chunks.append(page.extract_text() or '')
        text = ' '.join(text_chunks)
    except Exception as e:
        logger.error(f"Failed to parse PDF sites file '{pdf_path}': {e}")
        return []

    candidates = re.findall(r'https?://[^\s\]\[\)\("\'<>]+', text)
    cleaned = []
    for url in candidates:
        normalized = url.strip().rstrip('.,;:')
        if normalized:
            cleaned.append(normalized)

    # Preserve order and uniqueness
    return list(dict.fromkeys(cleaned))


def load_additional_sites(sites_file: str) -> List[Dict]:
    """Load additional site configs from CSV/XLSX/JSON."""
    if not sites_file:
        return []

    file_path = Path(sites_file)
    if not file_path.exists():
        logger.warning(f"Sites file not found: {sites_file}")
        return []

    suffix = file_path.suffix.lower()

    if suffix == '.pdf':
        logger.warning(
            f"PDF is not supported directly for --sites-file: {sites_file}. "
            "Extract URLs first using --extract-sites-pdf and then pass the generated JSON file to --sites-file."
        )
        return []

    try:
        if suffix == '.csv':
            raw_df = pd.read_csv(file_path)
        elif suffix in ('.xlsx', '.xls'):
            raw_df = pd.read_excel(file_path)
        elif suffix == '.json':
            raw_df = pd.DataFrame(json.loads(file_path.read_text(encoding='utf-8')))
        else:
            logger.warning(f"Unsupported sites file format: {sites_file}. Use CSV, XLSX, or JSON")
            return []
    except Exception as e:
        logger.error(f"Failed to read sites file '{sites_file}': {e}")
        return []

    if raw_df.empty:
        logger.warning(f"Sites file '{sites_file}' is empty")
        return []

    normalized_cols = {str(col).strip().lower(): col for col in raw_df.columns}

    def pick_col(*names: str) -> Optional[str]:
        for name in names:
            if name in normalized_cols:
                return normalized_cols[name]
        return None

    name_col = pick_col('name', 'company', 'company_name')
    url_col = pick_col('url', 'career_url', 'careers_url', 'site', 'website', 'link')
    type_col = pick_col('type', 'site_type')
    enabled_col = pick_col('enabled', 'is_enabled', 'active')

    if not url_col:
        logger.warning(f"Sites file '{sites_file}' is missing URL column (expected: url/career_url/careers_url/site)")
        return []

    sites: List[Dict] = []
    for _, row in raw_df.iterrows():
        raw_url = str(row.get(url_col, '')).strip()
        if not raw_url or raw_url.lower() in ('nan', 'none'):
            continue

        url = raw_url if raw_url.startswith(('http://', 'https://')) else f"https://{raw_url}"
        site_name = str(row.get(name_col, '')).strip() if name_col else ''
        if not site_name or site_name.lower() in ('nan', 'none'):
            site_name = derive_name_from_url(url)

        site_type = normalize_site_type(str(row.get(type_col, '')).strip() if type_col else 'generic')

        enabled = True
        if enabled_col:
            enabled_value = str(row.get(enabled_col, 'true')).strip().lower()
            enabled = enabled_value in ('1', 'true', 'yes', 'y')

        sites.append({
            'name': site_name,
            'type': site_type,
            'url': url,
            'enabled': enabled
        })

    logger.info(f"Loaded {len(sites)} additional sites from {sites_file}")
    return sites


def export_sites_from_pdf(pdf_path: str, output_file: str = 'extracted_company_sites.json') -> int:
    """Extract site URLs from PDF and save them to JSON as generic site configs."""
    urls = extract_urls_from_pdf(pdf_path)
    if not urls:
        return 0

    sites = [
        {
            'name': derive_name_from_url(url),
            'type': 'generic',
            'url': url,
            'enabled': True
        }
        for url in urls
    ]

    output_path = Path(output_file)
    output_path.write_text(json.dumps(sites, indent=2), encoding='utf-8')
    logger.info(f"Saved {len(sites)} extracted sites to {output_path}")
    return len(sites)


def get_site_profile_key(url: str) -> str:
    """Stable key for per-site filter profile cache."""
    parsed = urlparse(url)
    return parsed.netloc.lower().replace('www.', '').strip()


def load_filter_profiles(cache_file: str = FILTER_PROFILE_CACHE_FILE) -> Dict[str, Dict]:
    """Load cached per-site filter profiles."""
    path = Path(cache_file)
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to read filter profile cache '{cache_file}': {e}")
        return {}


def save_filter_profiles(profiles: Dict[str, Dict], cache_file: str = FILTER_PROFILE_CACHE_FILE) -> None:
    """Persist per-site filter profiles for future runs."""
    try:
        Path(cache_file).write_text(json.dumps(profiles, indent=2), encoding='utf-8')
        logger.info(f"Saved filter profiles to {cache_file}")
    except Exception as e:
        logger.warning(f"Failed to write filter profile cache '{cache_file}': {e}")

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
        self.p = None  # Initialize Playwright instance to avoid AttributeError in close_browser
    
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
                        desc_heading = self.page.locator('h2:has-text("Job Description"), h2:has-text("Description"), h3:has-text("Job Description")').first
                        if desc_heading:
                            # Get the next paragraph or div with content
                            next_elem = desc_heading.evaluate('(el) => el.nextElementSibling?.textContent || ""')
                            job_description = next_elem.strip() if next_elem else ''
                        if not job_description:
                            # Fallback: grab body text
                            body_text = self.page.locator('body').text_content()
                            job_description = body_text[:500] if body_text else ''
                    except Exception:
                        pass
                    
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
                        'Years of Experience': extract_years_of_experience(f"{min_req} {good_to_have} {job_description}"),
                        'Essential Keywords': extract_essential_keywords(f"{min_req} {good_to_have} {job_description}", title),
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
                    try:
                        self.page.wait_for_selector('h1, title, meta[property="og:title"]', timeout=5000)
                    except Exception:
                        pass
                    
                    # Extract from job detail page
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
                    
                    # Try to get requirements / must-have section first
                    min_req = self.safe_extract('[class*="requirement"], [class*="qualification"]', default='')
                    if not min_req:
                        min_req = self.extract_section_from_body([
                            'job qualifications',
                            'qualifications',
                            'must have',
                            'what we are looking for',
                            'requirements',
                            'minimum qualifications'
                        ])
                    
                    # Get full page text as fallback
                    if not min_req:
                        try:
                            page_text = self.page.locator('body').text_content()[:500]
                            min_req = page_text if page_text else ''
                        except Exception:
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
                    except Exception:
                        pass
                    
                    years_of_experience = extract_years_of_experience(min_req)
                    if not years_of_experience:
                        years_of_experience = extract_years_of_experience(f"{min_req} {job_description}")

                    jobs_data.append({
                        'Job ID': compute_job_id(link),
                        'Job Link': link,
                        'Title': title[:100] if title else '',
                        'Company': 'P&G',
                        'Location': location[:150] if location else '',
                        'Posted': posted[:50] if posted else '',
                        'Minimum Requirements': min_req[:300] if min_req else '',
                        'Good to Have': good_to_have,
                        'Job Description': job_description[:500] if job_description else '',
                        'Years of Experience': years_of_experience,
                        'Essential Keywords': extract_essential_keywords(f"{min_req} {job_description}", title),
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
                    except Exception:
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
                        'Years of Experience': extract_years_of_experience(job_description),
                        'Essential Keywords': extract_essential_keywords(job_description, title),
                        'Source': 'LinkedIn'
                    })
                except Exception as e:
                    logger.error(f"Error extracting LinkedIn job {idx}: {e}")
        except Exception as e:
            logger.error(f"Error in LinkedIn extraction: {e}")
        return jobs_data

    @retry(max_attempts=2, delay=3.0)
    def extract_from_generic(self) -> List[Dict]:
        """Generic extractor for external career sites loaded from files."""
        logger.info("Using generic extraction method")
        jobs_data = []

        try:
            self.page.wait_for_timeout(2500)

            candidate_selectors = [
                'a[href*="/job"]',
                'a[href*="/jobs"]',
                'a[href*="/search"]',
                'a[href*="/careers"]',
                'a[href*="greenhouse.io"]',
                'a[href*="lever.co"]',
                'a[href*="workday"]'
            ]

            links: List[str] = []
            for selector in candidate_selectors:
                try:
                    extracted = self.page.eval_on_selector_all(
                        selector,
                        'elements => [...new Set(elements.map(e => e.href).filter(Boolean))]'
                    )
                    links.extend(extracted)
                except Exception:
                    continue

            unique_links = []
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
            if not filters and self.config.get('auto_analyze_filters', True):
                filters = self.infer_generic_filters(unique_links)
                self.config['filters'] = filters
                self.config['inferred_filters'] = filters
                logger.info(
                    f"Inferred filters for {self.config.get('name', 'site')}: "
                    f"include={filters.get('include_patterns', [])}, "
                    f"exclude={filters.get('exclude_patterns', [])}, "
                    f"max_jobs={filters.get('max_jobs', 20)}"
                )

            filtered_links = self.apply_generic_filters(unique_links, filters)
            logger.info(f"Filtered generic links: {len(filtered_links)} (from {len(unique_links)} candidates)")

            # Expand listing pages (e.g., /search, /jobs) to concrete job detail links
            expanded_links = self.expand_listing_links(filtered_links)
            scrape_links = expanded_links if expanded_links else filtered_links
            if expanded_links:
                logger.info(f"Expanded to {len(expanded_links)} job-detail links from listing pages")

            for idx, link in enumerate(scrape_links, 1):
                try:
                    logger.info(f"Processing generic job {idx}/{len(scrape_links)}")
                    self.page.goto(link, wait_until='domcontentloaded', timeout=15000)

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
                        'job qualifications'
                    ])

                    job_description = ''
                    try:
                        body_text = self.page.locator('body').text_content() or ''
                        job_description = ' '.join(body_text.split())[:800]
                    except Exception:
                        pass

                    years_of_experience = extract_years_of_experience(min_req)
                    if not years_of_experience:
                        years_of_experience = extract_years_of_experience(job_description)

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
                        'Essential Keywords': extract_essential_keywords(f"{min_req} {job_description}", title),
                        'Source': self.config.get('name', 'External Careers')
                    })
                except Exception as e:
                    logger.error(f"Error extracting generic job {idx}: {str(e)[:100]}")

        except Exception as e:
            logger.error(f"Error in generic extraction: {e}")

        return jobs_data

    def infer_generic_filters(self, links: List[str]) -> Dict:
        """Infer site-specific link filters from first-run link candidates."""
        include_hints = [
            '/job/', '/jobs/', '/job?', '/jobs?',
            '/search/', '/search?',
            'workdayjobs', 'greenhouse.io', 'lever.co', 'smartrecruiters', 'icims.com'
        ]

        include_patterns: List[str] = []
        links_lower = [link.lower() for link in links]

        for hint in include_hints:
            if any(hint in link for link in links_lower):
                include_patterns.append(hint)

        inferred = {
            'include_patterns': include_patterns or DEFAULT_GENERIC_FILTERS['include_patterns'],
            'exclude_patterns': list(DEFAULT_GENERIC_FILTERS['exclude_patterns']),
            'title_must_contain': [],
            'max_jobs': DEFAULT_GENERIC_FILTERS['max_jobs']
        }
        return inferred

    def apply_generic_filters(self, links: List[str], filters: Optional[Dict]) -> List[str]:
        """Apply per-site include/exclude filters to candidate links."""
        if not links:
            return []

        effective_filters = filters or DEFAULT_GENERIC_FILTERS
        include_patterns = [str(p).lower() for p in effective_filters.get('include_patterns', []) if str(p).strip()]
        exclude_patterns = [str(p).lower() for p in effective_filters.get('exclude_patterns', []) if str(p).strip()]
        max_jobs_raw = effective_filters.get('max_jobs', DEFAULT_GENERIC_FILTERS['max_jobs'])

        try:
            max_jobs = int(max_jobs_raw)
        except Exception:
            max_jobs = DEFAULT_GENERIC_FILTERS['max_jobs']

        filtered: List[str] = []
        for link in links:
            lower_link = link.lower()

            if include_patterns and not any(pattern in lower_link for pattern in include_patterns):
                continue
            if exclude_patterns and any(pattern in lower_link for pattern in exclude_patterns):
                continue

            path = urlparse(link).path.strip().lower()
            if path in ('', '/', '/careers', '/jobs'):
                continue

            if link not in filtered:
                filtered.append(link)

        return filtered[:max_jobs]

    def expand_listing_links(self, links: List[str]) -> List[str]:
        """Open listing/search links and extract concrete job detail links."""
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
                anchors = self.page.eval_on_selector_all('a[href]', 'els => [...new Set(els.map(e => e.href).filter(Boolean))]')
                for anchor in anchors:
                    if not isinstance(anchor, str) or not anchor.startswith('http'):
                        continue
                    lower_anchor = anchor.lower()
                    if any(token in lower_anchor for token in job_tokens):
                        if anchor not in expanded:
                            expanded.append(anchor)
            except Exception:
                continue

        max_jobs = int((self.config.get('filters') or {}).get('max_jobs', DEFAULT_GENERIC_FILTERS['max_jobs']))
        return expanded[:max_jobs]
    
    def safe_extract(self, selector: str, default: str = '') -> str:
        """Safely extract text from selector"""
        try:
            element = self.page.query_selector(selector)
            if element:
                return element.inner_text().strip()
        except Exception:
            pass
        return default

    def extract_section_from_body(self, headings: List[str], window: int = 1800) -> str:
        """Extract a focused section from body text using heading keywords"""
        try:
            body_text = self.page.locator('body').text_content() or ''
            if not body_text:
                return ''

            normalized = ' '.join(body_text.split())
            lower_text = normalized.lower()

            for heading in headings:
                idx = lower_text.find(heading.lower())
                if idx != -1:
                    return normalized[idx:idx + window].strip()
        except Exception:
            pass

        return ''


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
        # Add timestamp to all records
        timestamp = datetime.utcnow().isoformat()
        
        rows = []
        for _, row in jobs_df.iterrows():
            rows.append({
                'job_id': str(row.get('Job ID', '')),
                'job_link': str(row.get('Job Link', '')),
                'title': str(row.get('Title', '')),
                'company': str(row.get('Company', '')),
                'location': str(row.get('Location', '')),
                'posted': str(row.get('Posted', '')),
                'minimum_requirements': str(row.get('Minimum Requirements', '')),
                'good_to_have': str(row.get('Good to Have', '')),
                'job_description': str(row.get('Job Description', '')),
                'years_of_experience': str(row.get('Years of Experience', '')),
                'essential_keywords': str(row.get('Essential Keywords', '')),
                'source': str(row.get('Source', '')),
                'scraped_at': timestamp
            })
        
        # Batch upserts to avoid timeouts (50 rows at a time)
        batch_size = 50
        total_rows = len(rows)
        
        for i in range(0, total_rows, batch_size):
            batch = rows[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_rows + batch_size - 1) // batch_size
            
            try:
                response = client.table('jobs').upsert(
                    batch, 
                    on_conflict='job_id',
                    returning='minimal'
                ).execute()
                logger.info(f"Upserted batch {batch_num}/{total_batches} ({len(batch)} rows) to Supabase")
                
                # Small delay between batches to avoid rate limits
                if i + batch_size < total_rows:
                    time.sleep(0.5)
                    
            except Exception as batch_error:
                logger.error(f"Failed to upsert batch {batch_num} ({len(batch)} rows) to Supabase")
                logger.error(f"Error details: {str(batch_error)}")
                logger.error(f"Traceback:\n{traceback.format_exc()}")
        
        logger.info(f"Successfully upserted {total_rows} jobs to Supabase in {total_batches} batches")
        
    except Exception as e:
        logger.error(f"Failed to upsert jobs to Supabase: {str(e)}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")

def run_multi_site_scraper(headless: bool = True, site_filter: Optional[List[str]] = None, output_file: str = 'multi_site_jobs.xlsx', sites_file: Optional[str] = None):
    """Scrape multiple job sites
    
    Args:
        headless: Run browser in headless mode (default True)
        site_filter: Optional list of site types to scrape (e.g., ['amazon', 'pg_careers'])
        output_file: Output Excel filename (default 'multi_site_jobs.xlsx')
        sites_file: Optional CSV/XLSX/JSON/PDF file with additional career-site URLs
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
            'enabled': False,  # Disabled until auth flow is finalized
            'storage_state': 'linkedin_state.json'  # set to your saved storage state file if you need authenticated access
        },
    ]

    if sites_file:
        external_sites = load_additional_sites(sites_file)
        sites.extend(external_sites)
        logger.info(f"Total configured sites after file load: {len(sites)}")

    all_jobs = []
    filter_profiles = load_filter_profiles()
    profiles_updated = False

    for site in sites:
        if not site.get('enabled', True):
            logger.info(f"Skipping {site['name']} (disabled)")
            continue
        
        # Apply site filter if provided
        if site_filter and site['type'] not in site_filter:
            logger.info(f"Skipping {site['name']} (not in filter)")
            continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Starting scrape for {site['name']}")
        logger.info(f"{'='*60}")

        if site.get('type') == 'generic':
            site_key = get_site_profile_key(site.get('url', ''))
            site['site_profile_key'] = site_key
            if not site.get('filters') and site_key in filter_profiles:
                site['filters'] = filter_profiles[site_key]
                logger.info(f"Using cached filters for {site['name']} ({site_key})")
            elif not site.get('filters'):
                site['auto_analyze_filters'] = True
                logger.info(f"No cached filters for {site['name']} ({site_key}); inferring filters from first run")
        
        scraper = JobSiteScraper(site)
        try:
            storage_state = site.get('storage_state')
            
            # Check if storage_state file exists before passing it
            if storage_state and not os.path.exists(storage_state):
                logger.warning(f"Storage state file '{storage_state}' not found for {site['name']}, proceeding without authentication")
                storage_state = None
            
            scraper.start_browser(headless=headless, storage_state=storage_state)
            jobs = scraper.scrape(site['url'])

            if site.get('type') == 'generic':
                inferred_filters = scraper.config.get('inferred_filters')
                site_key = scraper.config.get('site_profile_key') or get_site_profile_key(site.get('url', ''))
                if inferred_filters and site_key:
                    filter_profiles[site_key] = inferred_filters
                    profiles_updated = True

            # Filter valid jobs
            valid_jobs = [job for job in jobs if validate_job_data(job)]
            all_jobs.extend(valid_jobs)
            logger.info(f"Successfully scraped {len(valid_jobs)} valid jobs from {site['name']}")
        except Exception as e:
            logger.error(f"Failed to scrape {site['name']}: {e}")
        finally:
            scraper.close_browser()

    if profiles_updated:
        save_filter_profiles(filter_profiles)
    
    if not all_jobs:
        logger.warning("No jobs were scraped from any site")
        return None

    new_df = pd.DataFrame(all_jobs).astype(str)
    
    # Ensure all columns from JOB_SCHEMA are present
    for col in JOB_SCHEMA:
        if col not in new_df.columns:
            new_df[col] = ''
    
    output_path = Path(output_file)

    if output_path.exists():
        try:
            existing_df = pd.read_excel(output_path).astype(str)
        except Exception as e:
            logger.error(f"Failed to read existing Excel: {e}")
            existing_df = pd.DataFrame()
    else:
        existing_df = pd.DataFrame()

    # Ensure Job ID present in existing (backfill if missing)
    if not existing_df.empty:
        if 'Job ID' not in existing_df.columns:
            existing_df['Job ID'] = existing_df['Job Link'].apply(compute_job_id)
        
        # Ensure all columns from JOB_SCHEMA are present
        for col in JOB_SCHEMA:
            if col not in existing_df.columns:
                existing_df[col] = ''
        
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
    
    # Fill NaN values with empty strings to avoid schema mismatches
    merged_df = merged_df.fillna('')
    
    # Ensure all columns from JOB_SCHEMA are present in the final output
    for col in JOB_SCHEMA:
        if col not in merged_df.columns:
            merged_df[col] = ''

    # Save to Excel with columns in schema order
    merged_df.reset_index(drop=True, inplace=True)
    # Reorder columns to match JOB_SCHEMA, keep any extra columns at the end
    ordered_cols = [col for col in JOB_SCHEMA if col in merged_df.columns]
    extra_cols = [col for col in merged_df.columns if col not in JOB_SCHEMA]
    merged_df = merged_df[ordered_cols + extra_cols]
    
    merged_df.to_excel(output_path, index=False)
    logger.info(f"\nSaved {len(merged_df)} total jobs to {output_path} (added {added}, updated {updated})")
    
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
