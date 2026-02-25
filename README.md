# Job Finder - Multi-Site Job Scraper

A powerful, automated job scraper built with Python and Playwright that extracts job listings from multiple career sites and syncs them to a database.

## 🌟 Features

- **Multi-site Support**: Scrapes jobs from:
  - Amazon Careers
  - P&G Careers
  - LinkedIn Jobs (requires `--save-linkedin` auth step first)
  - Any generic career site via CSV/XLSX/JSON/PDF site lists
- **Smart Data Extraction**: Automatically extracts:
  - Job titles, companies, locations
  - Years of experience required (with word-to-number and seniority inference)
  - 200+ technical keywords and skills across 10 categories
  - Salary range (USD, INR LPA, GBP, K-notation, …)
  - Work mode (Remote / Hybrid / On-site / Unknown)
  - Full job descriptions, requirements and preferred qualifications
- **Excel Export**: Saves all jobs to a consolidated Excel file with automatic deduplication
- **Database Sync**: Optional Supabase integration for persistent storage
- **Incremental Updates**: Merges new job listings with existing data
- **CLI Flexibility**: Filter by site, dry-run mode, verbose/quiet logging, custom output

## 📋 Prerequisites

- **Python 3.11+**
- **Playwright browsers** (Chromium installed in setup step)

## 🚀 Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/gaganpasupuleti/job-finder.git
   cd job-finder
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers** *(required)*:
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

**Dry-run — collect data but skip writing files**:
```bash
python main.py --dry-run
```

**Verbose / quiet logging**:
```bash
python main.py --verbose   # DEBUG-level output
python main.py --quiet     # Errors only
```

**Include additional company career sites from file**:
```bash
python main.py --sites-file companies.xlsx
```

**Extract URLs from a companies PDF into JSON**:
```bash
python main.py --extract-sites-pdf companies.pdf --sites-output companies.json
```

**Use extracted JSON together with existing sites**:
```bash
python main.py --sites-file companies.json
```

**Run LinkedIn source scraping**:
```bash
python main.py --enable-linkedin --sites linkedin --linkedin-keywords "data engineer" --linkedin-location "India" --linkedin-max-jobs 40
```

**Generate separate Excel files for freshers and 1+ years**:
```bash
python main.py --enable-linkedin --sites linkedin --linkedin-keywords "software engineer" \
    --linkedin-location "India" --linkedin-max-jobs 100 \
    --output linkedin_jobs.xlsx --split-experience \
    --freshers-output linkedin_freshers_jobs.xlsx \
    --experienced-output linkedin_1plus_jobs.xlsx
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

## 📊 Output Schema

| Column | Description |
|--------|-------------|
| `Job ID` | SHA-256 of canonical URL |
| `Job Link` | Direct URL to job posting |
| `Title` | Job title |
| `Company` | Company name |
| `Location` | Job location |
| `Posted` | Posted date/time |
| `Minimum Requirements` | Required qualifications |
| `Good to Have` | Preferred qualifications |
| `Job Description` | Full or truncated description |
| `Years of Experience` | Minimum years extracted |
| `Essential Keywords` | Technical skills (comma-separated) |
| `Salary Range` | Detected compensation range |
| `Work Mode` | Remote / Hybrid / On-site / Unknown |
| `Source` | Source site name |

### Database Schema (Supabase)

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
  salary_range TEXT,
  work_mode TEXT,
  source TEXT,
  scraped_at TIMESTAMP
);
```

## 📁 Project Structure

```
job-finder/
├── main.py                    # CLI entry point
├── multi_site_scraper.py      # Backward-compatible facade
├── scrapers/
│   ├── base.py                # Base scraper class
│   ├── amazon.py              # Amazon extraction
│   ├── linkedin.py            # LinkedIn extraction
│   ├── pg.py                  # P&G extraction
│   └── generic.py             # Generic site extraction
├── db/
│   └── supabase_sync.py       # Supabase client + upsert
├── utils/
│   ├── experience.py          # Experience extraction
│   ├── keywords.py            # Skills/keyword extraction (200+ skills)
│   ├── job_utils.py           # compute_job_id, validate_job_data, JOB_SCHEMA
│   ├── sites_loader.py        # CSV/JSON/PDF site loading
│   ├── filters.py             # Filter profile cache
│   ├── salary.py              # Salary range extraction
│   ├── work_mode.py           # Remote/Hybrid/On-site detection
│   └── retry.py               # Retry decorator
├── tests/
│   ├── test_experience.py
│   ├── test_keywords.py
│   ├── test_job_utils.py
│   ├── test_sites_loader.py
│   └── test_salary_workmode.py
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

## 🧪 Running Tests

```bash
pytest tests/
```

## ⚠️ Important Notes

- The scraper respects rate limits with 1-second delays between individual job page navigations
- Generated Excel files are automatically excluded from git (see `.gitignore`)
- Authentication state files (`linkedin_state.json`) contain sensitive session cookies — never commit them
- If LinkedIn shows a login wall, run `python main.py --save-linkedin` first

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
