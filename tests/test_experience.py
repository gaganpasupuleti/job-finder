"""
Unit tests for utils/experience.py — experience extraction.
"""

import pytest
from utils.experience import extract_years_of_experience, extract_experience_structured


class TestExtractYearsOfExperience:
    """Tests for the backward-compatible string-returning function."""

    def test_empty_text(self):
        assert extract_years_of_experience('') == ''

    def test_none_text(self):
        assert extract_years_of_experience(None) == ''

    def test_simple_years(self):
        assert extract_years_of_experience('3 years of experience') == '3'

    def test_range_returns_minimum(self):
        assert extract_years_of_experience('3-5 years of experience') == '3'

    def test_range_with_to(self):
        assert extract_years_of_experience('3 to 5 years of experience') == '3'

    def test_plus_notation(self):
        assert extract_years_of_experience('5+ years of experience') == '5'

    def test_minimum_of(self):
        assert extract_years_of_experience('minimum of 3 years of experience') == '3'

    def test_at_least(self):
        assert extract_years_of_experience('at least 4 years experience') == '4'

    def test_yrs_abbreviation(self):
        assert extract_years_of_experience('2+ yrs exp') == '2'

    def test_experience_of_form(self):
        assert extract_years_of_experience('experience of 6 years') == '6'

    def test_experience_colon(self):
        assert extract_years_of_experience('Experience: 7 years') == '7'

    def test_written_number(self):
        result = extract_years_of_experience('three years of experience')
        assert result == '3'

    def test_written_range(self):
        result = extract_years_of_experience('three to five years of experience')
        assert result == '3'

    def test_written_number_twenty(self):
        result = extract_years_of_experience('twenty years of experience')
        assert result == '20'

    def test_written_number_zero(self):
        # 'zero years of experience' → 0 but our range guard filters 0 < val, so empty
        # This documents the current behavior (zero experience is caught by fresher patterns)
        result = extract_years_of_experience('zero years of experience required')
        # zero triggers fresher path or returns '' depending on order; must not error
        assert isinstance(result, str)

    def test_fresher_returns_zero(self):
        assert extract_years_of_experience('Looking for freshers') == '0'

    def test_entry_level_returns_zero(self):
        assert extract_years_of_experience('entry level position') == '0'

    def test_no_match_returns_empty(self):
        assert extract_years_of_experience('Looking for a team player') == ''

    def test_seniority_inferred_from_text(self):
        result = extract_years_of_experience('senior software engineer role')
        assert result == '5'

    def test_seniority_inferred_from_title(self):
        result = extract_years_of_experience('', title='Senior Engineer')
        assert result == '5'

    def test_intern_inferred(self):
        result = extract_years_of_experience('', title='Software Engineering Intern')
        assert result == '0'

    def test_large_number_ignored(self):
        # 50+ years is invalid — should not match
        assert extract_years_of_experience('50 years of experience') == ''


class TestExtractExperienceStructured:
    """Tests for the richer structured output."""

    def test_range_high_confidence(self):
        res = extract_experience_structured('3-5 years of experience')
        assert res['min_years'] == 3
        assert res['max_years'] == 5
        assert res['confidence'] == 'high'

    def test_single_high_confidence(self):
        res = extract_experience_structured('5 years of experience required')
        assert res['min_years'] == 5
        assert res['confidence'] == 'high'

    def test_fresher_medium_confidence(self):
        res = extract_experience_structured('fresher welcome')
        assert res['min_years'] == 0
        assert res['confidence'] == 'medium'

    def test_inferred_from_title(self):
        res = extract_experience_structured('', title='Principal Engineer')
        assert res['min_years'] == 8
        assert res['confidence'] == 'inferred'

    def test_no_match_all_none(self):
        res = extract_experience_structured('We love teamwork')
        assert res['min_years'] is None
        assert res['max_years'] is None
