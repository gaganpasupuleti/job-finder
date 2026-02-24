"""
Experience extraction utilities.

Extracts years of experience from free-form job description text using
regex patterns, word-to-number conversion, and seniority-level inference.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Map written numbers to integers (1-20)
_WORD_TO_NUM = {
    'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20,
}

# Seniority keywords → approximate min years
_SENIORITY_YEARS = {
    'intern': 0,
    'internship': 0,
    'fresher': 0,
    'entry level': 0,
    'entry-level': 0,
    'junior': 1,
    'associate': 1,
    'mid level': 3,
    'mid-level': 3,
    'senior': 5,
    'staff': 5,
    'lead': 6,
    'principal': 8,
    'architect': 8,
    'distinguished': 10,
    'fellow': 10,
    'director': 10,
    'vp': 12,
    'vice president': 12,
}

# Confidence levels
HIGH = 'high'
MEDIUM = 'medium'
LOW = 'low'
INFERRED = 'inferred'

_YRS = r'(?:years?|yrs?)'
_EXP = r'(?:relevant\s*)?(?:professional\s*)?(?:work\s*)?(?:experience|exp(?:erience)?)'

# Words that introduce a minimum/lower-bound number
_AT_LEAST = r'(?:minimum(?:\s+of)?|at\s+least|over|more\s+than|greater\s+than|minimum)'

_RANGE_PATTERNS = [
    # "3+ to 5 years of experience", "3-5 years exp", "three to five years"
    re.compile(
        r'(\d{1,2}|\b(?:' + '|'.join(_WORD_TO_NUM) + r')\b)'
        r'\s*\+?\s*(?:to|[-–])\s*'
        r'(\d{1,2}|\b(?:' + '|'.join(_WORD_TO_NUM) + r')\b)'
        r'\s*\+?\s*' + _YRS + r'\s*(?:of\s*)?' + _EXP,
        re.IGNORECASE
    ),
    # "3 to 5 years"  (without explicit "experience")
    re.compile(
        r'(\d{1,2})\s*(?:to|[-–])\s*(\d{1,2})\s*\+?\s*' + _YRS,
        re.IGNORECASE
    ),
]

_SINGLE_PATTERNS = [
    # "minimum of 3+ years of experience"
    re.compile(
        _AT_LEAST + r'?\s*(\d{1,2})\s*\+?\s*' + _YRS + r'\s*(?:of\s*)?' + _EXP,
        re.IGNORECASE
    ),
    # "3+ years experience"
    re.compile(
        r'(\d{1,2})\s*\+\s*' + _YRS + r'(?:\s*(?:of\s*)?' + _EXP + r')?',
        re.IGNORECASE
    ),
    # "3 years of experience"
    re.compile(
        r'(\d{1,2})\s*' + _YRS + r'\s*(?:of\s*)?' + _EXP,
        re.IGNORECASE
    ),
    # "3 yrs exp"
    re.compile(
        r'(\d{1,2})\s*\+?\s*' + _YRS + r'\s*' + _EXP,
        re.IGNORECASE
    ),
    # "experience of 3 years"
    re.compile(
        _EXP + r'\s*(?:of\s*)?(\d{1,2})\s*\+?\s*' + _YRS,
        re.IGNORECASE
    ),
    # "experience: 3 years"
    re.compile(
        r'experience\s*[:\-]\s*(\d{1,2})\s*\+?\s*' + _YRS,
        re.IGNORECASE
    ),
    # Written numbers: "three years of experience"
    re.compile(
        r'\b(' + '|'.join(_WORD_TO_NUM) + r')\s+(?:to\s+(?:' + '|'.join(_WORD_TO_NUM) + r')\s+)?' + _YRS + r'\s*(?:of\s*)?' + _EXP,
        re.IGNORECASE
    ),
]


def _parse_num(token: str) -> Optional[int]:
    """Convert numeric string or English word to int."""
    token = token.strip().lower()
    if token in _WORD_TO_NUM:
        return _WORD_TO_NUM[token]
    try:
        return int(token)
    except ValueError:
        return None


def extract_years_of_experience(text: str, title: str = '') -> str:
    """Extract minimum years of experience from job text.

    Tries explicit numeric ranges first, then single numbers, then falls back
    to seniority-level inference from *title* keywords.  Returns the minimum
    as a plain string (e.g. ``"3"``) or ``""`` when nothing is found.

    For richer structured output use :func:`extract_experience_structured`.

    Args:
        text: Job description / requirements body text.
        title: Optional job title for seniority inference.

    Returns:
        Minimum years as a string, or ``""`` if not detected.
    """
    result = extract_experience_structured(text, title)
    if result['min_years'] is not None:
        return str(result['min_years'])
    return ''


def extract_experience_structured(text: str, title: str = '') -> dict:
    """Return a rich dict describing the experience requirement.

    Keys:
        min_years (int | None): Minimum years required.
        max_years (int | None): Maximum years (from range), or None.
        raw_match (str): The substring that triggered the match.
        confidence (str): 'high', 'medium', 'low', or 'inferred'.

    Args:
        text: Combined job description / requirements text.
        title: Optional job title used for seniority-level inference.
    """
    result = {'min_years': None, 'max_years': None, 'raw_match': '', 'confidence': LOW}

    if not text:
        return _infer_from_title(title, result)

    normalized = re.sub(r'\s+', ' ', text.lower())

    # --- 1. Explicit ranges ---
    for pattern in _RANGE_PATTERNS:
        m = pattern.search(normalized)
        if m:
            lo = _parse_num(m.group(1))
            hi = _parse_num(m.group(2))
            if lo is not None and 0 <= lo <= 40:
                result['min_years'] = lo
                result['max_years'] = hi if (hi and hi > lo) else None
                result['raw_match'] = m.group(0)
                result['confidence'] = HIGH
                return result

    # --- 2. Single explicit numbers ---
    for pattern in _SINGLE_PATTERNS:
        for m in pattern.finditer(normalized):
            # The capture group index differs per pattern; group(1) is always the year digit
            val = _parse_num(m.group(1))
            if val is not None and 0 < val <= 40:
                result['min_years'] = val
                result['raw_match'] = m.group(0)
                result['confidence'] = HIGH
                return result

    # --- 3. Entry-level / fresher explicit phrases ---
    fresher_patterns = [
        r'\b(?:freshers?|entry[- ]level|no experience required|0\s*(?:to|[-–])\s*\d+\s*year)\b',
        r'\brecent\s+graduate\b',
        r'\bgraduate\s+program\b',
    ]
    for pat in fresher_patterns:
        m = re.search(pat, normalized)
        if m:
            result['min_years'] = 0
            result['raw_match'] = m.group(0)
            result['confidence'] = MEDIUM
            return result

    # --- 4. Seniority inference from text body ---
    for phrase, years in _SENIORITY_YEARS.items():
        if re.search(r'\b' + re.escape(phrase) + r'\b', normalized):
            result['min_years'] = years
            result['raw_match'] = phrase
            result['confidence'] = INFERRED
            return result

    return _infer_from_title(title, result)


def _infer_from_title(title: str, result: dict) -> dict:
    """Attempt seniority inference from job title."""
    if not title:
        return result
    title_lower = title.lower()
    for phrase, years in _SENIORITY_YEARS.items():
        if re.search(r'\b' + re.escape(phrase) + r'\b', title_lower):
            result['min_years'] = years
            result['raw_match'] = phrase
            result['confidence'] = INFERRED
            return result
    return result
