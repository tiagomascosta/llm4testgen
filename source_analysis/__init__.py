"""
Source analysis module for extracting method slices and dependencies.
"""

from .method_slicer import slice_method, parse_method_node
from .ast_analyzer import ASTAnalyzer
from .source_resolver import resolve_source_file
from .dependency_extractor import (
    extract_dependencies,
    find_flow_control_deps,
    extract_method_slice,
    parse_method_signature,
    load_source
)
from .test_scaffold import generate_test_scaffold, extract_package_from_imports

__all__ = [
    'slice_method',
    'ASTAnalyzer',
    'parse_method_node',
    'resolve_source_file',
    'extract_dependencies',
    'find_flow_control_deps',
    'extract_method_slice',
    'parse_method_signature',
    'load_source',
    'generate_test_scaffold',
    'extract_package_from_imports'
]
