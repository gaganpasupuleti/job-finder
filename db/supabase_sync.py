"""
Supabase database sync utilities.
"""

import logging
import os
import time
import traceback
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


def get_supabase_client() -> Optional[object]:
    """Initialize Supabase client from environment variables.

    Returns:
        Supabase client or ``None`` when not configured / unavailable.
    """
    if not SUPABASE_AVAILABLE:
        logger.warning(
            "supabase not installed; skipping DB sync. "
            "Install with: pip install supabase"
        )
        return None

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')

    if not url or not key:
        logger.warning(
            "SUPABASE_URL or SUPABASE_KEY env var not set; skipping DB sync. "
            "Set them in .env file or environment."
        )
        return None

    try:
        client = create_client(url, key)
        logger.info(f"Supabase client initialized for {url}")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        return None


def _to_standard_job_schema(row: dict) -> dict:
    """Map a Supabase jobs-row dict to the common in-memory job schema."""
    return {
        'Job ID': str(row.get('job_id', '') or ''),
        'Job Link': str(row.get('job_link', '') or ''),
        'Title': str(row.get('title', '') or ''),
        'Company': str(row.get('company', '') or ''),
        'Location': str(row.get('location', '') or ''),
        'Posted': str(row.get('posted', '') or ''),
        'Minimum Requirements': str(row.get('minimum_requirements', '') or ''),
        'Good to Have': str(row.get('good_to_have', '') or ''),
        'Job Description': str(row.get('job_description', '') or ''),
        'Years of Experience': str(row.get('years_of_experience', '') or ''),
        'Essential Keywords': str(row.get('essential_keywords', '') or ''),
        'Salary Range': str(row.get('salary_range', '') or ''),
        'Work Mode': str(row.get('work_mode', '') or ''),
        'Source': str(row.get('source', '') or ''),
    }


def fetch_recent_cached_jobs(
    client: object,
    *,
    keywords: str,
    location: str,
    source: str = 'LinkedIn',
    max_age_hours: int = 24,
    limit: int = 300,
) -> List[dict]:
    """Return recently scraped jobs for a keyword/location combination.

    This is used as a pre-scrape cache check to avoid unnecessary browser/API
    calls when equivalent data already exists in the previous 24 hours.
    """
    if client is None:
        return []

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        resp = (
            client.table('jobs')
            .select(
                'job_id,job_link,title,company,location,posted,minimum_requirements,'
                'good_to_have,job_description,years_of_experience,essential_keywords,'
                'salary_range,work_mode,source,scraped_at'
            )
            .eq('source', source)
            .ilike('location', f"%{location}%")
            .gte('scraped_at', cutoff)
            .limit(limit)
            .execute()
        )

        rows = resp.data or []
        if not rows:
            return []

        terms = [
            token.strip().lower()
            for token in str(keywords).replace('(', ' ').replace(')', ' ').split('OR')
            if token.strip()
        ]
        # Remove wrapping quotes from boolean terms.
        terms = [t.strip().strip('"\'') for t in terms if t.strip().strip('"\'')]

        filtered: List[dict] = []
        for row in rows:
            searchable = ' '.join([
                str(row.get('title', '') or ''),
                str(row.get('essential_keywords', '') or ''),
                str(row.get('job_description', '') or ''),
            ]).lower()

            if terms and not any(term in searchable for term in terms):
                continue
            filtered.append(_to_standard_job_schema(row))

        logger.info(
            f"Cache lookup for source={source}, location={location}, terms={terms}: "
            f"{len(filtered)} hit(s)"
        )
        return filtered
    except Exception as e:
        logger.warning(f"Pre-scrape cache check failed; proceeding with fresh scrape: {e}")
        return []


def upsert_jobs_to_supabase(client: object, jobs_df: pd.DataFrame) -> None:
    """Upsert jobs to Supabase.  Updates if job_id exists, inserts if new.

    Args:
        client: Supabase client returned by :func:`get_supabase_client`.
        jobs_df: DataFrame of jobs with columns matching ``JOB_SCHEMA``.
    """
    if client is None or jobs_df.empty:
        return

    try:
        timestamp = datetime.now(timezone.utc).isoformat()

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
                'salary_range': str(row.get('Salary Range', '')),
                'work_mode': str(row.get('Work Mode', '')),
                'source': str(row.get('Source', '')),
                'scraped_at': timestamp,
            })

        batch_size = 50
        total_rows = len(rows)
        total_batches = (total_rows + batch_size - 1) // batch_size

        for i in range(0, total_rows, batch_size):
            batch = rows[i:i + batch_size]
            batch_num = (i // batch_size) + 1

            try:
                client.table('jobs').upsert(
                    batch,
                    on_conflict='job_id',
                    returning='minimal',
                ).execute()
                logger.info(f"Upserted batch {batch_num}/{total_batches} ({len(batch)} rows) to Supabase")

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
