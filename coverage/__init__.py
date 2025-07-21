"""
Coverage analysis module for test suite generation.

This module provides JaCoCo coverage analysis capabilities including:
- Coverage metric extraction and calculation
- HTML report serving
- Coverage data export
"""

from .jacoco_analyzer import analyze_coverage, run_tests_with_coverage
from .coverage_metrics import CoverageMetrics
from .report_server import start_report_server, stop_report_server, generate_report_urls
from .coverage_config import CoverageConfig

__all__ = [
    'analyze_coverage',
    'run_tests_with_coverage', 
    'CoverageMetrics',
    'start_report_server',
    'stop_report_server',
    'generate_report_urls',
    'CoverageConfig'
] 