#!/usr/bin/env python3
"""
Main entry point for multi-site job scraper.

Usage:
    python main.py                                  # Run with default settings (headless mode)
    python main.py --headful                        # Run with visible browser window
    python main.py --sites amazon,pg                # Scrape only specific sites
    python main.py --extract-sites-pdf companies.pdf --sites-output companies.json
                                                    # Extract career URLs from PDF into JSON
    python main.py --sites-file companies.json      # Include extra career sites from JSON/CSV/XLSX
    python main.py --output my_jobs.xlsx            # Save to custom filename
    python main.py --save-linkedin                  # Save LinkedIn authentication state (requires LINKEDIN_USER/LINKEDIN_PASS env vars)
"""

import sys
import argparse
from multi_site_scraper import run_multi_site_scraper, save_linkedin_storage_state, export_sites_from_pdf

def main():
    parser = argparse.ArgumentParser(description='Multi-site job scraper (Amazon, P&G, LinkedIn)')
    parser.add_argument(
        '--headful', 
        action='store_true', 
        help='Run browser in headful mode (show window)'
    )
    parser.add_argument(
        '--sites',
        type=str,
        help='Comma-separated list of sites to scrape (e.g., amazon,pg_careers,linkedin). Default: all enabled sites'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='multi_site_jobs.xlsx',
        help='Output Excel filename (default: multi_site_jobs.xlsx)'
    )
    parser.add_argument(
        '--sites-file',
        type=str,
        help='Optional CSV/XLSX/JSON file containing additional company career sites to scrape'
    )
    parser.add_argument(
        '--extract-sites-pdf',
        type=str,
        help='Extract company career URLs from a PDF file and save as JSON, then use that JSON with --sites-file'
    )
    parser.add_argument(
        '--sites-output',
        type=str,
        default='extracted_company_sites.json',
        help='Output JSON file for --extract-sites-pdf (default: extracted_company_sites.json)'
    )
    parser.add_argument(
        '--save-linkedin', 
        action='store_true', 
        help='Save LinkedIn authentication state (requires LINKEDIN_USER and LINKEDIN_PASS env vars)'
    )
    
    args = parser.parse_args()
    
    if args.save_linkedin:
        print("Saving LinkedIn authentication state...")
        success = save_linkedin_storage_state('linkedin_state.json')
        if success:
            print("✓ LinkedIn storage state saved to 'linkedin_state.json'")
            print("  You can now run the scraper with authenticated LinkedIn access.")
        else:
            print("✗ Failed to save LinkedIn state. Check LINKEDIN_USER and LINKEDIN_PASS env vars.")
        return

    if args.extract_sites_pdf:
        print(f"Extracting site URLs from PDF: {args.extract_sites_pdf}")
        count = export_sites_from_pdf(args.extract_sites_pdf, args.sites_output)
        if count > 0:
            print(f"✓ Extracted {count} sites to '{args.sites_output}'")
            print(f"  Next run: python main.py --sites-file {args.sites_output}")
        else:
            print("✗ No sites extracted from PDF. Check file path/content.")
            sys.exit(1)
        return
    
    # Parse site filter
    site_filter = None
    if args.sites:
        site_filter = [s.strip() for s in args.sites.split(',')]
        print(f"Filtering to sites: {', '.join(site_filter)}")
    
    # Run the multi-site scraper
    headless = not args.headful
    print(f"Starting multi-site job scraper (headless={headless})...")
    print("Scraping Amazon, P&G Careers, and LinkedIn (if enabled)...")
    if args.sites_file:
        print(f"Including additional sites from: {args.sites_file}")
    print()
    
    df = run_multi_site_scraper(
        headless=headless,
        site_filter=site_filter,
        output_file=args.output,
        sites_file=args.sites_file
    )
    
    if df is not None:
        print(f"\n✓ Success! Scraped {len(df)} total jobs")
        print(f"  Sources: {', '.join(df['Source'].unique())}")
        print(f"  Saved to: {args.output}\n")
        print("First 5 jobs:")
        print(df[['Title', 'Company', 'Location', 'Source']].head().to_string())
    else:
        print("✗ No jobs were scraped. Check logs above.")
        sys.exit(1)

if __name__ == '__main__':
    main()
