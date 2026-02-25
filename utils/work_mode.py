"""
Work mode (Remote / Hybrid / On-site) detection utilities.
"""

import re
import logging

logger = logging.getLogger(__name__)

_REMOTE_PATTERNS = [
    r'\bremote\b', r'\bwork\s+from\s+home\b', r'\bwfh\b',
    r'\bfully\s+remote\b', r'\b100%\s+remote\b', r'\bremote[\s-]first\b',
    r'\bwork\s+anywhere\b', r'\bdistributed\s+team\b',
]

_HYBRID_PATTERNS = [
    r'\bhybrid\b', r'\bhybrid\s+work\b', r'\bhybrid\s+remote\b',
    r'\bflexible\s+work(?:ing)?\s+(?:arrangement|option|model)\b',
    r'\bpartially\s+remote\b', r'\b\d+\s+days?\s+(?:in|at)\s+office\b',
]

_ONSITE_PATTERNS = [
    r'\bon[\s-]?site\b', r'\bin[\s-]?office\b', r'\bin[\s-]?person\b',
    r'\bon[\s-]?location\b', r'\bpresence\s+required\b',
    r'\bmust\s+be\s+(?:present|located)\s+in\b',
    r'\bno\s+remote\b', r'\boffice[\s-]based\b',
]


def _matches(text: str, patterns: list) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def detect_work_mode(text: str, location: str = '') -> str:
    """Detect whether a job is Remote, Hybrid, On-site, or Unknown.

    Checks the job description *and* location string for keywords.

    Args:
        text: Job description / requirements body.
        location: Optional location string from the job posting.

    Returns:
        One of ``"Remote"``, ``"Hybrid"``, ``"On-site"``, ``"Unknown"``.
    """
    combined = f"{text} {location}"

    if _matches(combined, _REMOTE_PATTERNS):
        return 'Remote'
    if _matches(combined, _HYBRID_PATTERNS):
        return 'Hybrid'
    if _matches(combined, _ONSITE_PATTERNS):
        return 'On-site'
    return 'Unknown'
