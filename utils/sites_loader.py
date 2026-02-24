"""
Site-loading utilities.

Handles CSV / XLSX / JSON site config files and PDF URL extraction.
Also provides ``derive_name_from_url`` and ``normalize_site_type``.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import pandas as pd

logger = logging.getLogger(__name__)


def normalize_site_type(site_type: str) -> str:
    """Normalise site type; fall back to ``'generic'`` for unsupported values.

    Args:
        site_type: Raw site-type string from config file.

    Returns:
        One of ``'amazon'``, ``'pg_careers'``, ``'linkedin'``, ``'generic'``.
    """
    supported = {'amazon', 'pg_careers', 'linkedin', 'generic'}
    normalized = (site_type or '').strip().lower()
    return normalized if normalized in supported else 'generic'


def derive_name_from_url(url: str) -> str:
    """Build a human-readable site name from a URL's hostname.

    Args:
        url: Career site URL.

    Returns:
        A title-cased name ending in ``" Careers"``
        (e.g. ``"Acme Corp Careers"``).
    """
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
    """Extract unique career-site URLs from a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Ordered list of unique URLs found in the document.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning(
            "pypdf not installed; cannot parse PDF sites file. "
            "Install with: pip install pypdf"
        )
        return []

    try:
        reader = PdfReader(pdf_path)
        text_chunks = [page.extract_text() or '' for page in reader.pages]
        text = ' '.join(text_chunks)
    except Exception as e:
        logger.error(f"Failed to parse PDF sites file '{pdf_path}': {e}")
        return []

    candidates = re.findall(r'https?://[^\s\]\[\)\("\'<>]+', text)
    cleaned = [url.strip().rstrip('.,;:') for url in candidates if url.strip()]
    return list(dict.fromkeys(cleaned))


def load_additional_sites(sites_file: str) -> List[Dict]:
    """Load additional site configs from a CSV / XLSX / JSON file.

    Expected columns (case-insensitive):
        ``url`` (required), ``name``, ``type``, ``enabled``.

    Args:
        sites_file: Path to CSV, XLSX, or JSON file.

    Returns:
        List of site-config dicts suitable for the scraper loop.
    """
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
            "Extract URLs first using --extract-sites-pdf and then pass the "
            "generated JSON file to --sites-file."
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
            logger.warning(
                f"Unsupported sites file format: {sites_file}. Use CSV, XLSX, or JSON"
            )
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
        logger.warning(
            f"Sites file '{sites_file}' is missing URL column "
            "(expected: url/career_url/careers_url/site)"
        )
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

        site_type = normalize_site_type(
            str(row.get(type_col, '')).strip() if type_col else 'generic'
        )

        enabled = True
        if enabled_col:
            enabled_value = str(row.get(enabled_col, 'true')).strip().lower()
            enabled = enabled_value in ('1', 'true', 'yes', 'y')

        sites.append({
            'name': site_name,
            'type': site_type,
            'url': url,
            'enabled': enabled,
        })

    logger.info(f"Loaded {len(sites)} additional sites from {sites_file}")
    return sites


def export_sites_from_pdf(pdf_path: str, output_file: str = 'extracted_company_sites.json') -> int:
    """Extract site URLs from a PDF and save them as generic site configs.

    Args:
        pdf_path: Path to the PDF file.
        output_file: Destination JSON path (default: ``'extracted_company_sites.json'``).

    Returns:
        Number of sites extracted (0 on failure).
    """
    urls = extract_urls_from_pdf(pdf_path)
    if not urls:
        return 0

    sites = [
        {
            'name': derive_name_from_url(url),
            'type': 'generic',
            'url': url,
            'enabled': True,
        }
        for url in urls
    ]

    output_path = Path(output_file)
    output_path.write_text(json.dumps(sites, indent=2), encoding='utf-8')
    logger.info(f"Saved {len(sites)} extracted sites to {output_path}")
    return len(sites)
