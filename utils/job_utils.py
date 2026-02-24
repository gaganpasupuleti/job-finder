"""
Core job utility functions.

Provides compute_job_id, validate_job_data, and JOB_SCHEMA used across
all scrapers and the database sync layer.
"""

import hashlib
import re
import logging
from typing import Dict
from urllib.parse import urlparse, urlencode, parse_qsl

logger = logging.getLogger(__name__)

# Standard job schema columns in display order
JOB_SCHEMA = [
    'Job ID',
    'Job Link',
    'Title',
    'Company',
    'Location',
    'Posted',
    'Minimum Requirements',
    'Good to Have',
    'Job Description',
    'Years of Experience',
    'Essential Keywords',
    'Salary Range',
    'Work Mode',
    'Source',
]

# Query-string parameters commonly used for tracking that should be stripped
# before hashing so that the same job gets the same ID regardless of UTM tags.
_TRACKING_PARAMS = frozenset({
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'ref', 'referral', 'trk', 'trkInfo', 'trackingId',
    'icid', 'cid', 'source', 'channel', 'eid',
})


def _normalize_url(url: str) -> str:
    """Strip trailing slashes and remove tracking query params.

    Args:
        url: Raw job URL.

    Returns:
        Cleaned URL suitable for stable hashing.
    """
    if not url:
        return url
    parsed = urlparse(url.strip())
    # Remove tracking params from query string
    clean_qs = urlencode(
        [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in _TRACKING_PARAMS]
    )
    normalized = parsed._replace(query=clean_qs, fragment='')
    return normalized.geturl().rstrip('/')


def compute_job_id(link: str) -> str:
    """Return a stable SHA-256 job ID derived from the canonical job URL.

    Tracking query parameters (utm_*, ref, trk, …) are stripped before
    hashing so the same job always gets the same ID even if the URL is shared
    with different tracking tokens.

    Args:
        link: Raw job URL.

    Returns:
        64-character hex string (SHA-256 digest).
    """
    canonical = _normalize_url(link)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def validate_job_data(job: Dict) -> bool:
    """Return True if *job* has the minimum required non-empty fields.

    Args:
        job: Job data dict.

    Returns:
        ``True`` when ``Job ID``, ``Job Link``, and ``Title`` are all
        present and non-empty; ``False`` otherwise.
    """
    required_fields = ['Job ID', 'Job Link', 'Title']
    return all(str(job.get(field, '')).strip() for field in required_fields)
