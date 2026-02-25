"""
Salary extraction utilities.

Detects and extracts salary/compensation ranges from job description text.
Supports various currencies and formats (USD, INR LPA, GBP, EUR, K-notation, etc.).
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Each pattern: (regex, description)
_SALARY_PATTERNS = [
    # $120,000 - $180,000 or $120k-$180k
    re.compile(
        r'\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?[kKmM]?)\s*(?:[-–]|to)\s*\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?[kKmM]?)',
        re.IGNORECASE
    ),
    # 120K-180K  or  120,000-180,000
    re.compile(
        r'\b(\d{1,3}(?:,\d{3})*(?:\.\d+)?[kK])\s*(?:[-–]|to)\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?[kK])\b',
        re.IGNORECASE
    ),
    # ₹12-18 LPA or 12-18 LPA
    re.compile(
        r'[₹]?\s*(\d{1,3}(?:\.\d+)?)\s*(?:[-–]|to)\s*(\d{1,3}(?:\.\d+)?)\s*LPA',
        re.IGNORECASE
    ),
    # CTC: 12-18 LPA
    re.compile(
        r'CTC\s*[:\-]?\s*[₹]?\s*(\d{1,3}(?:\.\d+)?)\s*(?:[-–]|to)\s*(\d{1,3}(?:\.\d+)?)\s*LPA',
        re.IGNORECASE
    ),
    # £50k-£70k  or  €50k-€70k
    re.compile(
        r'[£€]\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?[kK]?)\s*(?:[-–]|to)\s*[£€]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?[kK]?)',
        re.IGNORECASE
    ),
    # Single value: $120,000/year or $120k/yr
    re.compile(
        r'\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?[kKmM]?)\s*(?:/\s*(?:year|yr|annum|annual|mo(?:nth)?))',
        re.IGNORECASE
    ),
]


def extract_salary(text: str) -> str:
    """Extract a salary range string from job text.

    Returns the first detected salary range as a human-readable string,
    or an empty string if none is found.

    Args:
        text: Job description or combined requirements text.

    Returns:
        Salary range string (e.g. ``"$120,000 - $180,000"``), or ``""``.
    """
    if not text:
        return ''

    normalized = re.sub(r'\s+', ' ', text)

    for pattern in _SALARY_PATTERNS:
        m = pattern.search(normalized)
        if m:
            return m.group(0).strip()

    return ''
