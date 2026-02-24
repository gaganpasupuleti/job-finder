"""
Unit tests for utils/job_utils.py — compute_job_id, validate_job_data.
"""

import pytest
from utils.job_utils import compute_job_id, validate_job_data, JOB_SCHEMA


class TestComputeJobId:
    def test_returns_64_char_hex(self):
        job_id = compute_job_id('https://example.com/jobs/123')
        assert len(job_id) == 64
        assert all(c in '0123456789abcdef' for c in job_id)

    def test_same_url_same_id(self):
        url = 'https://example.com/jobs/123'
        assert compute_job_id(url) == compute_job_id(url)

    def test_different_urls_different_ids(self):
        assert compute_job_id('https://example.com/jobs/1') != compute_job_id('https://example.com/jobs/2')

    def test_trailing_slash_normalized(self):
        assert compute_job_id('https://example.com/jobs/123/') == compute_job_id('https://example.com/jobs/123')

    def test_tracking_params_stripped(self):
        url1 = 'https://example.com/jobs/123'
        url2 = 'https://example.com/jobs/123?utm_source=linkedin&utm_campaign=summer'
        assert compute_job_id(url1) == compute_job_id(url2)

    def test_non_tracking_params_preserved(self):
        url1 = 'https://example.com/jobs/123?jobId=abc'
        url2 = 'https://example.com/jobs/123?jobId=xyz'
        assert compute_job_id(url1) != compute_job_id(url2)

    def test_sha256_not_sha1(self):
        # SHA-1 produces a 40-char hex; SHA-256 produces 64-char hex
        job_id = compute_job_id('https://example.com/jobs/1')
        assert len(job_id) == 64


class TestValidateJobData:
    def test_valid_job(self):
        job = {'Job ID': 'abc', 'Job Link': 'https://example.com', 'Title': 'Engineer'}
        assert validate_job_data(job) is True

    def test_missing_title(self):
        job = {'Job ID': 'abc', 'Job Link': 'https://example.com', 'Title': ''}
        assert validate_job_data(job) is False

    def test_missing_job_id(self):
        job = {'Job ID': '', 'Job Link': 'https://example.com', 'Title': 'Engineer'}
        assert validate_job_data(job) is False

    def test_missing_job_link(self):
        job = {'Job ID': 'abc', 'Job Link': '', 'Title': 'Engineer'}
        assert validate_job_data(job) is False

    def test_extra_fields_ok(self):
        job = {
            'Job ID': 'abc', 'Job Link': 'https://x.com', 'Title': 'Dev',
            'Company': 'Acme', 'Location': 'NY',
        }
        assert validate_job_data(job) is True


class TestJobSchema:
    def test_schema_contains_required_columns(self):
        for col in ['Job ID', 'Job Link', 'Title', 'Company', 'Location', 'Source']:
            assert col in JOB_SCHEMA

    def test_schema_contains_new_columns(self):
        assert 'Salary Range' in JOB_SCHEMA
        assert 'Work Mode' in JOB_SCHEMA
