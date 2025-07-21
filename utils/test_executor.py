import subprocess
import os
import time
import re
from pathlib import Path
from typing import Tuple, Optional, List, Dict
from .build_system_detector import BuildSystem
from .test_result_parser import parse_test_output, extract_test_method_names
from config import test_config

def save_assertion_failure_file(
    isolated_test_content: str,
    method_name: str, 
    class_name: str,
    package: str,
    output_dir: Path,
    counter: int
) -> None:
    """
    Save assertion failure files to potential_bugs directory.
    
    Args:
        isolated_test_content: The content of the isolated test file
        method_name: Name of the test method that failed
        class_name: Name of the test class
        package: Package name
        output_dir: Base output directory
        counter: Sequential counter for unique filenames
    """
    try:
        # Create potential_bugs directory
        potential_bugs_dir = output_dir / "potential_bugs"
        potential_bugs_dir.mkdir(parents=True, exist_ok=True)
        
        # Create filename with sequential number: {method}_{class}_{number:02d}Test.java
        filename = f"{method_name}_{class_name}_{counter:02d}Test.java"
        file_path = potential_bugs_dir / filename
        
        # Create the new class name that matches the filename
        new_class_name = f"{method_name}_{class_name}_{counter:02d}Test"
        
        # Update the class name inside the file content
        updated_content = isolated_test_content.replace(
            f"public class {class_name}Test",
            f"public class {new_class_name}"
        ).replace(
            f"public class {class_name}",
            f"public class {new_class_name}"
        )
        
        # Save the file
        file_path.write_text(updated_content, encoding='utf-8')
        
        print(f"   💾 Saved assertion failure: {filename}")
        
    except Exception as e:
        print(f"   ⚠️ Failed to save assertion failure file: {e}")

def remove_ansi_colors(text: str) -> str:
    """
    Remove ANSI color codes from text to facilitate regex matching.
    """
    # Remove ANSI escape sequences (color codes, cursor movement, etc.)
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def run_individual_test(
    test_class: str, 
    test_method: str, 
    repo_path: Path, 
    build_system: BuildSystem,
    timeout: int = 30
) -> Tuple[bool, str]:
    """
    Run a single test method and return its execution result.
    
    Args:
        test_class: Fully qualified test class name (e.g., "com.example.MyTest")
        test_method: Test method name (e.g., "testMethod")
        repo_path: Path to the repository root
        build_system: "gradle" or "maven"
        timeout: Timeout in seconds for test execution
        
    Returns:
        Tuple of (success: bool, output: str)
    """
    try:
        if build_system == "gradle":
            # Check for Gradle wrapper
            gradle_wrapper = repo_path / "gradlew"
            if gradle_wrapper.exists():
                # Make gradlew executable
                gradle_wrapper.chmod(0o755)
                cmd = [str(gradle_wrapper), "test", f"--tests={test_class}", "--stacktrace"]
            else:
                cmd = ["gradle", "test", f"--tests={test_class}", "--stacktrace"]
                
        elif build_system == "maven":
            # Extract class name from fully qualified name for Maven
            class_name = test_class.split('.')[-1]
            cmd = ["mvn", "test", f"-Dtest={class_name}", "-e", "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true"]
        else:
            raise ValueError(f"Unsupported build system: {build_system}")
        
        # Set environment variables for Java
        env = os.environ.copy()
        # Get Java version and path from global config (like compile_java_file.py does)
        java_version = test_config.get_java_version()
        java_path = test_config.get_java_path()
        
        if java_path:
            env['JAVA_HOME'] = java_path
            env['PATH'] = f"{java_path}/bin:{env['PATH']}"
            if build_system == "gradle":
                env['GRADLE_OPTS'] = f"-Dorg.gradle.java.home={java_path}"
        else:
            print("WARNING: Java path not set in test_config")
        
        # Run the test
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
        
        # Combine stdout and stderr
        output = result.stdout + "\n" + result.stderr
        
        # Determine success based on exit code and output
        success = result.returncode == 0
        
        # Parse the output to get more accurate test results based on build system
        if build_system == "gradle":
            # First check for BUILD SUCCESSFUL - this is the primary indicator
            if 'BUILD SUCCESSFUL' in output and 'FAILED' not in output:
                # If build is successful and no FAILED pattern found, assume test passed
                success = True
            else:
                # Gradle pattern: "1 test completed, 0 failed"
                test_completion_pattern = re.search(r'(\d+) tests? completed, (\d+) failed', output)
                if test_completion_pattern:
                    total_tests = int(test_completion_pattern.group(1))
                    failed_tests = int(test_completion_pattern.group(2))
                    
                    # If there are failed tests, the test failed
                    if failed_tests > 0:
                        success = False
                    else:
                        success = True
                else:
                    # Fallback: look for test failure patterns in the output
                    # Check for Gradle test failure patterns like "ClassName > methodName FAILED"
                    if ' > ' in output and ' FAILED' in output:
                        success = False
                    else:
                        # Fallback to build success/failure
                        success = result.returncode == 0
        elif build_system == "maven":
            # Maven pattern: "Tests run: 1, Failures: 0, Errors: 0"
            test_completion_pattern = re.search(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+)', output)
            if test_completion_pattern:
                total_tests = int(test_completion_pattern.group(1))
                failed_tests = int(test_completion_pattern.group(2))
                error_tests = int(test_completion_pattern.group(3))
                
                # If there are failures or errors, the test failed
                if failed_tests > 0 or error_tests > 0:
                    success = False
                else:
                    success = True
            else:
                # Fallback to build success/failure
                success = result.returncode == 0
        
        return success, output
        
    except subprocess.TimeoutExpired:
        return False, f"Test execution timed out after {timeout} seconds"
    except Exception as e:
        return False, f"Test execution failed: {str(e)}"

def run_test_class(
    test_class: str, 
    repo_path: Path, 
    build_system: BuildSystem,
    final_tests: List[Tuple],  # Make final_tests required
    scaffold: str = None,  # Add scaffold parameter
    timeout: int = 60,
    test_file_path: Path = None,
    output_dir: Path = None,
    json_logger = None,  # Add JSON logger parameter
    # Add new parameters for runtime fix loop
    class_code: str = None,
    junit_version: int = None,
    llm_client = None,
    args = None,
    mut_body: str = None
) -> Tuple[Dict[str, bool], Dict[str, str], Dict[str, str]]:
    """
    Run all tests in a test class both individually and then all together.
    
    Args:
        test_class: Fully qualified test class name
        repo_path: Path to the repository root
        build_system: Build system type
        final_tests: List of (scenario, test_method) tuples for direct execution
        scaffold: The test scaffold to use for assembly
        timeout: Timeout in seconds for test execution
        test_file_path: Optional path to the test file (if not provided, will be constructed from test_class)
        output_dir: Base output directory for saving assertion failure files
        json_logger: Optional JSON logger to update with execution results
        class_code: The class code for runtime fix loop
        junit_version: The JUnit version for runtime fix loop
        llm_client: The LLM client for runtime fix loop
        args: The arguments for runtime fix loop
        mut_body: The mut_body for runtime fix loop
        
    Returns:
        Tuple of (individual_results: Dict[str, bool], 
                 individual_failures: Dict[str, str], group_failures: Dict[str, str])
    """
    
    try:
        # First, extract test method names from the test file
        class_name = test_class.split('.')[-1]
        package = '.'.join(test_class.split('.')[:-1])
        
        # Find the test file - use provided path or construct from test_class
        if test_file_path is None:
            test_file_path = repo_path / "src" / "test" / "java" / package.replace('.', '/') / f"{class_name}.java"
        
        # Set environment variables
        env = os.environ.copy()
        # Get Java version and path from global config (like compile_java_file.py does)
        java_version = test_config.get_java_version()
        java_path = test_config.get_java_path()
        
        if java_path:
            env['JAVA_HOME'] = java_path
            env['PATH'] = f"{java_path}/bin:{env['PATH']}"
            if build_system == "gradle":
                env['GRADLE_OPTS'] = f"-Dorg.gradle.java.home={java_path}"
        else:
            print("WARNING: Java path not set in test_config")
        
        all_output = []
        individual_results = {}
        individual_failures = {}  # Track failure categories for individual tests
        overall_success = True
        
        # Initialize recent successful tests for runtime fix loop
        recent_successful_tests = []
        
        # Initialize individual test entries in JSON logger
        if json_logger and final_tests:
            for scenario, test_method in final_tests:
                method_name_match = re.search(r'public\s+void\s+(\w+)\s*\(', test_method)
                if method_name_match:
                    method_name = method_name_match.group(1)
                    json_logger.initialize_individual_test_entry(method_name)
        
        # STEP 1: Run each test method individually (isolated)
        print("🧪 STEP 1: Running tests individually (isolated)\n")
        
        # Use final_tests for direct execution
        if final_tests:
            # Direct execution from final_tests tuple
            for idx, (scenario, test_method) in enumerate(final_tests, 1):
                # Extract test method name directly from the method content
                method_name_match = re.search(r'public\s+void\s+(\w+)\s*\(', test_method)
                if method_name_match:
                    method_name = method_name_match.group(1)
                else:
                    print(f"   ❌ Could not extract method name for test {idx}")
                    continue
                
                print(f"   ✓ Running test {method_name}")
                
                # Create an isolated test file for this specific test method
                isolated_test_content = create_isolated_test_with_scaffold(
                    test_method, method_name, class_name, package, scaffold
                )
                
                # Use the same class name as the final assembled test file
                isolated_test_file = test_file_path.parent / f"{class_name}.java"
                isolated_test_file.write_text(isolated_test_content)
                
                try:
                    # Run the individual test
                    if build_system == "gradle":
                        gradle_wrapper = repo_path / "gradlew"
                        if gradle_wrapper.exists():
                            gradle_wrapper.chmod(0o755)
                            cmd = [str(gradle_wrapper), "test", f"--tests={test_class}", "--stacktrace"]
                        else:
                            cmd = ["gradle", "test", f"--tests={test_class}", "--stacktrace"]
                            
                    elif build_system == "maven":
                        cmd = ["mvn", "test", f"-Dtest={class_name}", "-e", "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true"]
                    else:
                        raise ValueError(f"Unsupported build system: {build_system}")
                    
                    result = subprocess.run(
                        cmd,
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        env=env
                    )
                    
                    # Combine stdout and stderr
                    test_output = result.stdout + "\n" + result.stderr
                    
                    # Determine success based on exit code and output
                    test_success = result.returncode == 0
                    
                    # Parse the output to get more accurate test results
                    # Look for patterns like "1 test completed, 0 failed" or "1 test completed, 1 failed"
                    test_completion_pattern = re.search(r'(\d+) tests? completed, (\d+) failed', test_output)
                    if test_completion_pattern:
                        total_tests = int(test_completion_pattern.group(1))
                        failed_tests = int(test_completion_pattern.group(2))
                        passed_tests = total_tests - failed_tests
                        
                        # If there are failed tests, the test failed
                        if failed_tests > 0:
                            test_success = False
                        else:
                            test_success = True
                    else:
                        # Fallback: look for test failure patterns in the output
                        # Check for Gradle test failure patterns like "ClassName > methodName FAILED"
                        if ' > ' in test_output and ' FAILED' in test_output:
                            test_success = False
                        elif 'BUILD SUCCESSFUL' in test_output and 'FAILED' not in test_output:
                            # If build is successful and no FAILED pattern found, assume test passed
                            test_success = True
                        else:
                            # Fallback to build success/failure
                            test_success = result.returncode == 0
                    
                    individual_results[method_name] = test_success
                    
                    # Categorize failure if test failed
                    if not test_success:
                        failure_category = categorize_test_failure(test_output, build_system)
                        individual_failures[method_name] = failure_category
                        overall_success = False
                        # Show concise failure status
                        failure_type = failure_category.replace('_', ' ').title()
                        print(f"   ❌ Failed ({failure_type})")
                        
                        # Add tests with assertion errors to successful tests list (they are runtime-successful)
                        if failure_category == "assertion_error":
                            # Check if this test method is already in the list to avoid duplicates
                            if test_method not in recent_successful_tests:
                                recent_successful_tests.append(test_method)
                                # Keep only the most recent examples
                                if args and hasattr(args, 'max_runtime_fix_examples') and len(recent_successful_tests) > args.max_runtime_fix_examples:
                                    recent_successful_tests.pop(0)
                            else:
                                print(f"   ℹ️ Test method already in examples list (skipping duplicate)")
                        
                        # Runtime fix loop integration
                        if failure_category == "runtime_error" and args and hasattr(args, 'max_runtime_fix_attempts') and args.max_runtime_fix_attempts > 0:
                            try:
                                # Import the runtime-fix loop
                                from utils.runtime_fix_loop import runtime_fix_loop, clean_runtime_error_comment
                                
                                # Check if required parameters are available
                                if not class_code:
                                    print(f"   ⚠️ Runtime fix skipped: class_code is missing")
                                    continue
                                if not junit_version:
                                    print(f"   ⚠️ Runtime fix skipped: junit_version is missing")
                                    continue
                                if not llm_client:
                                    print(f"   ⚠️ Runtime fix skipped: llm_client is missing")
                                    continue
                                
                                # Run the runtime-fix loop
                                fix_result, final_test_method, attempts_made, diagnosis = runtime_fix_loop(
                                    test_method=test_method,
                                    scaffold=scaffold,
                                    repo_path=repo_path,
                                    build_system=build_system,
                                    class_code=class_code,
                                    junit_version=junit_version,
                                    llm_client=llm_client,
                                    runtime_error_output=test_output,
                                    test_class=test_class,
                                    max_attempts=args.max_runtime_fix_attempts,
                                    recent_successful_tests=recent_successful_tests,
                                    max_examples=args.max_runtime_fix_examples,
                                    mut_body=mut_body
                                )
                                
                                if fix_result in ["passed", "assertion_error"]:
                                    print(f"   ✅ Runtime error fixed for {method_name} after {attempts_made} attempts")
                                    
                                    # Update individual results based on runtime fix loop result
                                    if fix_result == "passed":
                                        individual_results[method_name] = True
                                        individual_failures[method_name] = None  # Clear the failure
                                        overall_success = True
                                        print(f"   ✅ Fixed test method passes")
                                    else:  # assertion_error
                                        individual_results[method_name] = False
                                        individual_failures[method_name] = "assertion_error"
                                        overall_success = False
                                        print(f"   ❌ Fixed test method fails with assertion error")
                                    
                                    # Update final_tests with the fixed method
                                    for i, (scenario, original_test_method) in enumerate(final_tests):
                                        # Extract method name from original test method
                                        original_method_name_match = re.search(r'public\s+void\s+(\w+)\s*\(', original_test_method)
                                        if original_method_name_match and original_method_name_match.group(1) == method_name:
                                            # Replace the original test method with the fixed one
                                            final_tests[i] = (scenario, final_test_method)
                                            break
                                    
                                    # Add the fixed test method to recent successful tests
                                    recent_successful_tests.append(final_test_method)
                                    # Keep only the most recent examples
                                    if len(recent_successful_tests) > args.max_runtime_fix_examples:
                                        recent_successful_tests.pop(0)
                                    
                                    # Log successful runtime fix
                                    if json_logger:
                                        json_logger.add_individual_test_runtime_fix_result(
                                            test_name=method_name,
                                            runtime_fix_attempted=True,
                                            runtime_fix_successful=True,
                                            attempts_made=attempts_made,
                                            final_outcome=fix_result
                                        )
                                elif fix_result == "timeout":
                                    print(f"   ⏰ Runtime fix failed with timeout after {attempts_made} attempts")
                                    individual_results[method_name] = False
                                    individual_failures[method_name] = "timeout"
                                    overall_success = False
                                    
                                    # Log timeout runtime fix
                                    if json_logger:
                                        json_logger.add_individual_test_runtime_fix_result(
                                            test_name=method_name,
                                            runtime_fix_attempted=True,
                                            runtime_fix_successful=False,
                                            attempts_made=attempts_made,
                                            final_outcome="timeout"
                                        )
                                else:  # runtime_error
                                    print(f"   ❌ Runtime fix failed after {attempts_made} attempts")
                                    individual_results[method_name] = False
                                    individual_failures[method_name] = "runtime_error"
                                    overall_success = False
                                    
                                    # Log failed runtime fix
                                    if json_logger:
                                        json_logger.add_individual_test_runtime_fix_result(
                                            test_name=method_name,
                                            runtime_fix_attempted=True,
                                            runtime_fix_successful=False,
                                            attempts_made=attempts_made,
                                            final_outcome="runtime_error"
                                        )
                            except Exception as fix_error:
                                print(f"   ⚠️ Runtime fix loop failed with error: {str(fix_error)}")
                                # Continue with the test as failed, don't re-raise the exception
                                # Log runtime fix attempt that failed due to exception
                                if json_logger:
                                    json_logger.add_individual_test_runtime_fix_result(
                                        test_name=method_name,
                                        runtime_fix_attempted=True,
                                        runtime_fix_successful=False,
                                        attempts_made=0,
                                        final_outcome=failure_category
                                    )
                        else:
                            # Log test that failed but didn't trigger runtime fix
                            if json_logger:
                                json_logger.add_individual_test_runtime_fix_result(
                                    test_name=method_name,
                                    runtime_fix_attempted=False
                                )
                    else:
                        print(f"   ✅ Passed")
                        # Add successful test to recent successful tests for runtime fix examples
                        recent_successful_tests.append(test_method)
                        # Keep only the most recent examples
                        if args and hasattr(args, 'max_runtime_fix_examples') and len(recent_successful_tests) > args.max_runtime_fix_examples:
                            recent_successful_tests.pop(0)
                        
                        # Log test that didn't use runtime fix
                        if json_logger:
                            json_logger.add_individual_test_runtime_fix_result(
                                test_name=method_name,
                                runtime_fix_attempted=False
                            )
                    
                    # Save assertion failure files (just before cleanup)
                    if output_dir and not test_success and individual_failures.get(method_name) == "assertion_error":
                        # Count how many assertion failures we've seen so far
                        assertion_failure_count = sum(1 for failure_type in individual_failures.values() 
                                                    if failure_type == "assertion_error")
                        save_assertion_failure_file(
                            isolated_test_content=isolated_test_content,
                            method_name=method_name,
                            class_name=class_name,
                            package=package,
                            output_dir=output_dir,
                            counter=assertion_failure_count
                        )
                    
                except subprocess.TimeoutExpired:
                    print(f"   ⏰ Timeout")
                    individual_results[method_name] = False
                    individual_failures[method_name] = "timeout"
                    overall_success = False
                    all_output.append(f"=== INDIVIDUAL TEST: {method_name} ===")
                    all_output.append(f"TIMEOUT after {timeout} seconds")
                    all_output.append("=" * 50)
                    
                    # Log timeout test that didn't use runtime fix
                    if json_logger:
                        json_logger.add_individual_test_runtime_fix_result(
                            test_name=method_name,
                            runtime_fix_attempted=False
                        )
                except Exception as e:
                    print(f"   💥 Error")
                    individual_results[method_name] = False
                    individual_failures[method_name] = "runtime_error"
                    overall_success = False
                    all_output.append(f"=== INDIVIDUAL TEST: {method_name} ===")
                    all_output.append(f"ERROR: {str(e)}")
                    all_output.append("=" * 50)
                    
                    # Log exception test that didn't use runtime fix
                    if json_logger:
                        json_logger.add_individual_test_runtime_fix_result(
                            test_name=method_name,
                            runtime_fix_attempted=False
                        )
                
                finally:
                    # Clean up the isolated test file
                    if isolated_test_file.exists():
                        isolated_test_file.unlink()
            
            # Store the test methods list for group execution
            test_methods = list(individual_results.keys())
        else:
            # No final_tests provided - this should not happen in our new flow
            print("ERROR: No final_tests provided - cannot execute individual tests")
            return {}, {}, {}
        
        # Print detailed individual test summary
        individual_summary = create_detailed_summary(individual_failures, test_methods, "Individual", json_logger)
        print(individual_summary)
        
        # Filter out timeout tests from group runs
        timeout_tests = [method for method, result in individual_results.items() 
                        if individual_failures.get(method) == "timeout"]
        
        if timeout_tests:
            print(f"\n⚠️ Excluding {len(timeout_tests)} timeout tests from group runs: {timeout_tests}")
            test_methods_for_group = [method for method in test_methods 
                                     if method not in timeout_tests]
            
            # Create a filtered version of the test content that excludes timeout tests
            print(f"🔧 Creating filtered test file content (excluding timeout tests)...")
            # Create the test content from passing tests
            passing_tests = [(scenario, test_method) for scenario, test_method in final_tests 
                           if individual_results.get(re.search(r'public\s+void\s+(\w+)\s*\(', test_method).group(1), False)]
            filtered_test_content = create_filtered_test_content_from_tuples(passing_tests, timeout_tests, class_name, scaffold)
            
            # Write the filtered test file to disk before running group tests
            test_file_path.write_text(filtered_test_content)
        else:
            test_methods_for_group = test_methods
            
            # Create the test content from all tests
            test_content = create_test_content_from_tuples(final_tests, class_name, scaffold)
            
            # Write the original test file to disk before running group tests
            test_file_path.write_text(test_content)
        
        # Show which tests were excluded from analysis
        if timeout_tests:
            print(f"\n⚠️ Tests Excluded from Analysis (but still in file):")
            for i, method_name in enumerate(timeout_tests, 1):
                print(f"   {i}. {method_name}")
        
        # Force recompilation to ensure Maven uses the updated test file
        if build_system == "gradle":
            gradle_wrapper = repo_path / "gradlew"
            if gradle_wrapper.exists():
                gradle_wrapper.chmod(0o755)
                clean_cmd = [str(gradle_wrapper), "clean", "testClasses"]
            else:
                clean_cmd = ["gradle", "clean", "testClasses"]
        elif build_system == "maven":
            clean_cmd = ["mvn", "clean", "test-compile", "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true"]
        else:
            raise ValueError(f"Unsupported build system: {build_system}")
        
        try:
            subprocess.run(
                clean_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )
        except Exception as e:
            print(f"   ⚠️ Recompilation failed: {e}")
        
        # STEP 2: Run all tests together 5 times to filter flaky tests
 
        print("\n\n🧪 STEP 2: Running tests in group (5 iterations)\n")
        
        if build_system == "gradle":
            gradle_wrapper = repo_path / "gradlew"
            if gradle_wrapper.exists():
                gradle_wrapper.chmod(0o755)
                cmd = [str(gradle_wrapper), "test", f"--tests={test_class}"]
            else:
                cmd = ["gradle", "test", f"--tests={test_class}"]
                
        elif build_system == "maven":
            cmd = ["mvn", "test", f"-Dtest={class_name}", "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true"]
        else:
            raise ValueError(f"Unsupported build system: {build_system}")
        
        # Run the group test 5 times to filter flaky tests
        group_test_results = []  # Store results from each iteration
        group_failures = {}  # Track failure categories for group tests
        
        for iteration in range(5):
            try:
                # Run all tests together
                result = subprocess.run(
                    cmd,
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=timeout * 2,  # Give more time for all tests
                    env=env
                )
                
                group_output = result.stdout + "\n" + result.stderr
                group_success = result.returncode == 0
                
                # Remove ANSI color codes to facilitate parsing
                clean_group_output = remove_ansi_colors(group_output)
                
                print(f"   ✓ Iteration {iteration + 1}:")
                
                # Parse the group output to get individual results from this iteration
                group_individual_results = parse_test_output(clean_group_output, build_system)
                
                # For group runs, we need to infer which tests passed based on the summary and known test methods
                iteration_results = {}
                
                if build_system == "maven":
                    # Maven-specific parsing logic
                    # Look for Maven test summary pattern: "Tests run: X, Failures: Y, Errors: Z"
                    maven_summary_pattern = re.search(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+)', clean_group_output)
                    
                    # Initialize failing_tests at the beginning of Maven parsing
                    failing_tests = {}  # method_name -> failure_type
                    
                    if maven_summary_pattern:
                        total_tests = int(maven_summary_pattern.group(1))
                        failed_tests_count = int(maven_summary_pattern.group(2))
                        error_tests_count = int(maven_summary_pattern.group(3))
                        passed_tests_count = total_tests - failed_tests_count - error_tests_count
                        
                        # Parse the Maven output to find failing tests
                        lines = clean_group_output.split('\n')
                        in_failures_section = False
                        in_errors_section = False
                        
                        for line in lines:
                            line = line.strip()
                            
                            # Check for section headers
                            if '[ERROR] Failures:' in line:
                                in_failures_section = True
                                in_errors_section = False
                                continue
                            elif '[ERROR] Errors:' in line:
                                in_failures_section = False
                                in_errors_section = True
                                continue
                            elif line.startswith('[ERROR]') and ('Failures:' in line or 'Errors:' in line):
                                # Skip the header line itself
                                continue
                            elif line.startswith('[ERROR]') and not line.startswith('[ERROR]   '):
                                # End of section
                                in_failures_section = False
                                in_errors_section = False
                                continue
                            
                            # Parse failure lines
                            if in_failures_section and line.startswith('[ERROR]   '):
                                # Format: "[ERROR]   OrderByOperatorTest.testOrderByWithNonTextNodeFields:175 expected:<[Alic]e> but was:<[Charli]e>"
                                # Or: "[ERROR]   OrderByOperatorTest.testOrderByWithNullInputAndSortFields Expected exception: java.lang.NullPointerException"
                                # Extract the test method name
                                # Remove the "[ERROR]   " prefix
                                test_line = line.replace('[ERROR]   ', '').strip()
                                # Extract method name from "ClassName.methodName:lineNumber" or "ClassName.methodName Expected exception:"
                                # Updated regex to handle both formats
                                match = re.search(r'(\w+)\.(\w+)(?::\d+|\s+Expected exception:)', test_line)
                                if match:
                                    test_name = match.group(2)  # Get the method name
                                    failing_tests[test_name] = "assertion_error"
                            
                            # Parse error lines
                            elif in_errors_section and line.startswith('[ERROR]   '):
                                # Format: "[ERROR]   OrderByOperatorTest.testMethodName:123 » ExceptionName"
                                # Or: "[ERROR]   OrderByOperatorTest.testMethodName » Unexpected exception, expected<...> but was<...>"
                                test_line = line.replace('[ERROR]   ', '').strip()
                                # Updated regex to handle both colon and arrow formats
                                match = re.search(r'(\w+)\.(\w+)(?::\d+|\s*»)', test_line)
                                if match:
                                    test_name = match.group(2)  # Get the method name
                                    failing_tests[test_name] = "runtime_error"
                        
                        # For each known test method, determine if it passed or failed in this iteration
                        for method_name in test_methods_for_group:
                            if method_name in failing_tests:
                                # This test was explicitly reported as failed or errored
                                failure_type = failing_tests[method_name]
                                iteration_results[method_name] = False
                                # Update the failure tracking for this iteration
                                group_failures[method_name] = failure_type
                            else:
                                # This test was not reported as failed, so it must have passed
                                iteration_results[method_name] = True
                                # If this test passed in this iteration, only mark it as passed if we haven't seen it fail before
                                if method_name not in group_failures:
                                    group_failures[method_name] = None  # None means passed
                        
                        # Print clean summary for this iteration
                        error_counts = count_error_types(group_failures, test_methods_for_group)
                        error_breakdown = []
                        if error_counts["assertion_error"] > 0:
                            error_breakdown.append(f"{error_counts['assertion_error']} assertion")
                        if error_counts["runtime_error"] > 0:
                            error_breakdown.append(f"{error_counts['runtime_error']} runtime")
                        if error_counts["timeout"] > 0:
                            error_breakdown.append(f"{error_counts['timeout']} timeout")
                        
                        error_info = f" ({', '.join(error_breakdown)})" if error_breakdown else ""
                        print(f"   📊 {total_tests} total, {passed_tests_count} passed, {failed_tests_count + error_tests_count} failed{error_info}")
                        print()
                        
                        # Store the actual Maven counts for later use
                        iteration_results['_maven_total'] = total_tests
                        iteration_results['_maven_failures'] = failed_tests_count
                        iteration_results['_maven_errors'] = error_tests_count
                    
                    # Additional fallback: if we still have no failing tests but Maven reported errors/failures,
                    # try parsing the "Results :" section which has a different format
                    if not failing_tests and maven_summary_pattern and (failed_tests_count > 0 or error_tests_count > 0):
                        # Look for "Results :" section
                        results_section = False
                        for line in clean_group_output.split('\n'):
                            if 'Results :' in line:
                                results_section = True
                                continue
                            elif results_section and line.strip() == '':
                                # End of results section (empty line)
                                break
                            elif results_section and line.strip():
                                # Parse lines like:
                                # "Tests in error:"
                                # "  testMethodName(className): error message"
                                # "Failed tests:"
                                # "  testMethodName(className): failure message"
                                
                                if 'Tests in error:' in line:
                                    current_section = 'error'
                                    continue
                                elif 'Failed tests:' in line:
                                    current_section = 'failure'
                                    continue
                                elif line.startswith('  ') and '(' in line and '):' in line:
                                    # Extract test method name from indented line
                                    # Format: "  testMethodName(className): message"
                                    match = re.search(r'(\w+)\([^)]+\):', line.strip())
                                    if match:
                                        test_name = match.group(1)
                                        if current_section == 'error':
                                            failing_tests[test_name] = "runtime_error"
                                        elif current_section == 'failure':
                                            failing_tests[test_name] = "assertion_error"
                    
                    # Additional fallback: if we still have no failing tests but Maven reported errors/failures,
                    # try parsing the direct "Failed tests:" and "Tests in error:" sections
                    if not failing_tests and maven_summary_pattern and (failed_tests_count > 0 or error_tests_count > 0):
                        lines = clean_group_output.split('\n')
                        current_section = None
                        
                        for line in lines:
                            line = line.strip()
                            
                            # Check for section headers
                            if 'Failed tests:' in line:
                                current_section = 'failure'
                                # Check if there's a test on the same line as the header
                                if '(' in line and '):' in line:
                                    # Extract test from the same line as header
                                    # Find the part after "Failed tests:"
                                    test_part = line.split('Failed tests:')[1].strip()
                                    # More robust regex to capture test method names
                                    match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\([^)]+\):', test_part)
                                    if match:
                                        test_name = match.group(1)
                                        failing_tests[test_name] = "assertion_error"
                                continue
                            elif 'Tests in error:' in line:
                                current_section = 'error'
                                continue
                            elif line.startswith('Tests run:') or line.startswith('[INFO]') or line.startswith('[ERROR]'):
                                # End of test results section
                                current_section = None
                                continue
                            
                            # Parse test lines in current section
                            if current_section and line and '(' in line and '):' in line:
                                # Extract test method name from line
                                # Format: "testMethodName(className): message" or "  testMethodName(className): message"
                                # More robust regex to capture test method names
                                match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\([^)]+\):', line)
                                if match:
                                    test_name = match.group(1)
                                    if current_section == 'failure':
                                        failing_tests[test_name] = "assertion_error"
                                    elif current_section == 'error':
                                        failing_tests[test_name] = "runtime_error"
                    
                    # Use the failing_tests information to set iteration_results for each test method
                    if failing_tests:
                        # For each known test method, determine if it passed or failed in this iteration
                        for method_name in test_methods_for_group:
                            if method_name in failing_tests:
                                # This test was explicitly reported as failed or errored
                                failure_type = failing_tests[method_name]
                                iteration_results[method_name] = False
                                # Update the failure tracking for this iteration
                                group_failures[method_name] = failure_type
                            else:
                                # This test was not reported as failed, so it must have passed
                                iteration_results[method_name] = True
                                # If this test passed in this iteration, only mark it as passed if we haven't seen it fail before
                                if method_name not in group_failures:
                                    group_failures[method_name] = None  # None means passed
                    
                    # Fallback: if no Maven summary found, use the parsed results as-is
                    if not maven_summary_pattern:
                        iteration_results = group_individual_results
                        
                        # Handle the case where parse_test_output returns {'all_tests': True/False}
                        if 'all_tests' in group_individual_results:
                            all_tests_passed = group_individual_results['all_tests']
                            # Map the overall result to all individual test methods
                            for method_name in test_methods_for_group:
                                iteration_results[method_name] = all_tests_passed
                                if all_tests_passed:
                                    if method_name not in group_failures:
                                        group_failures[method_name] = None  # None means passed
                                else:
                                    group_failures[method_name] = "assertion_error"
                            
                            if all_tests_passed:
                                # Print simple summary for fallback case
                                total_tests = len(test_methods_for_group)
                                passed_tests_count = total_tests
                                failed_tests_count = 0
                                print(f"   📊 {total_tests} total, {passed_tests_count} passed, {failed_tests_count} failed")
                                print()

                        else:
                            # For fallback, we can't determine failure types, so mark all failures as assertion_error
                            for method_name, result in iteration_results.items():
                                if not result:  # False means failed
                                    group_failures[method_name] = "assertion_error"
                                elif method_name not in group_failures:
                                    group_failures[method_name] = None  # None means passed
                
                
                elif build_system == "gradle":
                    # Gradle-specific parsing logic for group tests
                    # Look for Gradle test summary pattern: "X tests completed, Y failed"
                    gradle_summary_pattern = re.search(r'(\d+) tests? completed, (\d+) failed', clean_group_output)
                    if gradle_summary_pattern:
                        total_tests = int(gradle_summary_pattern.group(1))
                        failed_tests_count = int(gradle_summary_pattern.group(2))
                        passed_tests_count = total_tests - failed_tests_count
                        
                        # Track failure types for individual tests
                        failing_tests = {}  # method_name -> failure_type
                        
                        # Parse the Gradle output to find failing tests
                        lines = clean_group_output.split('\n')
                        
                        for i, line in enumerate(lines):
                            line = line.strip()
                            
                            # Look for Gradle test failure pattern: "ClassName > methodName FAILED"
                            if ' > ' in line and ' FAILED' in line:
                                # Extract the test method name from the failure line
                                # Format: "com.fishercoder.solutions._235Test > recursiveCallToLeftSubtree FAILED"
                                match = re.search(r'(\w+) > (\w+) FAILED', line)
                                if match:
                                    test_name = match.group(2)  # Get the method name
                                    
                                    # Determine failure type by looking at the next line using format-based parsing
                                    failure_type = "assertion_error"  # Default
                                    if i + 1 < len(lines):
                                        next_line = lines[i + 1].strip()
                                        original_next_line = lines[i + 1]  # Keep original for indentation check
                                        
                                        # Runtime error format: indented line starting with exception class name
                                        # Pattern: "    org.package.ExceptionName at File.java:line"
                                        if original_next_line.startswith('    ') and len(next_line.split()) > 0:
                                            first_word = next_line.split()[0]
                                            
                                            # Check if the first word looks like an exception class name
                                            # Exception class names typically contain dots and end with Exception/Error
                                            if '.' in first_word and (first_word.endswith('Exception') or first_word.endswith('Error')):
                                                # Special case: AssertionError is an assertion error, not a runtime error
                                                if first_word.endswith('AssertionError'):
                                                    # Always check the next two lines for a runtime exception caused by AssertionError
                                                    for offset in [1, 2]:
                                                        if i + offset < len(lines):
                                                            possible_caused_by = lines[i + offset].strip()
                                                            if possible_caused_by.startswith('Caused by:') and any(runtime_exc in possible_caused_by for runtime_exc in ['NullPointerException', 'IllegalArgumentException', 'RuntimeException', 'ParseException', 'MissingMethodInvocationException']):
                                                                failure_type = "runtime_error"
                                                                break
                                                    # If no runtime exception found, keep as assertion_error
                                                else:
                                                    failure_type = "runtime_error"
                                    
                                    failing_tests[test_name] = failure_type
                        
                        # For each known test method, determine if it passed or failed in this iteration
                        for method_name in test_methods_for_group:
                            if method_name in failing_tests:
                                # This test was explicitly reported as failed
                                failure_type = failing_tests[method_name]
                                iteration_results[method_name] = False
                                # Update the failure tracking for this iteration
                                group_failures[method_name] = failure_type
                            else:
                                # This test was not reported as failed, so it must have passed
                                iteration_results[method_name] = True
                                if method_name not in group_failures:
                                    group_failures[method_name] = None  # None means passed
                        
                        # Store the actual Gradle counts for later use
                        iteration_results['_gradle_total'] = total_tests
                        iteration_results['_gradle_failures'] = failed_tests_count
                        iteration_results['_gradle_passed'] = passed_tests_count
                        
                        # Print clean summary for this iteration
                        error_counts = count_error_types(group_failures, test_methods_for_group)
                        error_breakdown = []
                        if error_counts["assertion_error"] > 0:
                            error_breakdown.append(f"{error_counts['assertion_error']} assertion")
                        if error_counts["runtime_error"] > 0:
                            error_breakdown.append(f"{error_counts['runtime_error']} runtime")
                        if error_counts["timeout"] > 0:
                            error_breakdown.append(f"{error_counts['timeout']} timeout")
                        
                        error_info = f" ({', '.join(error_breakdown)})" if error_breakdown else ""
                        print(f"   📊 {total_tests} total, {passed_tests_count} passed, {failed_tests_count} failed{error_info}")
                        print()
                    else:
                        # Gradle pattern not found - assume all tests passed
                        total_tests = len(test_methods_for_group)
                        passed_tests_count = total_tests
                        failed_tests_count = 0
                        print(f"   📊 {total_tests} total, {passed_tests_count} passed, {failed_tests_count} failed")
                        print()
                
                group_test_results.append(iteration_results)
                
            except subprocess.TimeoutExpired:
                print(f"Iteration {iteration + 1}: ⏰ TIMEOUT")
                # Mark all tests as failed for this iteration
                iteration_results = {method_name: False for method_name in test_methods_for_group}
                for method_name in test_methods_for_group:
                    group_failures[method_name] = "timeout"
                group_test_results.append(iteration_results)
            except Exception as e:
                print(f"Iteration {iteration + 1}: 💥 ERROR - {e}")
                # Mark all tests as failed for this iteration
                iteration_results = {method_name: False for method_name in test_methods_for_group}
                for method_name in test_methods_for_group:
                    group_failures[method_name] = "runtime_error"
                group_test_results.append(iteration_results)
        
        # Create detailed group summary with build system totals
        group_summary = create_detailed_summary(group_failures, test_methods_for_group, "Group", json_logger)
        print(group_summary)
        
        return individual_results, individual_failures, group_failures
    
    except subprocess.TimeoutExpired:
        return {}, {}, {}
    except Exception as e:
        return {}, {}, {}

def run_all_tests(
    repo_path: Path, 
    build_system: BuildSystem,
    timeout: int = 120
) -> Tuple[bool, str]:
    """
    Run all tests in the project.
    
    Args:
        repo_path: Path to the repository root
        build_system: "gradle" or "maven"
        timeout: Timeout in seconds for test execution
        
    Returns:
        Tuple of (success: bool, output: str)
    """
    try:
        if build_system == "gradle":
            gradle_wrapper = repo_path / "gradlew"
            if gradle_wrapper.exists():
                gradle_wrapper.chmod(0o755)
                cmd = [str(gradle_wrapper), "test"]
            else:
                cmd = ["gradle", "test"]
                
        elif build_system == "maven":
            cmd = ["mvn", "test", "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true"]
        else:
            raise ValueError(f"Unsupported build system: {build_system}")
        
        # Set environment variables
        env = os.environ.copy()
        # Get Java version and path from global config (like compile_java_file.py does)
        java_version = test_config.get_java_version()
        java_path = test_config.get_java_path()
        
        if java_path:
            env['JAVA_HOME'] = java_path
            env['PATH'] = f"{java_path}/bin:{env['PATH']}"
            if build_system == "gradle":
                env['GRADLE_OPTS'] = f"-Dorg.gradle.java.home={java_path}"
        
        # Run all tests
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
        
        output = result.stdout + "\n" + result.stderr
        success = result.returncode == 0
        
        return success, output
        
    except subprocess.TimeoutExpired:
        return False, f"Test execution timed out after {timeout} seconds"
    except Exception as e:
        return False, f"Test execution failed: {str(e)}"

def execute_and_filter_tests(
    test_file_path: Path,
    package: str,
    class_name: str,
    repo_path: Path,
    build_system: BuildSystem,
    test_methods: List[str] = None
) -> List[Tuple[str, str]]:
    """
    Execute tests and return only the passing ones.
    
    Args:
        test_file_path: Path to the test file
        package: Package name
        class_name: Class name
        repo_path: Repository path
        build_system: Build system type
        test_methods: List of test method names (if None, will be extracted from file)
        
    Returns:
        List of tuples (scenario_description, test_method_content) for passing tests
    """
    # Read the test file content
    test_content = test_file_path.read_text()
    
    # Use provided test methods or extract them if not provided
    if test_methods is None:
        test_methods = extract_test_method_names(test_content)
    
    if not test_methods:
        return []
    
    # Run the entire test class to get results
    fully_qualified_class = f"{package}.{class_name}"
    # Note: This function is not used in the new flow and would need final_tests parameter
    # For now, we'll skip the execution and just return empty results
    success = False
    output = "Function not implemented for new flow"
    individual_results = {}
    group_results_inferred = {}
    individual_failures = {}
    group_failures = {}
    
    # Return empty list since this function is not used in the new flow
    return []

def create_isolated_test_with_scaffold(test_content: str, method_name: str, class_name: str, package: str, scaffold: str = None) -> str:
    """
    Create an isolated test file containing the scaffold and the specified test method.
    
    Args:
        test_content: The full test class content OR the individual test method content
        method_name: The name of the test method to isolate
        class_name: The test class name
        package: The package name
        scaffold: The test scaffold to use (optional)
        
    Returns:
        The content of the isolated test file
    """
    import re
    
    # Check if test_content is a full test class or just a single test method
    if '@Test' in test_content and 'public void' in test_content and 'class' not in test_content:
        # This is a single test method content
        method_lines = test_content.split('\n')
    else:
        # This is a full test class content - extract the specific method
        # Extract the specific test method from the full test content
        # Look for the method signature first
        method_pattern = re.compile(rf'public\s+void\s+{re.escape(method_name)}\s*\(')
        
        method_lines = []
        in_method = False
        brace_count = 0
        lines = test_content.split('\n')
        
        for i, line in enumerate(lines):
            if method_pattern.search(line):
                # Found the start of our method
                in_method = True
                
                # Check if there's a @Test annotation on the previous line
                if i > 0 and '@Test' in lines[i-1]:
                    method_lines.append(lines[i-1])  # Add the @Test line
                
                method_lines.append(line)  # Add the method signature line
                brace_count = line.count('{') - line.count('}')
            elif in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count == 0:
                    # Method is complete
                    break
        
        if not method_lines:
            # Fallback: try to find the method using a simpler approach
            method_start = test_content.find(f'public void {method_name}(')
            if method_start != -1:
                # Find the opening brace
                brace_start = test_content.find('{', method_start)
                if brace_start != -1:
                    # Count braces to find the end
                    brace_count = 1
                    pos = brace_start + 1
                    while pos < len(test_content) and brace_count > 0:
                        if test_content[pos] == '{':
                            brace_count += 1
                        elif test_content[pos] == '}':
                            brace_count -= 1
                        pos += 1
                    
                    method_content = test_content[method_start:pos]
                    method_lines = method_content.split('\n')
                    
                    # Add @Test if it's missing
                    if not any('@Test' in line for line in method_lines):
                        for i, line in enumerate(method_lines):
                            if line.strip().startswith('public void'):
                                method_lines[i] = '    @Test' + line
                                break
    
    if scaffold:
        # Use the provided scaffold
        assembled_test_file = scaffold
        
        # Insert the single test method before the closing brace
        last_brace_index = assembled_test_file.rfind("}")
        if last_brace_index != -1:
            # Build the test methods block
            test_methods_block = []
            # Add the test method with proper indentation
            for line in method_lines:
                if line.strip():
                    test_methods_block.append("    " + line)
                else:
                    test_methods_block.append("")
            
            # Insert the test method before the closing brace
            assembled_test_file = (
                assembled_test_file[:last_brace_index] +
                "\n" +
                "\n".join(test_methods_block).rstrip() + "\n" +
                assembled_test_file[last_brace_index:]
            )
        
        return assembled_test_file
    else:
        # Fallback to basic scaffold
        scaffold_lines = [
            f"package {package};",
            "",
            "import org.junit.Test;",
            "import static org.junit.Assert.*;",
            "",
            f"public class {class_name} {{",
            "    // Test setup and helper methods would go here",
            ""
        ]
        
        # Add the method lines with proper indentation
        for line in method_lines:
            if line.strip():
                scaffold_lines.append("    " + line)
            else:
                scaffold_lines.append("")
        
        # Close the class
        scaffold_lines.append("}")
        
        return "\n".join(scaffold_lines)

def categorize_test_failure(test_output: str, build_system: str) -> str:
    """
    Categorize test failure based on build system output.
    
    Args:
        test_output: The test execution output
        build_system: Build system type ("gradle" or "maven")
        
    Returns:
        Failure category: "assertion_error" (FAILURES) or "runtime_error" (ERRORS)
    """
    output_lower = test_output.lower()
    
    if build_system == "maven":
        # Maven reports "FAILURES" for assertion failures and "ERRORS" for runtime exceptions
        lines = test_output.split('\n')
        for line in lines:
            # Look for Maven summary line: "Tests run: X, Failures: Y, Errors: Z"
            if "failures:" in line.lower() and "errors:" in line.lower():
                import re
                # Extract both failures and errors from the same line
                failures_match = re.search(r'failures:\s*(\d+)', line.lower())
                errors_match = re.search(r'errors:\s*(\d+)', line.lower())
                
                if failures_match and errors_match:
                    failures_count = int(failures_match.group(1))
                    errors_count = int(errors_match.group(1))
                    
                    # Prioritize errors over failures (if both exist, it's likely an error)
                    if errors_count > 0:
                        return "runtime_error"
                    elif failures_count > 0:
                        return "assertion_error"
            
            # Fallback: check individual patterns if not found together
            elif "failures:" in line.lower() and any(char.isdigit() for char in line):
                import re
                match = re.search(r'failures:\s*(\d+)', line.lower())
                if match and int(match.group(1)) > 0:
                    return "assertion_error"
            elif "errors:" in line.lower() and any(char.isdigit() for char in line):
                import re
                match = re.search(r'errors:\s*(\d+)', line.lower())
                if match and int(match.group(1)) > 0:
                    return "runtime_error"
    
    elif build_system == "gradle":
        # For Gradle, we need to parse the output format to determine failure type
        # Gradle output format for test failures:
        # com.fishercoder.solutions._235Test > recursiveCallToLeftSubtree FAILED
        #     org.mockito.exceptions.misusing.MissingMethodInvocationException at _235Test.java:19
        # OR
        # com.fishercoder.solutions._235Test > testLowestCommonAncestorWhenBothPSmallerThanRoot FAILED
        #     java.lang.AssertionError at _235Test.java:21
        
        lines = test_output.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Look for Gradle test failure pattern: "ClassName > methodName FAILED"
            if ' > ' in line and ' FAILED' in line:
                # This is a test failure line, check the next line for exception details
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    original_next_line = lines[i + 1]  # Keep original for indentation check
                    
                    # Runtime error format: indented line starting with exception class name
                    # Pattern: "    org.package.ExceptionName at File.java:line"
                    if original_next_line.startswith('    ') and len(next_line.split()) > 0:
                        first_word = next_line.split()[0]
                        
                        # Check if the first word looks like an exception class name
                        # Exception class names typically contain dots and end with Exception/Error
                        if '.' in first_word and (first_word.endswith('Exception') or first_word.endswith('Error')):
                            # Special case: AssertionError is an assertion error, not a runtime error
                            if first_word.endswith('AssertionError'):
                                # Always check the next two lines for a runtime exception caused by AssertionError
                                for offset in [1, 2]:
                                    if i + offset < len(lines):
                                        possible_caused_by = lines[i + offset].strip()
                                        if possible_caused_by.startswith('Caused by:') and any(runtime_exc in possible_caused_by for runtime_exc in ['NullPointerException', 'IllegalArgumentException', 'RuntimeException', 'ParseException', 'MissingMethodInvocationException']):
                                            failure_type = "runtime_error"
                                            break
                                # If no runtime exception found, keep as assertion_error
                            else:
                                failure_type = "runtime_error"
                    
                    # If we don't find the runtime error format, it's an assertion error
                    return "assertion_error"
                else:
                    return "assertion_error"
        
        # Fallback: if we can't determine from format, default to assertion error
        return "assertion_error"
    
    # Fallback: check for specific patterns if build system specific parsing didn't work
    if "assertionerror" in output_lower or "expected:" in output_lower or "but was:" in output_lower:
        return "assertion_error"
    elif any(exc in output_lower for exc in ["nullpointerexception", "illegalargumentexception", "runtimeexception", "parseexception", "missingmethodinvocationexception"]):
        return "runtime_error"
    
    # Default to assertion error if we can't determine
    return "assertion_error"

def create_detailed_summary(failure_details: Dict[str, str], test_methods: List[str], summary_type: str, json_logger=None) -> str:
    """
    Create a detailed summary of test execution results.
    
    Args:
        failure_details: Dictionary mapping test method names to failure categories
        test_methods: List of all test method names
        summary_type: Type of summary ("Individual" or "Group")
        json_logger: Optional JSON logger to update with execution results
        
    Returns:
        Formatted summary string
    """
    total_tests = len(test_methods)
    # Infer pass/fail status from failure_details
    passed_tests = sum(1 for method in test_methods if failure_details.get(method) is None)
    failed_tests = total_tests - passed_tests
    
    # Count failure types
    failure_counts = {
        "assertion_error": 0,
        "runtime_error": 0,
        "timeout": 0
    }
    
    for method in test_methods:
        failure_type = failure_details.get(method)
        if failure_type is not None:  # If test failed (has a failure type)
            if failure_type in failure_counts:
                failure_counts[failure_type] += 1
    
    # Log to JSON if logger is provided
    if json_logger:
        # Convert failure_details to the format expected by JSON logger
        # Map failure types to readable names
        failures_dict = {}
        for method in test_methods:
            failure_type = failure_details.get(method)
            if failure_type is not None:  # If test failed
                if failure_type == "assertion_error":
                    failures_dict[method] = "Assertion Error"
                elif failure_type == "runtime_error":
                    failures_dict[method] = "Runtime Error"
                elif failure_type == "timeout":
                    failures_dict[method] = "Timeout"
        
        if summary_type == "Individual":
            json_logger.update_test_execution_individual(
                total_tests=total_tests,
                passed=passed_tests,
                assertion_errors=failure_counts["assertion_error"],
                runtime_errors=failure_counts["runtime_error"],
                timeout_errors=failure_counts["timeout"],
                failures=failures_dict
            )
        elif summary_type == "Group":
            json_logger.update_test_execution_group(
                total_tests=total_tests,
                passed=passed_tests,
                assertion_errors=failure_counts["assertion_error"],
                runtime_errors=failure_counts["runtime_error"],
                timeout_errors=failure_counts["timeout"],
                failures=failures_dict
            )
    
    # Build summary
    summary_lines = []
    summary_lines.append(f"\n📊 {summary_type} Test Execution Summary:")
    summary_lines.append("─" * 50)
    
    summary_lines.append(f"   Total tests: {total_tests}")
    summary_lines.append(f"   ✅ Passed: {passed_tests}")
    
    # Add failure breakdown to the failed count line
    if failed_tests > 0:
        failure_breakdown_parts = []
        for failure_type, count in failure_counts.items():
            if count > 0:
                readable_type = failure_type.replace("_", " ").title()
                failure_breakdown_parts.append(f"{count} {readable_type}")
        
        failure_info = f" ({', '.join(failure_breakdown_parts)})"
        summary_lines.append(f"   ❌ Failed: {failed_tests}{failure_info}")
    else:
        summary_lines.append(f"   ❌ Failed: {failed_tests}")
    
    # Add detailed failure information with renamed section
    if failed_tests > 0:
        summary_lines.append(f"\n   📋 Failure Breakdown:")
        for method in test_methods:
            failure_type = failure_details.get(method)
            if failure_type is not None:  # If test failed
                readable_type = failure_type.replace("_", " ").title()
                summary_lines.append(f"      • {method}: {readable_type}")
    
    return "\n".join(summary_lines)

def create_filtered_test_content(test_content: str, timeout_tests: List[str], class_name: str) -> str:
    """
    Create a filtered version of test content that excludes timeout test methods.
    
    Args:
        test_content: The original test class content
        timeout_tests: List of test method names to exclude
        class_name: The test class name
        
    Returns:
        Filtered test content with timeout tests removed
    """
    if not timeout_tests:
        return test_content
    
    print(f"   Filtering out {len(timeout_tests)} timeout tests: {timeout_tests}")
    
    lines = test_content.split('\n')
    filtered_lines = []
    skip_method = False
    brace_count = 0
    in_method = False
    
    for i, line in enumerate(lines):
        # Check if this line starts a timeout test method
        for timeout_test in timeout_tests:
            # Look for @Test annotation followed by the method
            if '@Test' in line and f'public void {timeout_test}(' in lines[i + 1] if i + 1 < len(lines) else False:
                skip_method = True
                print(f"     Skipping timeout test: {timeout_test}")
                break
            # Also check if method starts on the same line as @Test
            elif '@Test' in line and f'public void {timeout_test}(' in line:
                skip_method = True
                print(f"     Skipping timeout test: {timeout_test}")
                break
        
        if skip_method:
            # Skip this line and start counting braces
            if '{' in line:
                brace_count = line.count('{') - line.count('}')
                if brace_count == 0:
                    # Method ends on the same line
                    skip_method = False
            continue
        
        # If we're in a method we're skipping, count braces
        if skip_method:
            brace_count += line.count('{') - line.count('}')
            if brace_count == 0:
                # Method is complete, stop skipping
                skip_method = False
            continue
        
        # Add the line if we're not skipping
        filtered_lines.append(line)
    
    return '\n'.join(filtered_lines) 

def count_error_types(failure_details: Dict[str, str], test_methods: List[str]) -> Dict[str, int]:
    """
    Count the number of each error type from failure details.
    
    Args:
        failure_details: Dictionary mapping test method names to failure categories
        test_methods: List of all test method names
        
    Returns:
        Dictionary with counts for each error type
    """
    error_counts = {
        "assertion_error": 0,
        "runtime_error": 0,
        "timeout": 0
    }
    
    for method in test_methods:
        failure_type = failure_details.get(method)
        if failure_type in error_counts:
            error_counts[failure_type] += 1
    
    return error_counts 

def create_test_content_from_tuples(final_tests: List[Tuple], class_name: str, scaffold: str = None) -> str:
    """
    Create test content from final_tests tuples for group execution.
    
    Args:
        final_tests: List of (scenario, test_method) tuples
        class_name: Name of the test class
        scaffold: The test scaffold to use (optional)
        
    Returns:
        Assembled test content string
    """
    if scaffold:
        # Use the provided scaffold
        assembled_test_file = scaffold
        
        # Insert all test methods before the closing brace
        last_brace_index = assembled_test_file.rfind("}")
        if last_brace_index != -1:
            # Build the test methods block
            test_methods_block = []
            for idx, (scenario, test_method) in enumerate(final_tests, 1):
                test_methods_block.append(f"    // Test {idx}: {scenario.title}")
                test_methods_block.append(f"    // {scenario.description}")
                # Add the test method with proper indentation
                for line in test_method.splitlines():
                    if line.strip():
                        test_methods_block.append("    " + line)
                    else:
                        test_methods_block.append("")
                test_methods_block.append("")  # Add blank line between methods
            
            # Insert the test methods before the closing brace
            assembled_test_file = (
                assembled_test_file[:last_brace_index] +
                "\n" +
                "\n".join(test_methods_block).rstrip() + "\n" +
                assembled_test_file[last_brace_index:]
            )
        
        return assembled_test_file
    else:
        # Fallback to basic structure
        test_content = f"public class {class_name} {{\n"
        for scenario, test_method in final_tests:
            test_content += f"    // {scenario.title}\n"
            test_content += f"    {test_method}\n\n"
        test_content += "}"
        return test_content

def create_filtered_test_content_from_tuples(passing_tests: List[Tuple], timeout_tests: List[str], class_name: str, scaffold: str = None) -> str:
    """
    Create filtered test content from passing tests tuples.
    
    Args:
        passing_tests: List of (scenario, test_method) tuples for passing tests
        timeout_tests: List of timeout test method names
        class_name: Name of the test class
        scaffold: The test scaffold to use (optional)
        
    Returns:
        Filtered test content string
    """
    if scaffold:
        # Use the provided scaffold
        assembled_test_file = scaffold
        
        # Insert all passing test methods before the closing brace
        last_brace_index = assembled_test_file.rfind("}")
        if last_brace_index != -1:
            # Build the test methods block
            test_methods_block = []
            for idx, (scenario, test_method) in enumerate(passing_tests, 1):
                test_methods_block.append(f"    // Test {idx}: {scenario.title}")
                test_methods_block.append(f"    // {scenario.description}")
                # Add the test method with proper indentation
                for line in test_method.splitlines():
                    if line.strip():
                        test_methods_block.append("    " + line)
                    else:
                        test_methods_block.append("")
                test_methods_block.append("")  # Add blank line between methods
            
            # Insert the test methods before the closing brace
            assembled_test_file = (
                assembled_test_file[:last_brace_index] +
                "\n" +
                "\n".join(test_methods_block).rstrip() + "\n" +
                assembled_test_file[last_brace_index:]
            )
        
        return assembled_test_file
    else:
        # Fallback to basic structure
        test_content = f"public class {class_name} {{\n"
        for scenario, test_method in passing_tests:
            test_content += f"    // {scenario.title}\n"
            test_content += f"    {test_method}\n\n"
        test_content += "}"
        return test_content 