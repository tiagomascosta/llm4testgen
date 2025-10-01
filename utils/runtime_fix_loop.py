import logging
from typing import Tuple, List, Optional
from pathlib import Path
from prompting import build_runtime_fix_prompt, RuntimeCodeOnly
from llm import OllamaClient
from utils.test_executor import run_individual_test, categorize_test_failure
from utils.compile_fix_loop import count_errors, filter_maven_compilation_errors
from config import test_config
from utils.colors import Colors, step, success, error, warning, info, summary
import os
import subprocess
import re

logger = logging.getLogger(__name__)

def extract_execution_progress(runtime_error_output: str, test_method_name: str) -> int:
    """
    Extract the line number where the runtime error occurred in the test method.
    
    Args:
        runtime_error_output: The test execution output
        test_method_name: Name of the test method
        
    Returns:
        Line number where error occurred, or 0 if cannot determine
    """
    lines = runtime_error_output.split('\n')
    
    for line in lines:
        # Look for stack trace lines like:
        # Maven format: "at TestClass.testMethod(TestClass.java:25)"
        # Maven format: "at com.example.TestClass.testMethod(TestClass.java:25)"
        # Gradle format: "    java.lang.NullPointerException at TotemProtocolDecoderTest.java:50"
        # Gradle format: "    org.package.ExceptionName at File.java:line"
        
        # Check for Maven format first
        if test_method_name in line and '.java:' in line:
            match = re.search(r'\.java:(\d+)', line)
            if match:
                return int(match.group(1))
        
        # Check for Gradle format (indented exception lines)
        if line.strip().startswith('java.') or line.strip().startswith('org.') or line.strip().startswith('com.'):
            # Look for pattern: "ExceptionName at File.java:line"
            match = re.search(r'at\s+(\w+)\.java:(\d+)', line)
            if match:
                return int(match.group(2))
    
    return 0

def is_compilation_error(test_output: str, build_system: str) -> bool:
    """
    Check if the test output indicates a compilation error.
    
    Args:
        test_output: The test execution output
        build_system: Build system type ("gradle" or "maven")
        
    Returns:
        True if compilation failed, False otherwise
    """
    output_lower = test_output.lower()
    
    # Check for build success indicators (consistent with existing codebase)
    if build_system == "maven":
        if "BUILD SUCCESS" in test_output:
            return False
        # Check for Maven compilation error pattern (exact regex from compile_fix_loop.py)
        if re.search(r"^\[ERROR\] COMPILATION ERROR :\s*$", test_output, re.MULTILINE):
            return True
        # Check for compilation error patterns in Maven
        if "compilation failure" in output_lower or "compilation error" in output_lower:
            return True
        # Check for specific Maven compilation error patterns
        if "[error]" in output_lower and ("cannot find symbol" in output_lower or "expected" in output_lower or "missing" in output_lower):
            return True
    else:  # Gradle
        if "BUILD SUCCESSFUL" in test_output:
            return False
        # Check for compilation error patterns in Gradle
        if "compilation failed" in output_lower or "compilation error" in output_lower:
            return True
        # Check for specific Gradle compilation error patterns
        if "error:" in output_lower and ("cannot find symbol" in output_lower or "expected" in output_lower or "missing" in output_lower):
            return True
    
    # Check for error count in output (using existing count_errors function)
    error_count = count_errors(test_output)
    if error_count > 0:
        return True
    
    return False

def clean_runtime_error_comment(test_method: str) -> str:
    """
    Remove the runtime error comment from a test method.
    
    Args:
        test_method: The test method that may contain runtime error comments
        
    Returns:
        The test method with runtime error comments removed
    """
    lines = test_method.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Remove the runtime error comment if present
        if '// <-- RUNTIME ERROR OCCURRED HERE' in line:
            # Remove the comment part
            cleaned_line = line.replace('  // <-- RUNTIME ERROR OCCURRED HERE', '')
            cleaned_lines.append(cleaned_line)
        else:
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def runtime_fix_loop(
    test_method: str,
    scaffold: str,
    repo_path: Path,
    build_system: str,
    class_code: str,
    junit_version: int,
    llm_client: OllamaClient,
    runtime_error_output: str,
    test_class: str,
    max_attempts: int = 5,
    recent_successful_tests: List[str] = None,
    max_examples: int = 3,
    mut_body: str = None
) -> Tuple[str, str, int, str]:
    """
    Run the runtime-fix loop to attempt to fix runtime errors in a test method.
    
    Args:
        test_method: The test method that failed with runtime error
        scaffold: The test class scaffold
        repo_path: Path to the repository
        build_system: Build system type ("gradle" or "maven")
        class_code: The class under test code
        junit_version: The JUnit version being used
        llm_client: The LLM client to use for fixes
        runtime_error_output: The runtime error output from test execution
        test_class: Fully qualified test class name
        max_attempts: Maximum number of fix attempts
        recent_successful_tests: List of recent successful test methods for examples
        max_examples: Maximum number of examples to include in runtime-fix prompts
        mut_body: The method under test body (for MUT delimiting)
        
    Returns:
        Tuple of (result_type, final_test_method, attempts_made, best_diagnosis)
        where result_type is one of: "passed", "assertion_error", "timeout", "runtime_error"
    """
    if recent_successful_tests is None:
        recent_successful_tests = []
    
    # Initialize tracking variables
    best_test_method = test_method
    attempts_made = 0
    best_diagnosis = None
    best_error_line = 0
    best_error_output = runtime_error_output  # Track the best error output we've seen
    
    # Extract test method name
    method_name_match = re.search(r'public\s+void\s+(\w+)\s*\(', test_method)
    if not method_name_match:
        logger.error("Could not extract method name from test method")
        return "runtime_error", test_method, 0, None
    
    test_method_name = method_name_match.group(1)
    
    # Get initial progress
    best_progress = extract_execution_progress(runtime_error_output, test_method_name)
    
    # Initialize best_error_line with the initial progress
    best_error_line = best_progress
    
    # Print initial status
    print(f"   {warning('Test method failed with runtime error')} (line {best_progress}), starting runtime-fix loop")
    
    # Get the test file path from config
    test_file_path = test_config.get_test_file_path()
    if not test_file_path:
        logger.error("Could not find test file path in config")
        return "runtime_error", test_method, 0, None
    
    test_file = Path(test_file_path)
    test_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Run the fix loop
    for attempt in range(1, max_attempts + 1):
        attempts_made = attempt
        
        # Build the runtime-fix prompt with examples
        system_message, prompt = build_runtime_fix_prompt(
            test_method=best_test_method,
            scaffold=scaffold,
            runtime_error_output=best_error_output,
            class_code=class_code,
            junit_version=junit_version,
            recent_successful_tests=recent_successful_tests,
            max_examples=max_examples,
            execution_progress=best_progress,
            mut_body=mut_body,
            previous_diagnosis=best_diagnosis,
            previous_error_line=best_error_line,
            build_system=build_system
        )
        
        # Call LLM to get fixed test method
        try:
            response = llm_client.call_structured(
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                schema=RuntimeCodeOnly.model_json_schema(),
                is_code_task=True
            )
            
            # Parse the response
            code_only = RuntimeCodeOnly.model_validate_json(response)
            new_test_method = code_only.code.rstrip()
            new_diagnosis = code_only.diagnosis
            
            # Convert string 'None' to actual None
            if new_diagnosis == 'None':
                new_diagnosis = None
            
            # Check if the response is valid
            if not new_test_method or new_test_method in ("{}", "{ }", "{\n}", "{\r\n}", "{\n    }"):
                print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {warning('Invalid response from LLM')}")
                continue
                
        except Exception as e:
            print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {warning('Failed to get fix from LLM')}")
            continue
        
        # Test the new test method
        # Insert the test method directly into the scaffold
        full_test_file = scaffold
        last_brace_pos = full_test_file.rfind('}')
        if last_brace_pos != -1:
            full_test_file = full_test_file[:last_brace_pos] + new_test_method + '\n' + full_test_file[last_brace_pos:]
        
        test_file.write_text(full_test_file)
        
        try:
            # Run the individual test
            success, new_output = run_individual_test(
                test_class=test_class,
                test_method=test_method_name,
                repo_path=repo_path,
                build_system=build_system,
                timeout=30
            )
            
            # Check if test passed
            if success:
                print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {success('Runtime error fixed')}")
                print(f"   {success('Runtime fix successful after')} {attempts_made} attempts")
                return "passed", new_test_method, attempts_made, new_diagnosis
            
            # Check if this is a compilation error (LLM gave us invalid code)
            if is_compilation_error(new_output, build_system):
                print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {warning('Invalid (Compilation Error)')}")
                continue
            
            # Categorize the failure (only if not a compilation error)
            failure_type = categorize_test_failure(new_output, build_system)
            
            # Handle different failure types
            if failure_type == "timeout":
                print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {warning('Invalid (Timeout)')}")
                print(f"   {error('Runtime fix failed after')} {attempts_made} attempts")
                return "timeout", best_test_method, attempts_made, best_diagnosis
            
            if failure_type == "assertion_error":
                print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {success('Runtime error fixed')}")
                print(f"   {success('Runtime fix successful after')} {attempts_made} attempts")
                return "assertion_error", new_test_method, attempts_made, new_diagnosis
            
            # Still a runtime error - check progress
            current_progress = extract_execution_progress(new_output, test_method_name)
            
            if current_progress > best_progress:
                print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {success('Improved to line')} {current_progress}")
                best_test_method = new_test_method
                best_progress = current_progress
                best_diagnosis = new_diagnosis  # Update diagnosis for the new line
                best_error_line = current_progress
                best_error_output = new_output
            else:
                print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {warning('Still on line')} {current_progress}")
                # Update diagnosis even if we're on the same line, as long as we have a valid diagnosis
                if new_diagnosis and (best_diagnosis is None or best_diagnosis == 'None'):
                    best_diagnosis = new_diagnosis
                # Do NOT update best_error_output when we regress - keep the best we've seen
        
        finally:
            # Clean up the test file after test attempt
            if test_file.exists():
                test_file.unlink()
    
    # If we get here, we've exhausted all attempts
    print(f"   {error('Runtime fix failed after')} {attempts_made} attempts")
    return "runtime_error", best_test_method, attempts_made, best_diagnosis 