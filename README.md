# Job Finder - Multi-Site Job Scraper

A powerful, automated job scraper built with Python and Playwright that extracts job listings from multiple career sites and syncs them to a database.

## 🌟 Features

- **Multi-site Support**: Scrapes jobs from:
  - Amazon Careers
  - P&G Careers
  - LinkedIn Jobs (currently disabled pending auth flow finalization)
- **Smart Data Extraction**: Automatically extracts:
  - Job titles, companies, locations
  - Years of experience required
  - Essential technical keywords and skills
  - Full job descriptions
  - Minimum requirements and preferred qualifications
- **Excel Export**: Saves all jobs to a consolidated Excel file with automatic deduplication
- **Database Sync**: Optional Supabase integration for persistent storage
- **Incremental Updates**: Merges new job listings with existing data
- **CLI Flexibility**: Filter by site, customize output, run in headless or visible mode
- **Bring Your Own Site List**: Load additional company career URLs from CSV/XLSX/JSON

## 📋 Prerequisites

- **Python 3.9+**
- **Playwright browsers** (Chromium will be installed automatically)

## 🚀 Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/gaganpasupuleti/job-finder.git
   cd job-finder
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers**:
   ```bash
   playwright install chromium
   ```

4. **(Optional) Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your Supabase credentials if using database sync
   ```

## 💻 Usage

### Basic Usage

Run the scraper with default settings (scrapes all enabled sites):
```bash
python main.py
```

### Advanced Options

**Run with visible browser** (useful for debugging):
```bash
python main.py --headful
```

**Scrape specific sites only**:
```bash
python main.py --sites amazon,pg_careers
```

**Specify custom output filename**:
```bash
python main.py --output my_jobs.xlsx
```

**Include additional company career sites from file**:
```bash
python main.py --sites-file "C:/path/to/companies.xlsx"
```

**Extract URLs from a companies PDF into JSON**:
```bash
python main.py --extract-sites-pdf "C:/path/to/companies.pdf" --sites-output "companies.json"
```

**Use extracted JSON together with existing sites**:
```bash
python main.py --sites-file "companies.json"
```

**Combine multiple options**:
```bash
python main.py --headful --sites amazon --output amazon_jobs.xlsx
```

**Run LinkedIn source scraping**:
```bash
python main.py --enable-linkedin --sites linkedin --linkedin-keywords "data engineer" --linkedin-location "India" --linkedin-max-jobs 40
```

**Generate separate Excel files for freshers and 1+ years**:
```bash
python main.py --enable-linkedin --sites linkedin --linkedin-keywords "software engineer" --linkedin-location "India" --linkedin-max-jobs 100 --output linkedin_jobs.xlsx --split-experience --freshers-output linkedin_freshers_jobs.xlsx --experienced-output linkedin_1plus_jobs.xlsx
```

### Additional Sites File Format

Supported formats for `--sites-file`: `.csv`, `.xlsx`, `.json`

- For CSV/XLSX/JSON, include at least a URL column: `url` (or `career_url`, `careers_url`, `site`)
- Optional columns: `name`, `type`, `enabled`
- Unsupported `type` values automatically fallback to `generic`
- For PDF input, first run `--extract-sites-pdf` to generate a JSON file, then pass that JSON to `--sites-file`

### LinkedIn Authentication (Optional)

To enable LinkedIn scraping with authentication:

1. Set environment variables:
   ```bash
   export LINKEDIN_USER=your-email@example.com
   export LINKEDIN_PASS=your-password
   ```

2. Save authentication state:
   ```bash
   python main.py --save-linkedin
   ```

3. Run LinkedIn scraping (uses `linkedin_state.json` by default):
   ```bash
   python main.py --enable-linkedin --sites linkedin --linkedin-keywords "software engineer" --linkedin-location "India"
   ```

4. If your storage state file is custom, pass it explicitly:
   ```bash
   python main.py --enable-linkedin --sites linkedin --linkedin-storage-state my_linkedin_state.json
   ```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SUPABASE_URL` | Your Supabase project URL | No (for DB sync) |
| `SUPABASE_KEY` | Your Supabase anon/service key | No (for DB sync) |
| `LINKEDIN_USER` | LinkedIn email for authentication | No (for LinkedIn) |
| `LINKEDIN_PASS` | LinkedIn password | No (for LinkedIn) |

### Enabling/Disabling Sites

Edit `multi_site_scraper.py` and modify the `sites` list in `run_multi_site_scraper()`:
```python
{
    'name': 'LinkedIn Jobs',
    'type': 'linkedin',
    'url': '...',
    'enabled': True,  # Change to True to enable
    'storage_state': 'linkedin_state.json'
}
```

## 📊 Output Schema

The scraper generates data with the following columns:

| Column | Description | Type |
|--------|-------------|------|
| `Job ID` | Unique identifier (hash of job link) | Text |
| `Job Link` | Direct URL to job posting | Text |
| `Title` | Job title | Text |
| `Company` | Company name | Text |
| `Location` | Job location | Text |
| `Posted` | Posted date/time | Text |
| `Minimum Requirements` | Required qualifications | Text |
| `Good to Have` | Preferred qualifications | Text |
| `Job Description` | Full or truncated description | Text |
| `Years of Experience` | Extracted experience requirement (e.g., "3-5", "2") | Text |
| `Essential Keywords` | Extracted technical skills (e.g., "Python, AWS, Docker") | Text |
| `Source` | Source site name | Text |

### Database Schema (Supabase)

For database sync, create a table with these columns:

```sql
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  job_link TEXT,
  title TEXT,
  company TEXT,
  location TEXT,
  posted TEXT,
  minimum_requirements TEXT,
  good_to_have TEXT,
  job_description TEXT,
  years_of_experience TEXT,
  essential_keywords TEXT,
  source TEXT,
  scraped_at TIMESTAMP
);
```

## 📁 Project Structure

```
job-finder/
├── main.py                    # CLI entry point
├── multi_site_scraper.py      # Core scraping logic
├── requirements.txt           # Python dependencies
├── .env.example              # Environment variable template
├── .gitignore                # Git ignore rules
├── README.md                 # This file
└── multi_site_jobs.xlsx      # Generated output (gitignored)
```

## ⚠️ Important Notes

- **LinkedIn scraping is currently disabled** pending finalization of the authentication flow
- LinkedIn code remains intact and can be re-enabled when ready
- The scraper respects rate limits with delays between requests
- Generated Excel files are automatically excluded from git (see `.gitignore`)
- Authentication state files (`linkedin_state.json`) contain sensitive session cookies and should never be committed

## 🐛 Troubleshooting

**"No jobs were scraped"**: 
- Check your internet connection
- Try running with `--headful` to see what's happening
- Some sites may have changed their HTML structure

**Playwright browser not found**:
```bash
playwright install chromium
```

**Supabase errors**:
- Verify your `SUPABASE_URL` and `SUPABASE_KEY` in `.env`
- Ensure your database table schema matches the expected structure

## 📝 License

This project is open source and available for educational purposes.

## 🤝 Contributing

Contributions are welcome! Please ensure:
- Code follows existing patterns
- All scrapers include the full job schema
- Changes don't break existing functionality

## 📧 Contact

For questions or issues, please open an issue on GitHub.
