"""
Filter profile cache and generic link-filter utilities.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

FILTER_PROFILE_CACHE_FILE = 'site_filter_profiles.json'

DEFAULT_GENERIC_FILTERS: Dict = {
    'include_patterns': ['/job', '/jobs', '/search', 'workdayjobs', 'greenhouse.io', 'lever.co'],
    'exclude_patterns': ['/about', '/blog', '/news', '/event', '/privacy', '/terms', '/contact', '/investor'],
    'title_must_contain': [],
    'max_jobs': 20,
}


def get_site_profile_key(url: str) -> str:
    """Return a stable cache key for a site based on its hostname.

    Args:
        url: Site URL.

    Returns:
        Lower-case hostname without ``www.`` prefix.
    """
    parsed = urlparse(url)
    return parsed.netloc.lower().replace('www.', '').strip()


def load_filter_profiles(cache_file: str = FILTER_PROFILE_CACHE_FILE) -> Dict[str, Dict]:
    """Load cached per-site filter profiles from disk.

    Args:
        cache_file: Path to the JSON cache file.

    Returns:
        Dict mapping site keys to their filter dicts.
    """
    path = Path(cache_file)
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to read filter profile cache '{cache_file}': {e}")
        return {}


def save_filter_profiles(
    profiles: Dict[str, Dict],
    cache_file: str = FILTER_PROFILE_CACHE_FILE,
) -> None:
    """Persist per-site filter profiles for future runs.

    Args:
        profiles: Dict mapping site keys to filter dicts.
        cache_file: Destination JSON path.
    """
    try:
        Path(cache_file).write_text(json.dumps(profiles, indent=2), encoding='utf-8')
        logger.info(f"Saved filter profiles to {cache_file}")
    except Exception as e:
        logger.warning(f"Failed to write filter profile cache '{cache_file}': {e}")
