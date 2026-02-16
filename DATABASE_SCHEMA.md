# Database Schema Documentation

## Updated Job Schema

This document describes the complete database schema for the job scraper after all enhancements.

## Complete Column List (in order)

1. **Job ID** - Primary Key
2. **Job Link**
3. **Title**
4. **Company** *(NEW)*
5. **Location**
6. **Posted**
7. **Minimum Requirements**
8. **Good to Have**
9. **Job Description**
10. **Years of Experience** *(NEW)*
11. **Essential Keywords** *(NEW)*
12. **Source**
13. **scraped_at** *(NEW - DB only)*

## Supabase Database Schema

### SQL Schema Definition

```sql
CREATE TABLE jobs (
  -- Primary identifier (hash of job link)
  job_id TEXT PRIMARY KEY,
  
  -- Basic job information
  job_link TEXT NOT NULL,
  title TEXT,
  company TEXT,
  location TEXT,
  posted TEXT,
  
  -- Job requirements and description
  minimum_requirements TEXT,
  good_to_have TEXT,
  job_description TEXT,
  
  -- Extracted/computed fields
  years_of_experience TEXT,
  essential_keywords TEXT,
  
  -- Metadata
  source TEXT,
  scraped_at TIMESTAMP
);

-- Create index on source for filtering
CREATE INDEX idx_jobs_source ON jobs(source);

-- Create index on scraped_at for time-based queries
CREATE INDEX idx_jobs_scraped_at ON jobs(scraped_at);

-- Create index on company for company-based queries
CREATE INDEX idx_jobs_company ON jobs(company);
```

## Column Details

### job_id (TEXT, PRIMARY KEY)
- SHA-1 hash of the job link
- Ensures uniqueness across all job postings
- Used for upsert conflict resolution

### job_link (TEXT, NOT NULL)
- Direct URL to the job posting
- Source of truth for job_id generation

### title (TEXT)
- Job title/position name
- Example: "Senior Software Engineer", "Product Manager"

### company (TEXT) - NEW FIELD
- Company name
- Extracted from job site or set to site name for Amazon/P&G
- Example: "Amazon", "P&G", "Microsoft"

### location (TEXT)
- Job location (city, state, country, or remote)
- Example: "Bangalore, India", "Remote", "Seattle, WA"

### posted (TEXT)
- When the job was posted
- Format varies by source site
- Example: "2 days ago", "2024-01-15"

### minimum_requirements (TEXT)
- Required qualifications for the role
- May include education, skills, certifications
- Truncated to first 300 characters for P&G

### good_to_have (TEXT)
- Preferred/nice-to-have qualifications
- Often empty for some sources
- Example: "Master's degree preferred"

### job_description (TEXT)
- Full or partial job description
- Truncated to 500-1000 characters depending on source
- Contains responsibilities, requirements, company info

### years_of_experience (TEXT) - NEW FIELD
- Automatically extracted from job description
- Pattern matching for "X years", "X-Y years", etc.
- Empty string if not found
- Examples: "3", "3-5", "2", "5+"

### essential_keywords (TEXT) - NEW FIELD
- Comma-separated list of technical skills/keywords
- Automatically extracted from job text
- Limited to top 15 keywords
- Examples: "Python, AWS, Docker, React, SQL"
- Includes: programming languages, frameworks, databases, cloud platforms, tools

### source (TEXT)
- Which job site the listing came from
- Values: "Amazon", "P&G Careers", "LinkedIn"

### scraped_at (TIMESTAMP) - NEW FIELD (DB only)
- UTC timestamp when the job was last scraped
- Format: ISO 8601 (e.g., "2024-01-15T14:30:00.000000")
- Updated on every upsert
- Used to track freshness of job data

## Excel Output Schema

The Excel file (`multi_site_jobs.xlsx`) contains all fields except `scraped_at`:

1. Job ID
2. Job Link
3. Title
4. Company
5. Location
6. Posted
7. Minimum Requirements
8. Good to Have
9. Job Description
10. Years of Experience
11. Essential Keywords
12. Source

## Migration Notes

If you have an existing database, you need to add these new columns:

```sql
-- Add new columns to existing table
ALTER TABLE jobs ADD COLUMN company TEXT;
ALTER TABLE jobs ADD COLUMN years_of_experience TEXT;
ALTER TABLE jobs ADD COLUMN essential_keywords TEXT;
ALTER TABLE jobs ADD COLUMN scraped_at TIMESTAMP;

-- Create new indexes
CREATE INDEX idx_jobs_company ON jobs(company);
CREATE INDEX idx_jobs_scraped_at ON jobs(scraped_at);
```

## Data Extraction Logic

### Years of Experience Extraction
Uses regex patterns to find:
- "X years" / "X years of experience"
- "X-Y years" / "X to Y years"
- "minimum X years"
- "at least X years"
- "X yrs"

### Essential Keywords Extraction
Searches for common technical terms:
- **Languages**: Python, Java, JavaScript, TypeScript, C++, C#, Ruby, Go, Rust, PHP, Swift, Kotlin
- **Frameworks**: React, Angular, Vue, Node.js, Django, Flask, Spring, Express, FastAPI
- **Databases**: SQL, MySQL, PostgreSQL, MongoDB, Redis, DynamoDB, Oracle, Cassandra
- **Cloud/DevOps**: AWS, Azure, GCP, Docker, Kubernetes, Jenkins, CI/CD, Terraform, Ansible
- **Data/AI/ML**: Machine Learning, Deep Learning, AI, Data Science, TensorFlow, PyTorch, Pandas, NumPy
- **Other**: Agile, Scrum, Git, REST API, GraphQL, Microservices, Linux, Bash

Returns up to 15 most relevant keywords found.

## API Usage Example

When using the Supabase API, rows are upserted with this structure:

```python
{
    'job_id': 'abc123...',
    'job_link': 'https://...',
    'title': 'Senior Software Engineer',
    'company': 'Amazon',
    'location': 'Bangalore, India',
    'posted': '2 days ago',
    'minimum_requirements': 'Bachelor degree in CS...',
    'good_to_have': 'Masters degree...',
    'job_description': 'We are looking for...',
    'years_of_experience': '3-5',
    'essential_keywords': 'Python, AWS, Docker, React, SQL',
    'source': 'Amazon',
    'scraped_at': '2024-01-15T14:30:00.000000'
}
```

The upsert uses `on_conflict='job_id'` to update existing records.
