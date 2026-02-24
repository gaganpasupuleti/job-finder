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
    python main.py --enable-linkedin --sites linkedin --linkedin-keywords "data engineer" --linkedin-location "India"
                                                    # Pull LinkedIn job listings using LinkedIn source
    python main.py --save-linkedin                  # Save LinkedIn authentication state (requires LINKEDIN_USER/LINKEDIN_PASS env vars)
"""

import sys
import argparse
from multi_site_scraper import (
    run_multi_site_scraper,
    save_linkedin_storage_state,
    export_sites_from_pdf,
    split_jobs_by_experience,
)

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
    parser.add_argument(
        '--enable-linkedin',
        action='store_true',
        help='Enable LinkedIn site scraping in this run (disabled by default)'
    )
    parser.add_argument(
        '--linkedin-keywords',
        type=str,
        default='software engineer',
        help='LinkedIn search keywords (default: software engineer)'
    )
    parser.add_argument(
        '--linkedin-location',
        type=str,
        default='India',
        help='LinkedIn search location (default: India)'
    )
    parser.add_argument(
        '--linkedin-max-jobs',
        type=int,
        default=50,
        help='Maximum LinkedIn jobs to process (default: 50)'
    )
    parser.add_argument(
        '--linkedin-storage-state',
        type=str,
        default='linkedin_state.json',
        help='Path to LinkedIn Playwright storage state file (default: linkedin_state.json)'
    )
    parser.add_argument(
        '--split-experience',
        action='store_true',
        help='Split scraped jobs into two Excel files: freshers and 1+ years'
    )
    parser.add_argument(
        '--freshers-output',
        type=str,
        default='linkedin_freshers_jobs.xlsx',
        help='Output Excel file for freshers/entry-level jobs'
    )
    parser.add_argument(
        '--experienced-output',
        type=str,
        default='linkedin_1plus_jobs.xlsx',
        help='Output Excel file for jobs requiring 1+ years experience'
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
    if args.enable_linkedin:
        print(
            f"LinkedIn enabled: keywords='{args.linkedin_keywords}', "
            f"location='{args.linkedin_location}', max_jobs={args.linkedin_max_jobs}"
        )
    print()
    
    df = run_multi_site_scraper(
        headless=headless,
        site_filter=site_filter,
        output_file=args.output,
        sites_file=args.sites_file,
        linkedin_enabled=args.enable_linkedin,
        linkedin_keywords=args.linkedin_keywords,
        linkedin_location=args.linkedin_location,
        linkedin_max_jobs=args.linkedin_max_jobs,
        linkedin_storage_state=args.linkedin_storage_state
    )
    
    if df is not None:
        print(f"\n✓ Success! Scraped {len(df)} total jobs")
        print(f"  Sources: {', '.join(df['Source'].unique())}")
        print(f"  Saved to: {args.output}\n")

        if args.split_experience:
            split_counts = split_jobs_by_experience(
                df,
                freshers_output=args.freshers_output,
                experienced_output=args.experienced_output
            )
            print(
                f"  Split files: {args.freshers_output} (freshers={split_counts['freshers']}), "
                f"{args.experienced_output} (1+ years={split_counts['experienced_1plus']})\n"
            )

        print("First 5 jobs:")
        print(df[['Title', 'Company', 'Location', 'Source']].head().to_string())
    else:
        print("✗ No jobs were scraped. Check logs above.")
        sys.exit(1)

if __name__ == '__main__':
    main()
