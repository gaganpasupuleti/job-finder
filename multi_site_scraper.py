"""
Multi-site job scraper — backward-compatible facade.

All implementation has been moved to sub-packages:
  scrapers/   — site-specific Playwright scrapers
  db/         — Supabase sync
  utils/      — experience, keywords, job utilities, site loading, filters

This module re-exports everything so that existing callers remain unaffected:

    from multi_site_scraper import run_multi_site_scraper, ...
"""

# ---------------------------------------------------------------------------
# Re-exports from sub-modules (backward compatibility)
# ---------------------------------------------------------------------------
from utils.experience import extract_years_of_experience  # noqa: F401
from utils.keywords import extract_essential_keywords      # noqa: F401
from utils.job_utils import compute_job_id, validate_job_data, JOB_SCHEMA  # noqa: F401
from utils.sites_loader import (  # noqa: F401
    normalize_site_type,
    derive_name_from_url,
    load_additional_sites,
    export_sites_from_pdf,
    extract_urls_from_pdf,
)
from utils.filters import (  # noqa: F401
    FILTER_PROFILE_CACHE_FILE,
    DEFAULT_GENERIC_FILTERS,
    get_site_profile_key,
    load_filter_profiles,
    save_filter_profiles,
)
from utils.retry import retry  # noqa: F401
from utils.salary import extract_salary  # noqa: F401
from utils.work_mode import detect_work_mode  # noqa: F401
from db.supabase_sync import (  # noqa: F401
    get_supabase_client,
    upsert_jobs_to_supabase,
    fetch_recent_cached_jobs,
)

# ---------------------------------------------------------------------------
# Composite scraper class — inherits all extract_from_* methods
# ---------------------------------------------------------------------------
import logging
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import pandas as pd

from scrapers.base import JobSiteScraper as _BaseScraper
from scrapers.amazon import AmazonScraper as _AmazonMixin
from scrapers.pg import PGScraper as _PGMixin
from scrapers.linkedin import LinkedInScraper as _LinkedInMixin
from scrapers.generic import GenericScraper as _GenericMixin

logger = logging.getLogger(__name__)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)


class JobSiteScraper(  # noqa: E302
    _AmazonMixin,
    _PGMixin,
    _LinkedInMixin,
    _GenericMixin,
    _BaseScraper,
):
    """All-in-one scraper combining base + all site-specific extractors."""


# ---------------------------------------------------------------------------
# save_linkedin_storage_state helper
# ---------------------------------------------------------------------------

def save_linkedin_storage_state(output_path: str = 'linkedin_state.json') -> bool:
    """Log in to LinkedIn and save Playwright storage_state to *output_path*.

    Reads credentials from ``LINKEDIN_USER`` / ``LINKEDIN_PASS`` env vars.
    Run this once to create the session file used for authenticated scraping.

    Args:
        output_path: Destination path for the storage-state JSON.

    Returns:
        ``True`` on success, ``False`` on failure.
    """
    user = os.getenv('LINKEDIN_USER')
    pwd = os.getenv('LINKEDIN_PASS')
    if not user or not pwd:
        logger.error(
            'Set LINKEDIN_USER and LINKEDIN_PASS environment variables before calling this helper'
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
            page.wait_for_load_state('networkidle', timeout=15000)
            context.storage_state(path=output_path)
            browser.close()
        logger.info(f"Saved LinkedIn storage_state to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create LinkedIn storage state: {e}")
        return False


# ---------------------------------------------------------------------------
# Main scraper orchestrator
# ---------------------------------------------------------------------------

def run_multi_site_scraper(
    headless: bool = True,
    site_filter: Optional[List[str]] = None,
    output_file: str = 'multi_site_jobs.xlsx',
    sites_file: Optional[str] = None,
    linkedin_enabled: bool = False,
    linkedin_keywords: str = 'software engineer',
    linkedin_location: str = 'India',
    linkedin_max_jobs: int = 50,
    linkedin_source: str = 'browser',
    linkedin_api_pages: int = 1,
    linkedin_storage_state: str = 'linkedin_state.json',
    dry_run: bool = False,
) -> Optional[pd.DataFrame]:
    """Scrape multiple job sites and return a consolidated DataFrame.

    Args:
        headless: Run browser in headless mode (default ``True``).
        site_filter: Optional list of site types to scrape.
        output_file: Output Excel filename.
        sites_file: Optional CSV / XLSX / JSON file with extra career sites.
        linkedin_enabled: Enable LinkedIn scraping for this run.
        linkedin_keywords: LinkedIn search keywords.
        linkedin_location: LinkedIn search location.
        linkedin_max_jobs: Maximum number of LinkedIn jobs to process.
        linkedin_source: LinkedIn source mode: ``browser`` or ``rapidapi``.
        linkedin_api_pages: Number of RapidAPI pages to request.
        linkedin_storage_state: Path to LinkedIn Playwright storage state.
        dry_run: When ``True`` collect data but skip writing Excel / Supabase.

    Returns:
        DataFrame of all scraped jobs, or ``None`` when nothing was scraped.
    """
    sites: List[Dict] = [
        {
            'name': 'Amazon Jobs',
            'type': 'amazon',
            'url': (
                'https://www.amazon.jobs/en/search?base_query=&loc_query=India'
                '&country=IND&employment_type%5B%5D=Full%20Time'
            ),
            'enabled': True,
        },
        {
            'name': 'P&G Careers',
            'type': 'pg_careers',
            'url': 'https://www.pgcareers.com/global/en/search-results',
            'enabled': True,
        },
        {
            'name': 'LinkedIn Jobs',
            'type': 'linkedin',
            'url': (
                f'https://www.linkedin.com/jobs/search/'
                f'?keywords={quote_plus(linkedin_keywords)}'
                f'&location={quote_plus(linkedin_location)}'
            ),
            'enabled': linkedin_enabled,
            'storage_state': linkedin_storage_state,
            'max_jobs': max(1, int(linkedin_max_jobs)),
            'source_mode': str(linkedin_source).lower().strip(),
            'api_pages': max(1, int(linkedin_api_pages)),
            'keywords': linkedin_keywords,
            'location': linkedin_location,
            'slow_mo_ms': 95,
        },
    ]

    if sites_file:
        external_sites = load_additional_sites(sites_file)
        sites.extend(external_sites)
        logger.info(f"Total configured sites after file load: {len(sites)}")

    all_jobs: List[Dict] = []
    supabase_client = get_supabase_client()
    filter_profiles = load_filter_profiles()
    profiles_updated = False

    for site in sites:
        if not site.get('enabled', True):
            logger.info(f"Skipping {site['name']} (disabled)")
            continue
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
                logger.info(
                    f"No cached filters for {site['name']} ({site_key}); "
                    "inferring filters from first run"
                )

        scraper = JobSiteScraper(site)
        try:
            storage_state = site.get('storage_state')
            if storage_state and not os.path.exists(storage_state):
                logger.warning(
                    f"Storage state file '{storage_state}' not found for "
                    f"{site['name']}, proceeding without authentication"
                )
                storage_state = None

            if site.get('type') == 'linkedin' and supabase_client is not None:
                cached = fetch_recent_cached_jobs(
                    supabase_client,
                    keywords=str(site.get('keywords', '')),
                    location=str(site.get('location', '')),
                    source='LinkedIn',
                    max_age_hours=24,
                    limit=max(50, int(site.get('max_jobs', 50)) * 4),
                )
                if cached:
                    logger.info(
                        f"Using {len(cached)} cached LinkedIn jobs from last 24h "
                        f"for keywords='{site.get('keywords')}', location='{site.get('location')}'"
                    )
                    all_jobs.extend(cached[: int(site.get('max_jobs', 50))])
                    continue

            scraper.start_browser(headless=headless, storage_state=storage_state)
            jobs = scraper.scrape(site['url'])

            if site.get('type') == 'generic':
                inferred_filters = scraper.config.get('inferred_filters')
                site_key = scraper.config.get('site_profile_key') or get_site_profile_key(
                    site.get('url', '')
                )
                if inferred_filters and site_key:
                    filter_profiles[site_key] = inferred_filters
                    profiles_updated = True

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

    for col in JOB_SCHEMA:
        if col not in new_df.columns:
            new_df[col] = ''

    if dry_run:
        logger.info(f"[dry-run] Would write {len(new_df)} jobs — skipping Excel and Supabase.")
        return new_df

    output_path = Path(output_file)

    if output_path.exists():
        try:
            existing_df = pd.read_excel(output_path).astype(str)
        except Exception as e:
            logger.error(f"Failed to read existing Excel: {e}")
            existing_df = pd.DataFrame()
    else:
        existing_df = pd.DataFrame()

    if not existing_df.empty:
        if 'Job ID' not in existing_df.columns:
            existing_df['Job ID'] = existing_df['Job Link'].apply(compute_job_id)
        for col in JOB_SCHEMA:
            if col not in existing_df.columns:
                existing_df[col] = ''
        existing_df.set_index('Job ID', inplace=True, drop=False)

    if 'Job ID' not in new_df.columns:
        new_df['Job ID'] = new_df['Job Link'].apply(compute_job_id)
    new_df.set_index('Job ID', inplace=True, drop=False)

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
        merged_df.update(new_df.loc[overlap_ids])
        merged_df = pd.concat([merged_df, added_df])

    merged_df = merged_df.fillna('')

    for col in JOB_SCHEMA:
        if col not in merged_df.columns:
            merged_df[col] = ''

    merged_df.reset_index(drop=True, inplace=True)
    ordered_cols = [col for col in JOB_SCHEMA if col in merged_df.columns]
    extra_cols = [col for col in merged_df.columns if col not in JOB_SCHEMA]
    merged_df = merged_df[ordered_cols + extra_cols]

    merged_df.to_excel(output_path, index=False)
    logger.info(f"\nSaved {len(merged_df)} total jobs to {output_path} (added {added}, updated {updated})")

    if supabase_client:
        upsert_jobs_to_supabase(supabase_client, merged_df)

    return merged_df


# ---------------------------------------------------------------------------
# split_jobs_by_experience — kept here for backward compatibility
# ---------------------------------------------------------------------------

def split_jobs_by_experience(
    jobs_df: pd.DataFrame,
    freshers_output: str = 'linkedin_freshers_jobs.xlsx',
    experienced_output: str = 'linkedin_1plus_jobs.xlsx',
) -> Dict:
    """Split jobs into freshers (0 / unknown) and 1+ years experience files.

    Args:
        jobs_df: DataFrame produced by :func:`run_multi_site_scraper`.
        freshers_output: Excel path for fresher / entry-level jobs.
        experienced_output: Excel path for 1+ years jobs.

    Returns:
        Dict with ``freshers`` and ``experienced_1plus`` counts.
    """
    import re

    if jobs_df is None or jobs_df.empty:
        return {'freshers': 0, 'experienced_1plus': 0}

    def infer_years(row: pd.Series) -> Optional[int]:
        years_raw = str(row.get('Years of Experience', '') or '').strip()
        match = re.search(r'\d{1,2}', years_raw)
        if match:
            return int(match.group(0))

        text = ' '.join([
            str(row.get('Title', '') or ''),
            str(row.get('Minimum Requirements', '') or ''),
            str(row.get('Job Description', '') or ''),
        ]).lower()

        if any(token in text for token in ['fresher', 'entry level', 'entry-level', 'intern', 'trainee', 'graduate program']):
            return 0

        range_match = re.search(r'(\d{1,2})\s*(?:to|[-–])\s*(\d{1,2})\s*\+?\s*years?', text)
        if range_match:
            return int(range_match.group(1))

        exp_match = re.search(r'(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp)', text)
        if exp_match:
            return int(exp_match.group(1))

        return None

    classified = jobs_df.copy()
    classified['__min_years'] = classified.apply(infer_years, axis=1)

    experienced_df = classified[
        classified['__min_years'].apply(lambda v: pd.notna(v) and float(v) >= 1)
    ].copy()
    freshers_df = classified[
        classified['__min_years'].apply(lambda v: pd.isna(v) or float(v) < 1)
    ].copy()

    freshers_df = freshers_df.drop(columns=['__min_years'])
    experienced_df = experienced_df.drop(columns=['__min_years'])

    freshers_df.to_excel(freshers_output, index=False)
    experienced_df.to_excel(experienced_output, index=False)

    logger.info(
        f"Saved split outputs: freshers={len(freshers_df)} to {freshers_output}, "
        f"1+ years={len(experienced_df)} to {experienced_output}"
    )

    return {
        'freshers': len(freshers_df),
        'experienced_1plus': len(experienced_df),
    }


if __name__ == '__main__':
    df = run_multi_site_scraper()
    if df is not None:
        print(f"\nTotal jobs scraped: {len(df)}")
        print(f"Sources: {df['Source'].unique()}")
        print(f"\nFirst few rows:")
        print(df.head())
