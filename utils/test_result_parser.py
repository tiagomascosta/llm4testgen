import re
from typing import Dict, List, Tuple

def parse_gradle_test_output(output: str) -> Dict[str, bool]:
    """
    Parse Gradle test output to extract test pass/fail status.
    
    Args:
        output: Raw output from Gradle test execution
        
    Returns:
        Dictionary mapping test method names to pass/fail status
    """
    results = {}
    
    # Look for the specific pattern we saw in the debug output:
    # "com.fishercoder.solutions._235Test > testNodesAreEqual FAILED"
    test_result_pattern = re.compile(r'(\w+Test)\s*>\s*(\w+)\s+(PASSED|FAILED)')
    
    failed_tests = set()
    for line_num, line in enumerate(output.split('\n'), 1):
        match = test_result_pattern.search(line)
        if match:
            test_class, method_name, status = match.groups()
            if status == 'FAILED':
                failed_tests.add(method_name)
                results[method_name] = False
            elif status == 'PASSED':
                results[method_name] = True
    
    # Also look for the summary pattern: "X tests completed, Y failed"
    summary_pattern = re.search(r'(\d+) tests? completed, (\d+) failed', output)
    if summary_pattern:
        total_tests = int(summary_pattern.group(1))
        failed_tests_count = int(summary_pattern.group(2))
        passed_tests_count = total_tests - failed_tests_count
        
        # If we have a summary but no individual results, and all tests passed,
        # mark all tests as passed
        if failed_tests_count == 0 and not results:
            results['all_tests'] = True
        # If we have some failed tests but not all individual results,
        # this means the missing tests passed (Gradle only reports failures)
        elif failed_tests_count > 0 and len(failed_tests) < failed_tests_count:
            pass  # Some failed tests weren't captured in output
    
    # Look for test execution patterns
    # Gradle typically shows: ✓ testMethodName or ✗ testMethodName
    test_pattern = re.compile(r'([✓✗])\s+(\w+)')
    
    for line_num, line in enumerate(output.split('\n'), 1):
        match = test_pattern.search(line)
        if match:
            status, method_name = match.groups()
            results[method_name] = (status == '✓')
    
    # Look for test class patterns (duplicate of first pattern, but keeping for compatibility)
    test_class_pattern = re.compile(r'(\w+Test)\s*>\s*(\w+)\s+(PASSED|FAILED)')
    
    for line_num, line in enumerate(output.split('\n'), 1):
        match = test_class_pattern.search(line)
        if match:
            test_class, method_name, status = match.groups()
            if status == 'FAILED':
                failed_tests.add(method_name)
                results[method_name] = False
            elif status == 'PASSED':
                results[method_name] = True
    
    # Look for build status
    if 'BUILD SUCCESS' in output or 'BUILD SUCCESSFUL' in output:
        # If we have BUILD SUCCESS but no individual results, assume all tests passed
        if not results:
            results['all_tests'] = True
    elif 'BUILD FAILED' in output:
        # If we have BUILD FAILED but no individual results, assume some tests failed
        if not results:
            results['all_tests'] = False
    
    # Look for additional Gradle patterns (duplicate, but keeping for compatibility)
    # Sometimes Gradle shows: "TestClassName > testMethodName FAILED"
    gradle_test_pattern = re.compile(r'(\w+Test)\s*>\s*(\w+)\s+(PASSED|FAILED)')
    
    for line_num, line in enumerate(output.split('\n'), 1):
        match = gradle_test_pattern.search(line)
        if match:
            test_class, method_name, status = match.groups()
            if status == 'FAILED':
                failed_tests.add(method_name)
                results[method_name] = False
            elif status == 'PASSED':
                results[method_name] = True
    
    return results

def parse_maven_test_output(output: str) -> Dict[str, bool]:
    """
    Parse Maven test output to extract test pass/fail status.
    
    Args:
        output: Raw output from Maven test execution
        
    Returns:
        Dictionary mapping test method names to pass/fail status
    """
    results = {}
    
    # Maven typically shows test results like:
    # Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
    # or individual test results in verbose mode
    
    # Look for test execution summary
    summary_pattern = re.compile(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+)')
    
    for line in output.split('\n'):
        match = summary_pattern.search(line)
        if match:
            total, failures, errors = map(int, match.groups())
            # If no failures and no errors, all tests passed
            if failures == 0 and errors == 0:
                # We can't determine individual test names from summary, so mark as success
                results['all_tests'] = True
            else:
                results['all_tests'] = False
    
    # Look for individual test results in verbose output
    test_pattern = re.compile(r'Running (\w+)')
    for line in output.split('\n'):
        match = test_pattern.search(line)
        if match:
            test_name = match.group(1)
            # Check if this test passed by looking for success indicators
            if 'BUILD SUCCESS' in output:
                results[test_name] = True
            else:
                results[test_name] = False
    
    return results

def parse_test_output(output: str, build_system: str) -> Dict[str, bool]:
    """
    Parse test execution output based on the build system.
    
    Args:
        output: Raw output from test execution
        build_system: "gradle" or "maven"
        
    Returns:
        Dictionary mapping test method names to pass/fail status
    """
    if build_system == "gradle":
        return parse_gradle_test_output(output)
    elif build_system == "maven":
        return parse_maven_test_output(output)
    else:
        raise ValueError(f"Unsupported build system: {build_system}")

def extract_test_method_names(test_content: str) -> List[str]:
    """
    Extract test method names from a test class content.
    
    Args:
        test_content: The content of a test class file
        
    Returns:
        List of test method names
    """
    method_names = []
    
    # Look for @Test annotations followed by method declarations
    # Handle both single-line and multi-line @Test annotations
    # Pattern 1: @Test and method declaration on same line
    test_pattern1 = re.compile(r'@Test\s+public\s+void\s+(\w+)\s*\(')
    
    # Pattern 2: @Test on separate line from method declaration
    test_pattern2 = re.compile(r'@Test\s*\n\s*public\s+void\s+(\w+)\s*\(')
    
    # Pattern 3: @Test with expected exception on separate line
    test_pattern3 = re.compile(r'@Test\s*\([^)]*\)\s*\n\s*public\s+void\s+(\w+)\s*\(')
    
    # Search with all patterns
    for pattern in [test_pattern1, test_pattern2, test_pattern3]:
        for match in pattern.finditer(test_content):
            method_names.append(match.group(1))
    
    # Remove duplicates while preserving order
    seen = set()
    unique_method_names = []
    for name in method_names:
        if name not in seen:
            seen.add(name)
            unique_method_names.append(name)
    
    return unique_method_names

def extract_test_method_names_from_list(test_methods: List[str]) -> List[str]:
    """
    Extract method names from a list of individual test method strings.
    Uses the same regex pattern used throughout the codebase for consistency.
    
    Args:
        test_methods: List of individual test method strings
        
    Returns:
        List of unique test method names
    """
    method_names = []
    for test_method in test_methods:
        method_name_match = re.search(r'public\s+void\s+(\w+)\s*\(', test_method)
        if method_name_match:
            method_names.append(method_name_match.group(1))
    return list(set(method_names))  # Remove duplicates

def get_fully_qualified_test_name(package: str, class_name: str, method_name: str) -> str:
    """
    Get the fully qualified test name for execution.
    
    Args:
        package: Package name (e.g., "com.example")
        class_name: Test class name (e.g., "MyTest")
        method_name: Test method name (e.g., "testMethod")
        
    Returns:
        Fully qualified test name
    """
    return f"{package}.{class_name}.{method_name}" 