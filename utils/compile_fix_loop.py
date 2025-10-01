import logging
from typing import Tuple, List, Optional
from pathlib import Path
from prompting import build_compile_fix_prompt, CodeOnly
from llm import OllamaClient
from utils.compiler import assemble_and_compile_test
from config import test_config
from utils.colors import Colors, step, success, error, warning, info, summary
import os
import subprocess
import re

logger = logging.getLogger(__name__)

def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI color codes from text to make pattern matching easier.
    
    Args:
        text: Text that may contain ANSI color codes
        
    Returns:
        Text with ANSI color codes removed
    """
    # Remove ANSI color codes: \x1b[ followed by numbers, semicolons, and ending with 'm'
    return re.sub(r'\x1b\[[0-9;]*m', '', text)

def filter_maven_compilation_errors(compilation_output: str) -> str:
    """
    Filter Maven compilation output to show only the actual errors.
    
    Args:
        compilation_output: Full Maven compilation output (may include STDOUT/STDERR labels)
        
    Returns:
        Filtered output showing only compilation errors
    """
    if not compilation_output:
        return compilation_output
    
    # Extract STDOUT content if the output has STDOUT/STDERR labels
    stdout_content = compilation_output
    if "STDOUT:" in compilation_output:
        parts = compilation_output.split("STDOUT:")
        if len(parts) > 1:
            stdout_part = parts[1]
            if "STDERR:" in stdout_part:
                stdout_content = stdout_part.split("STDERR:")[0]
            else:
                stdout_content = stdout_part
    
    # Strip ANSI color codes to make pattern matching easier
    stdout_content = strip_ansi_codes(stdout_content)
    
    # Use regex to find the line '[ERROR] COMPILATION ERROR :'
    pattern = re.compile(r"^\[ERROR\] COMPILATION ERROR :\s*$", re.MULTILINE)
    match = pattern.search(stdout_content)
    if match:
        # Find the start of the line immediately above the match
        start_pos = match.start()
        # Look for the previous newline to find the start of the previous line
        prev_newline = stdout_content.rfind('\n', 0, start_pos)
        if prev_newline != -1:
            # Look for the newline before that to get the start of the line above
            line_above_start = stdout_content.rfind('\n', 0, prev_newline)
            if line_above_start != -1:
                # Include from the line above the match
                return stdout_content[line_above_start + 1:].lstrip('\n')
            else:
                # If no newline before prev_newline, start from the beginning
                return stdout_content[prev_newline + 1:].lstrip('\n')
        else:
            # If no previous newline found, start from the match
            return stdout_content[match.start():].lstrip('\n')
    
    # If no pattern matched, return the full output
        print("[WARN] '[ERROR] COMPILATION ERROR :' not found in Maven output.")
        return stdout_content.strip()

def count_errors(stderr_text: str) -> int:
    """
    Count the number of compilation errors in stderr output.
    
    Args:
        stderr_text: The stderr output from compilation
        
    Returns:
        int: Number of error lines found
    """
    if not stderr_text:
        return 0
    
    # Strip ANSI color codes to make pattern matching easier
    stderr_text = strip_ansi_codes(stderr_text)
    
    # Look for "X errors" pattern in the output
    match = re.search(r'(\d+)\s+errors?', stderr_text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    # If no "X errors" pattern found, count lines with "[ERROR]" in them
    error_lines = [line for line in stderr_text.split('\n') if '[ERROR]' in line and 'error:' in line.lower()]
    return len(error_lines)

def compile_fix_loop(
    test_method: str,
    scaffold: str,
    repo_path: Path,
    java_home: str,
    class_code: str,
    junit_version: int,
    llm_client: OllamaClient,
    compilation_errors: str,
    max_attempts: int = 7,
    recent_successful_tests: List[str] = None,
    max_examples: int = 3
) -> Tuple[bool, str, int]:
    """
    Run the compile-fix loop to attempt to fix compilation errors in a test method.
    
    Args:
        test_method: The test method that failed to compile
        scaffold: The test class scaffold
        repo_path: Path to the repository
        java_home: Path to Java home directory
        class_code: The class under test code
        junit_version: The JUnit version being used
        llm_client: The LLM client to use for fixes
        compilation_errors: The compilation errors from the failed compilation
        max_attempts: Maximum number of fix attempts
        recent_successful_tests: List of recent successful test methods for examples
        max_examples: Maximum number of examples to include in compile-fix prompts
        
    Returns:
        Tuple of (success, final_test_method, attempts_made)
    """
    if recent_successful_tests is None:
        recent_successful_tests = []
    
    # Initialize tracking variables
    best_test_method = test_method
    best_error_count = float('inf')
    attempts_made = 0
    
    # Get the test file path from config (this should be the actual test file location)
    test_file_path = test_config.get_test_file_path()
    if not test_file_path:
        logger.error("Could not find test file path in config")
        return False, test_method, 0
    
    test_file = Path(test_file_path)
    
    # Ensure the test directory exists
    test_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Get Java version and path from global config (like compile_java_file.py does)
    java_version = test_config.get_java_version()
    java_path = test_config.get_java_path()
    
    if not java_path:
        logger.error("Java path not set in test_config")
        return False, test_method, 0
    
    # Set up compilation command
    if (repo_path / 'pom.xml').exists():
        # Maven - include skip flags to avoid Spotless formatting issues
        cmd = ["mvn", "clean", "compile", "test-compile", "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dfindbugs.skip=true","-Dpmd.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true", "-Denforcer.skip=true"]
    else:
        # Gradle - add --no-daemon flag to make compilation stricter and more consistent with test execution
        cmd = ["./gradlew", "compileTestJava", "--no-daemon"] if (repo_path / "gradlew").exists() else ["gradle", "compileTestJava", "--no-daemon"]
    
    env = os.environ.copy()
    env['JAVA_HOME'] = java_path
    env['PATH'] = f"{java_path}/bin:{env['PATH']}"
    env['GRADLE_OPTS'] = f"-Dorg.gradle.java.home={java_path}"
    
    # Count errors from the initial compilation
    best_error_count = count_errors(compilation_errors)
    print(f"   {warning('Test method failed to compile')} ({best_error_count} errors), starting compile-fix loop")
    
    # Filter compilation errors for Maven projects
    filtered_compilation_errors = compilation_errors
    if (repo_path / 'pom.xml').exists():
        filtered_compilation_errors = filter_maven_compilation_errors(compilation_errors)
    
    # Run the fix loop
    for attempt in range(1, max_attempts + 1):
        attempts_made = attempt
        
        # Build the compile-fix prompt with examples
        system_message, prompt = build_compile_fix_prompt(
            test_method=best_test_method,
            scaffold=scaffold,
            compilation_errors=filtered_compilation_errors,
            class_code=class_code,
            junit_version=junit_version,
            recent_successful_tests=recent_successful_tests,
            max_examples=max_examples
        )
        
        # Call LLM to get fixed test method
        try:
            response = llm_client.call_structured(
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                schema=CodeOnly.model_json_schema(),
                is_code_task=True
            )
            
            # Parse the response
            code_only = CodeOnly.model_validate_json(response)
            new_test_method = code_only.code.rstrip()
            
            # Check if the response is valid
            if not new_test_method or new_test_method in ("{}", "{ }", "{\n}", "{\r\n}", "{\n    }"):
                print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {warning('Invalid response from LLM')}")
                continue
                
        except Exception as e:
            print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {warning('Failed to get fix from LLM')}")
            continue
        
        # Compile the new test method to check if it works
        # Insert the test method directly into the scaffold (same as in the prompt)
        full_test_file = scaffold
        last_brace_pos = full_test_file.rfind('}')
        if last_brace_pos != -1:
            # Insert the test method before the closing brace
            full_test_file = full_test_file[:last_brace_pos] + new_test_method + '\n' + full_test_file[last_brace_pos:]
        
        test_file.write_text(full_test_file)
        
        try:
            result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, env=env)
            new_compilation_errors = f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
            new_error_count = count_errors(new_compilation_errors)
            
            # Filter new compilation errors for Maven projects
            filtered_new_compilation_errors = new_compilation_errors
            if (repo_path / 'pom.xml').exists():
                filtered_new_compilation_errors = filter_maven_compilation_errors(new_compilation_errors)
            
            # Check if this attempt actually succeeded
            if result.returncode == 0:
                print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {success('Compilation successful')}")
                return True, new_test_method, attempts_made
            
        finally:
            # Clean up the test file after compilation attempt
            if test_file.exists():
                test_file.unlink()
        
        # Update the best test method and error count for the next iteration
        if new_error_count <= best_error_count:
            if new_error_count < best_error_count:
                print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {success('Improved to')} {new_error_count} errors")
            else:
                print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {warning('Still')} {best_error_count} errors")
                
            best_test_method = new_test_method
            best_error_count = new_error_count
            compilation_errors = new_compilation_errors
            filtered_compilation_errors = filtered_new_compilation_errors
        else:
            # Error count increased, don't update best
            print(f"   {info('Fix attempt')} {attempt}/{max_attempts} - {warning('Still')} {best_error_count} errors")
    
    # If we get here, we've exhausted all attempts
    return False, best_test_method, attempts_made 