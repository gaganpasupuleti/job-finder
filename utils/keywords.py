"""
Skills and keyword extraction utilities.

Provides a massively expanded taxonomy of 200+ technical skills organized into
categories. Each skill entry is a ``(regex_pattern, canonical_name, category)``
tuple so that pattern matching and display are kept separate.

Public API
----------
extract_essential_keywords(text, title='') -> str
    Backward-compatible comma-separated string of up to 20 matched skills.

extract_keywords_structured(text, title='') -> list[dict]
    Richer output: list of ``{skill_name, category, confidence}`` dicts.
"""

import re
import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Taxonomy: (regex_pattern, canonical_display_name, category)
# All patterns are matched against lowercased text inside word boundaries.
# ---------------------------------------------------------------------------

_SKILLS: List[Tuple[str, str, str]] = [
    # ---- Programming Languages ----
    (r'python', 'Python', 'Programming Languages'),
    (r'java(?!script)', 'Java', 'Programming Languages'),
    (r'javascript|js(?=\b)', 'JavaScript', 'Programming Languages'),
    (r'typescript|ts(?=\b)', 'TypeScript', 'Programming Languages'),
    (r'c\+\+|cpp', 'C++', 'Programming Languages'),
    (r'c#|csharp', 'C#', 'Programming Languages'),
    (r'\bc\b(?!\+)', 'C', 'Programming Languages'),
    (r'ruby(?!\s+on)', 'Ruby', 'Programming Languages'),
    (r'\bgo\b|golang', 'Go', 'Programming Languages'),
    (r'rust', 'Rust', 'Programming Languages'),
    (r'php', 'PHP', 'Programming Languages'),
    (r'swift(?!ui)', 'Swift', 'Programming Languages'),
    (r'kotlin', 'Kotlin', 'Programming Languages'),
    (r'scala', 'Scala', 'Programming Languages'),
    (r'\br\b(?=\s+(?:language|programming|studio|\d))', 'R', 'Programming Languages'),
    (r'matlab', 'MATLAB', 'Programming Languages'),
    (r'perl', 'Perl', 'Programming Languages'),
    (r'\blua\b', 'Lua', 'Programming Languages'),
    (r'dart', 'Dart', 'Programming Languages'),
    (r'elixir', 'Elixir', 'Programming Languages'),
    (r'haskell', 'Haskell', 'Programming Languages'),
    (r'clojure', 'Clojure', 'Programming Languages'),
    (r'groovy', 'Groovy', 'Programming Languages'),
    (r'objective-c|objc', 'Objective-C', 'Programming Languages'),
    (r'assembly|asm\b', 'Assembly', 'Programming Languages'),
    (r'cobol', 'COBOL', 'Programming Languages'),
    (r'fortran', 'Fortran', 'Programming Languages'),
    (r'julia', 'Julia', 'Programming Languages'),
    (r'shell script|bash script|shellscript', 'Shell/Bash', 'Programming Languages'),
    (r'powershell', 'PowerShell', 'Programming Languages'),
    (r'\bvba\b', 'VBA', 'Programming Languages'),
    (r'solidity', 'Solidity', 'Programming Languages'),
    # ---- Frontend ----
    (r'react(?:\.js)?(?!\s+native)', 'React', 'Frontend'),
    (r'angular(?:js)?', 'Angular', 'Frontend'),
    (r'vue(?:\.js)?', 'Vue.js', 'Frontend'),
    (r'next\.?js|nextjs', 'Next.js', 'Frontend'),
    (r'nuxt\.?js|nuxtjs', 'Nuxt.js', 'Frontend'),
    (r'svelte', 'Svelte', 'Frontend'),
    (r'jquery', 'jQuery', 'Frontend'),
    (r'bootstrap', 'Bootstrap', 'Frontend'),
    (r'tailwind\s*css|tailwindcss', 'Tailwind CSS', 'Frontend'),
    (r'material[-\s]?ui|mui\b', 'Material UI', 'Frontend'),
    (r'webpack', 'Webpack', 'Frontend'),
    (r'\bvite\b', 'Vite', 'Frontend'),
    (r'html5?', 'HTML5', 'Frontend'),
    (r'css3?', 'CSS3', 'Frontend'),
    (r'sass|scss', 'SASS/SCSS', 'Frontend'),
    (r'redux', 'Redux', 'Frontend'),
    (r'mobx', 'MobX', 'Frontend'),
    (r'gatsby(?:\.js)?', 'Gatsby', 'Frontend'),
    (r'ember(?:\.js)?', 'Ember.js', 'Frontend'),
    (r'backbone(?:\.js)?', 'Backbone.js', 'Frontend'),
    # ---- Backend ----
    (r'node\.?js|nodejs', 'Node.js', 'Backend'),
    (r'express(?:\.js)?', 'Express', 'Backend'),
    (r'django', 'Django', 'Backend'),
    (r'flask', 'Flask', 'Backend'),
    (r'fastapi', 'FastAPI', 'Backend'),
    (r'spring\s*boot', 'Spring Boot', 'Backend'),
    (r'\bspring\b(?!\s*boot)', 'Spring', 'Backend'),
    (r'\.net\b|dotnet', '.NET', 'Backend'),
    (r'asp\.net|aspnet', 'ASP.NET', 'Backend'),
    (r'ruby\s+on\s+rails|rails\b', 'Ruby on Rails', 'Backend'),
    (r'laravel', 'Laravel', 'Backend'),
    (r'symfony', 'Symfony', 'Backend'),
    (r'nestjs|nest\.js', 'NestJS', 'Backend'),
    (r'\bgin\b(?=\s+framework|\s+go|\s+golang)', 'Gin', 'Backend'),
    (r'\becho\b(?=\s+framework)', 'Echo', 'Backend'),
    (r'\bfiber\b(?=\s+go|\s+framework)', 'Fiber', 'Backend'),
    (r'phoenix(?:\s+framework)?', 'Phoenix', 'Backend'),
    (r'actix', 'Actix', 'Backend'),
    (r'\brocket\b(?=\s+(?:framework|rust))', 'Rocket', 'Backend'),
    # ---- Databases ----
    (r'\bsql\b(?!ite)', 'SQL', 'Databases'),
    (r'mysql', 'MySQL', 'Databases'),
    (r'postgresql|postgres(?!ql)', 'PostgreSQL', 'Databases'),
    (r'mongodb|mongo\b', 'MongoDB', 'Databases'),
    (r'redis', 'Redis', 'Databases'),
    (r'dynamodb', 'DynamoDB', 'Databases'),
    (r'oracle\s*db|oracle\b', 'Oracle', 'Databases'),
    (r'cassandra', 'Cassandra', 'Databases'),
    (r'sqlite', 'SQLite', 'Databases'),
    (r'mariadb', 'MariaDB', 'Databases'),
    (r'couchdb', 'CouchDB', 'Databases'),
    (r'neo4j', 'Neo4j', 'Databases'),
    (r'influxdb', 'InfluxDB', 'Databases'),
    (r'elasticsearch|opensearch', 'Elasticsearch', 'Databases'),
    (r'supabase', 'Supabase', 'Databases'),
    (r'firebase', 'Firebase', 'Databases'),
    (r'planetscale', 'PlanetScale', 'Databases'),
    (r'cockroachdb', 'CockroachDB', 'Databases'),
    (r'timescaledb', 'TimescaleDB', 'Databases'),
    (r'snowflake', 'Snowflake', 'Databases'),
    (r'bigquery', 'BigQuery', 'Databases'),
    (r'redshift', 'Redshift', 'Databases'),
    (r'databricks', 'Databricks', 'Databases'),
    # ---- Cloud & DevOps ----
    (r'\baws\b|amazon\s+web\s+services', 'AWS', 'Cloud & DevOps'),
    (r'\bazure\b|microsoft\s+azure', 'Azure', 'Cloud & DevOps'),
    (r'\bgcp\b|google\s+cloud', 'GCP', 'Cloud & DevOps'),
    (r'docker', 'Docker', 'Cloud & DevOps'),
    (r'kubernetes|k8s\b', 'Kubernetes', 'Cloud & DevOps'),
    (r'jenkins', 'Jenkins', 'Cloud & DevOps'),
    (r'github\s*actions', 'GitHub Actions', 'Cloud & DevOps'),
    (r'gitlab\s*ci', 'GitLab CI', 'Cloud & DevOps'),
    (r'circleci', 'CircleCI', 'Cloud & DevOps'),
    (r'terraform', 'Terraform', 'Cloud & DevOps'),
    (r'ansible', 'Ansible', 'Cloud & DevOps'),
    (r'puppet', 'Puppet', 'Cloud & DevOps'),
    (r'\bchef\b(?=\s+(?:automation|devops|config))', 'Chef', 'Cloud & DevOps'),
    (r'\bhelm\b', 'Helm', 'Cloud & DevOps'),
    (r'istio', 'Istio', 'Cloud & DevOps'),
    (r'prometheus', 'Prometheus', 'Cloud & DevOps'),
    (r'grafana', 'Grafana', 'Cloud & DevOps'),
    (r'datadog', 'Datadog', 'Cloud & DevOps'),
    (r'new\s+relic', 'New Relic', 'Cloud & DevOps'),
    (r'cloudformation', 'CloudFormation', 'Cloud & DevOps'),
    (r'pulumi', 'Pulumi', 'Cloud & DevOps'),
    (r'vagrant', 'Vagrant', 'Cloud & DevOps'),
    (r'ci/cd|cicd|continuous\s+integration|continuous\s+delivery', 'CI/CD', 'Cloud & DevOps'),
    (r'serverless', 'Serverless', 'Cloud & DevOps'),
    # ---- Data & AI/ML ----
    (r'machine\s+learning|ml\b', 'Machine Learning', 'Data & AI/ML'),
    (r'deep\s+learning|dl\b(?=\s+model)', 'Deep Learning', 'Data & AI/ML'),
    (r'\bnlp\b|natural\s+language\s+processing', 'NLP', 'Data & AI/ML'),
    (r'computer\s+vision|cv\b(?=\s+model)', 'Computer Vision', 'Data & AI/ML'),
    (r'tensorflow', 'TensorFlow', 'Data & AI/ML'),
    (r'pytorch', 'PyTorch', 'Data & AI/ML'),
    (r'keras', 'Keras', 'Data & AI/ML'),
    (r'scikit[-\s]?learn|sklearn', 'scikit-learn', 'Data & AI/ML'),
    (r'pandas', 'Pandas', 'Data & AI/ML'),
    (r'numpy', 'NumPy', 'Data & AI/ML'),
    (r'scipy', 'SciPy', 'Data & AI/ML'),
    (r'\bspark\b|apache\s+spark|pyspark', 'Spark', 'Data & AI/ML'),
    (r'hadoop', 'Hadoop', 'Data & AI/ML'),
    (r'kafka', 'Kafka', 'Data & AI/ML'),
    (r'airflow', 'Airflow', 'Data & AI/ML'),
    (r'\bdbt\b', 'dbt', 'Data & AI/ML'),
    (r'tableau', 'Tableau', 'Data & AI/ML'),
    (r'power\s*bi', 'Power BI', 'Data & AI/ML'),
    (r'looker', 'Looker', 'Data & AI/ML'),
    (r'hugging\s*face', 'Hugging Face', 'Data & AI/ML'),
    (r'openai', 'OpenAI', 'Data & AI/ML'),
    (r'langchain', 'LangChain', 'Data & AI/ML'),
    (r'\bllm\b|large\s+language\s+model', 'LLM', 'Data & AI/ML'),
    (r'\brag\b|retrieval[\s-]augmented', 'RAG', 'Data & AI/ML'),
    (r'mlflow', 'MLflow', 'Data & AI/ML'),
    (r'kubeflow', 'Kubeflow', 'Data & AI/ML'),
    (r'\bai\b|artificial\s+intelligence', 'AI', 'Data & AI/ML'),
    (r'data\s+science', 'Data Science', 'Data & AI/ML'),
    (r'data\s+engineer', 'Data Engineering', 'Data & AI/ML'),
    (r'data\s+warehouse', 'Data Warehouse', 'Data & AI/ML'),
    (r'etl\b|elt\b', 'ETL/ELT', 'Data & AI/ML'),
    # ---- Mobile ----
    (r'react\s+native', 'React Native', 'Mobile'),
    (r'flutter', 'Flutter', 'Mobile'),
    (r'swiftui', 'SwiftUI', 'Mobile'),
    (r'jetpack\s+compose', 'Jetpack Compose', 'Mobile'),
    (r'xamarin', 'Xamarin', 'Mobile'),
    (r'ionic', 'Ionic', 'Mobile'),
    (r'cordova|phonegap', 'Cordova', 'Mobile'),
    # ---- Testing ----
    (r'jest', 'Jest', 'Testing'),
    (r'mocha', 'Mocha', 'Testing'),
    (r'pytest', 'Pytest', 'Testing'),
    (r'junit', 'JUnit', 'Testing'),
    (r'selenium', 'Selenium', 'Testing'),
    (r'cypress', 'Cypress', 'Testing'),
    (r'playwright', 'Playwright', 'Testing'),
    (r'testng', 'TestNG', 'Testing'),
    (r'cucumber', 'Cucumber', 'Testing'),
    (r'postman', 'Postman', 'Testing'),
    (r'unit\s+test|unit\s+testing', 'Unit Testing', 'Testing'),
    (r'e2e\s+test|end[\s-]to[\s-]end\s+test', 'E2E Testing', 'Testing'),
    # ---- Tools & Practices ----
    (r'\bgit\b(?!\s*hub|\s*lab)', 'Git', 'Tools & Practices'),
    (r'github(?!\s*actions)', 'GitHub', 'Tools & Practices'),
    (r'gitlab(?!\s*ci)', 'GitLab', 'Tools & Practices'),
    (r'bitbucket', 'Bitbucket', 'Tools & Practices'),
    (r'jira', 'Jira', 'Tools & Practices'),
    (r'confluence', 'Confluence', 'Tools & Practices'),
    (r'agile', 'Agile', 'Tools & Practices'),
    (r'scrum', 'Scrum', 'Tools & Practices'),
    (r'kanban', 'Kanban', 'Tools & Practices'),
    (r'rest\s*api|restful', 'REST API', 'Tools & Practices'),
    (r'graphql', 'GraphQL', 'Tools & Practices'),
    (r'grpc', 'gRPC', 'Tools & Practices'),
    (r'websocket|web\s+socket', 'WebSocket', 'Tools & Practices'),
    (r'microservice', 'Microservices', 'Tools & Practices'),
    (r'monorepo', 'Monorepo', 'Tools & Practices'),
    (r'event[\s-]driven', 'Event-Driven', 'Tools & Practices'),
    (r'domain[\s-]driven\s+design|ddd\b', 'Domain-Driven Design', 'Tools & Practices'),
    (r'design\s+pattern', 'Design Patterns', 'Tools & Practices'),
    (r'devops', 'DevOps', 'Tools & Practices'),
    (r'devsecops', 'DevSecOps', 'Tools & Practices'),
    # ---- Security ----
    (r'oauth', 'OAuth', 'Security'),
    (r'\bjwt\b|json\s+web\s+token', 'JWT', 'Security'),
    (r'saml', 'SAML', 'Security'),
    (r'ssl[/\s]tls|tls\b', 'SSL/TLS', 'Security'),
    (r'owasp', 'OWASP', 'Security'),
    (r'penetration\s+test|pentest', 'Penetration Testing', 'Security'),
    (r'soc\s*2', 'SOC2', 'Security'),
    (r'gdpr', 'GDPR', 'Security'),
    (r'zero\s+trust', 'Zero Trust', 'Security'),
    # ---- Infrastructure / Other ----
    (r'\blinux\b', 'Linux', 'Infrastructure'),
    (r'\bbash\b', 'Bash', 'Infrastructure'),
    (r'nginx', 'Nginx', 'Infrastructure'),
    (r'apache(?:\s+(?:http|web)\s+server)?', 'Apache', 'Infrastructure'),
    (r'rabbitmq', 'RabbitMQ', 'Infrastructure'),
    (r'celery', 'Celery', 'Infrastructure'),
    (r'webrtc', 'WebRTC', 'Infrastructure'),
    (r'blockchain', 'Blockchain', 'Infrastructure'),
    (r'\biot\b|internet\s+of\s+things', 'IoT', 'Infrastructure'),
    (r'ar[/\s]vr|augmented\s+reality|virtual\s+reality', 'AR/VR', 'Infrastructure'),
    (r'message\s+queue|mq\b', 'Message Queue', 'Infrastructure'),
    (r'load\s+balanc', 'Load Balancing', 'Infrastructure'),
    (r'cdn\b|content\s+delivery\s+network', 'CDN', 'Infrastructure'),
]

# Precompile patterns (case-insensitive, whole-word)
_COMPILED: List[Tuple[re.Pattern, str, str]] = []
for _pat, _name, _cat in _SKILLS:
    try:
        _COMPILED.append((re.compile(r'(?<![a-z0-9])' + _pat + r'(?![a-z0-9])', re.IGNORECASE), _name, _cat))
    except re.error as _e:
        logger.warning(f"Bad skill regex '{_pat}': {_e}")


def extract_keywords_structured(text: str, title: str = '') -> List[Dict]:
    """Return list of matched skills with name, category, and confidence.

    Args:
        text: Job description / requirements body.
        title: Optional job title (searched separately).

    Returns:
        List of dicts with keys: ``skill_name``, ``category``, ``confidence``.
    """
    combined = f"{title} {text}"
    if not combined.strip():
        return []

    seen: Dict[str, Dict] = {}

    for pattern, name, category in _COMPILED:
        if pattern.search(combined):
            if name not in seen:
                # Higher confidence if found in title
                confidence = 'high' if title and pattern.search(title) else 'medium'
                seen[name] = {'skill_name': name, 'category': category, 'confidence': confidence}

    return list(seen.values())


def extract_essential_keywords(text: str, title: str = '') -> str:
    """Extract essential technical keywords from job text.

    Backward-compatible: returns a comma-separated string of up to 20 skills.

    Args:
        text: Job description / requirements body.
        title: Optional job title.

    Returns:
        Comma-separated canonical skill names (up to 20).
    """
    skills = extract_keywords_structured(text, title)
    names = [s['skill_name'] for s in skills]
    return ', '.join(names[:20])


def build_boolean_or_query(job_titles: List[str]) -> str:
    """Build an optimized boolean OR query from a list of job titles.

    Example:
        ["Python", "ServiceNow"] -> ("Python" OR "ServiceNow")

    Args:
        job_titles: Candidate titles / skill phrases.

    Returns:
        Boolean query string suitable for search endpoints.
    """
    if not job_titles:
        return ''

    cleaned: List[str] = []
    seen = set()
    for item in job_titles:
        title = str(item or '').strip()
        if not title:
            continue
        # Normalize whitespace and escape embedded double-quotes.
        title = ' '.join(title.split()).replace('"', '\\"')
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(f'"{title}"')

    if not cleaned:
        return ''
    if len(cleaned) == 1:
        return cleaned[0]
    return f"({' OR '.join(cleaned)})"
