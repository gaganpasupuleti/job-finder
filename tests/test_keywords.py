"""
Unit tests for utils/keywords.py — skill/keyword extraction.
"""

import pytest
from utils.keywords import (
    extract_essential_keywords,
    extract_keywords_structured,
    build_boolean_or_query,
)


class TestExtractEssentialKeywords:
    """Tests for the backward-compatible comma-separated string output."""

    def test_empty_text(self):
        assert extract_essential_keywords('') == ''

    def test_python_detected(self):
        result = extract_essential_keywords('We need Python and Django skills')
        assert 'Python' in result

    def test_javascript_detected(self):
        result = extract_essential_keywords('React and JavaScript required')
        assert 'JavaScript' in result

    def test_cplusplus_detected(self):
        result = extract_essential_keywords('Experience with C++ and embedded systems')
        assert 'C++' in result

    def test_kubernetes_abbreviation(self):
        result = extract_essential_keywords('Deploy on k8s clusters')
        assert 'Kubernetes' in result

    def test_machine_learning_detected(self):
        result = extract_essential_keywords('machine learning and deep learning experience')
        assert 'Machine Learning' in result

    def test_react_native_not_confused_with_react(self):
        result = extract_keywords_structured('React Native mobile app development')
        names = [s['skill_name'] for s in result]
        assert 'React Native' in names

    def test_typescript_abbreviation(self):
        result = extract_essential_keywords('Strong TS and JS skills')
        assert 'TypeScript' in result

    def test_spring_boot_detected(self):
        result = extract_essential_keywords('Spring Boot microservices')
        assert 'Spring Boot' in result

    def test_aws_detected(self):
        result = extract_essential_keywords('Deploy to AWS using CloudFormation')
        assert 'AWS' in result

    def test_limit_to_20_keywords(self):
        text = (
            'Python Java JavaScript TypeScript Go Rust PHP Swift Kotlin Scala '
            'React Angular Vue Django Flask FastAPI Spring Node.js Docker Kubernetes '
            'AWS Azure Terraform Jenkins PostgreSQL MongoDB Redis TensorFlow PyTorch'
        )
        result = extract_essential_keywords(text)
        keywords = [k.strip() for k in result.split(',') if k.strip()]
        assert len(keywords) <= 20

    def test_title_boosts_confidence(self):
        skills = extract_keywords_structured('', title='Python Developer')
        python_skills = [s for s in skills if s['skill_name'] == 'Python']
        assert python_skills
        assert python_skills[0]['confidence'] == 'high'


class TestExtractKeywordsStructured:
    """Tests for the richer structured output."""

    def test_returns_list_of_dicts(self):
        result = extract_keywords_structured('Python and AWS required')
        assert isinstance(result, list)
        for item in result:
            assert 'skill_name' in item
            assert 'category' in item
            assert 'confidence' in item

    def test_category_assigned_correctly(self):
        result = extract_keywords_structured('Python developer needed')
        python_entry = next((s for s in result if s['skill_name'] == 'Python'), None)
        assert python_entry is not None
        assert python_entry['category'] == 'Programming Languages'

    def test_aws_cloud_category(self):
        result = extract_keywords_structured('Experience with AWS')
        aws_entry = next((s for s in result if s['skill_name'] == 'AWS'), None)
        assert aws_entry is not None
        assert aws_entry['category'] == 'Cloud & DevOps'

    def test_no_duplicates(self):
        result = extract_keywords_structured('Python Python Python')
        names = [s['skill_name'] for s in result]
        assert len(names) == len(set(names))


class TestBooleanBuilder:
    def test_builds_or_query(self):
        query = build_boolean_or_query(['Python', 'ServiceNow'])
        assert query == '("Python" OR "ServiceNow")'

    def test_single_title(self):
        assert build_boolean_or_query(['Python']) == '"Python"'

    def test_deduplicates_and_trims(self):
        query = build_boolean_or_query(['  Python  ', 'python', '', 'Service Now'])
        assert query == '("Python" OR "Service Now")'
