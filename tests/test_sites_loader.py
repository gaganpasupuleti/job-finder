"""
Unit tests for utils/sites_loader.py — derive_name_from_url, normalize_site_type.
"""

import pytest
from utils.sites_loader import derive_name_from_url, normalize_site_type


class TestDeriveNameFromUrl:
    def test_basic_url(self):
        result = derive_name_from_url('https://www.acme.com/careers')
        assert 'Acme' in result
        assert result.endswith('Careers')

    def test_careers_subdomain(self):
        result = derive_name_from_url('https://careers.google.com')
        # 'careers' prefix is skipped; should use 'google'
        assert 'Google' in result

    def test_no_www(self):
        result = derive_name_from_url('https://stripe.com/jobs')
        assert 'Stripe' in result

    def test_empty_url(self):
        result = derive_name_from_url('')
        assert result == 'External Careers'

    def test_hyphenated_domain(self):
        result = derive_name_from_url('https://my-company.com/careers')
        assert 'My Company' in result

    def test_ends_with_careers(self):
        result = derive_name_from_url('https://example.com')
        assert result.endswith('Careers')


class TestNormalizeSiteType:
    def test_amazon_passthrough(self):
        assert normalize_site_type('amazon') == 'amazon'

    def test_pg_careers_passthrough(self):
        assert normalize_site_type('pg_careers') == 'pg_careers'

    def test_linkedin_passthrough(self):
        assert normalize_site_type('linkedin') == 'linkedin'

    def test_generic_passthrough(self):
        assert normalize_site_type('generic') == 'generic'

    def test_unknown_falls_back_to_generic(self):
        assert normalize_site_type('workday') == 'generic'

    def test_empty_falls_back_to_generic(self):
        assert normalize_site_type('') == 'generic'

    def test_none_falls_back_to_generic(self):
        assert normalize_site_type(None) == 'generic'

    def test_case_insensitive(self):
        assert normalize_site_type('AMAZON') == 'amazon'

    def test_strips_whitespace(self):
        assert normalize_site_type('  linkedin  ') == 'linkedin'
