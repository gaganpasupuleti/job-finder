"""
Supabase database sync utilities.
"""

import logging
import os
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

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
