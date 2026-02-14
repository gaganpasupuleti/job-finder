#!/usr/bin/env python3
"""
Main entry point for multi-site job scraper.

Usage:
    python main.py                  # Run with default settings (headless mode)
    python main.py --headful        # Run with visible browser window
    python main.py --save-linkedin  # Save LinkedIn authentication state (requires LINKEDIN_USER/LINKEDIN_PASS env vars)
"""

import sys
import argparse
from multi_site_scraper import run_multi_site_scraper, save_linkedin_storage_state

def main():
    parser = argparse.ArgumentParser(description='Multi-site job scraper (Amazon, P&G, LinkedIn)')
    parser.add_argument(
        '--headful', 
        action='store_true', 
        help='Run browser in headful mode (show window)'
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
    
    # Run the multi-site scraper
    headless = not args.headful
    print(f"Starting multi-site job scraper (headless={headless})...")
    print("Scraping Amazon, P&G Careers, and LinkedIn...\n")
    
    df = run_multi_site_scraper(headless=headless)
    
    if df is not None:
        print(f"\n✓ Success! Scraped {len(df)} total jobs")
        print(f"  Sources: {', '.join(df['Source'].unique())}")
        print(f"  Saved to: multi_site_jobs.xlsx\n")
        print("First 5 jobs:")
        print(df[['Title', 'Location', 'Source']].head().to_string())
    else:
        print("✗ No jobs were scraped. Check logs above.")
        sys.exit(1)

if __name__ == '__main__':
    main()
