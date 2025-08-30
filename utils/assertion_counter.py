import re
from pathlib import Path
from typing import List


def count_assertions_in_test_file(file_path: Path) -> int:
    """Count assertions in a Java test file using regex patterns."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return 0
    
    # SPECIFIC assertion patterns (no overlapping)
    assertion_patterns = [
        # JUnit 4 & 5 Core Assertions (specific, no overlap)
        r'\bassertTrue\b',
        r'\bassertFalse\b',
        r'\bassertEquals\b',
        r'\bassertNotEquals\b',
        r'\bassertNull\b',
        r'\bassertNotNull\b',
        r'\bassertSame\b',
        r'\bassertNotSame\b',
        r'\bassertArrayEquals\b',
        r'\bassertIterableEquals\b',
        r'\bassertLinesMatch\b',
        r'\bassertInstanceOf\b',
        r'\bassertNotInstanceOf\b',
        r'\bassertThrows\b',
        r'\bassertDoesNotThrow\b',
        r'\bassertTimeout\b',
        r'\bassertTimeoutPreemptively\b',
        r'\bassertAll\b',
        
        # TestNG specific
        r'\bassertNoThrows\b',
    ]
    
    total_assertions = 0
    
    for pattern in assertion_patterns:
        matches = re.findall(pattern, content)
        total_assertions += len(matches)
    
    return total_assertions


def count_assertions_in_test_suite(test_suite_dir: Path) -> int:
    """Count total assertions across all test files in a test suite."""
    total_assertions = 0
    
    print(f"🔍 Scanning directory: {test_suite_dir}")
    
    if not test_suite_dir.exists():
        print(f"❌ Directory does not exist: {test_suite_dir}")
        return 0
    
    # Find all Java test files
    java_files = list(test_suite_dir.glob("**/*.java"))
    print(f"🔍 Found {len(java_files)} Java files")
    
    for test_file in java_files:
        if test_file.is_file():
            file_assertions = count_assertions_in_test_file(test_file)
            total_assertions += file_assertions
            print(f"  📊 {test_file.name}: {file_assertions} assertions")
    
    return total_assertions


def count_assertions_in_final_test_suite(output_dir: Path) -> int:
    """Count assertions in the final test suite (the one that gets saved to the repository)."""
    # The output_dir is already the test_suite directory
    test_suite_dir = output_dir
    
    print(f"🔍 Looking for test suite in: {test_suite_dir}")
    print(f"🔍 Directory exists: {test_suite_dir.exists()}")
    
    if not test_suite_dir.exists():
        print(f"❌ Test suite directory not found: {test_suite_dir}")
        return 0
    
    # Count assertions in all Java files in the test_suite directory
    total_assertions = count_assertions_in_test_suite(test_suite_dir)
    
    print(f"📊 Total assertions in final test suite: {total_assertions}")
    return total_assertions
