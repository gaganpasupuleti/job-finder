"""
Unit tests for utils/salary.py and utils/work_mode.py.
"""

import pytest
from utils.salary import extract_salary
from utils.work_mode import detect_work_mode


class TestExtractSalary:
    def test_empty(self):
        assert extract_salary('') == ''

    def test_usd_range(self):
        result = extract_salary('Salary: $120,000 - $180,000 per year')
        assert '$120,000' in result or '120,000' in result

    def test_k_notation(self):
        result = extract_salary('Pay: 80K-120K')
        assert result != ''

    def test_lpa_india(self):
        result = extract_salary('CTC: 12-18 LPA')
        assert result != ''

    def test_gbp_range(self):
        result = extract_salary('£50k-£70k annually')
        assert result != ''

    def test_no_salary_in_text(self):
        result = extract_salary('We offer competitive compensation and great benefits.')
        assert result == ''


class TestDetectWorkMode:
    def test_remote(self):
        assert detect_work_mode('This is a fully remote position') == 'Remote'

    def test_hybrid(self):
        assert detect_work_mode('We offer hybrid work arrangements') == 'Hybrid'

    def test_onsite(self):
        assert detect_work_mode('Must be on-site daily') == 'On-site'

    def test_unknown(self):
        assert detect_work_mode('Join our team and make an impact') == 'Unknown'

    def test_location_used(self):
        assert detect_work_mode('', location='Remote - United States') == 'Remote'

    def test_case_insensitive(self):
        assert detect_work_mode('REMOTE FIRST COMPANY') == 'Remote'

    def test_wfh(self):
        assert detect_work_mode('Work from home allowed') == 'Remote'
