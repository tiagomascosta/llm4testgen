import shutil
import re
from pathlib import Path
from typing import Dict, Tuple
from git import Repo
import os
import subprocess

from .test_executor import run_individual_test, categorize_test_failure
from .build_system_detector import BuildSystem
from config import test_config
from init.repository import RepositoryManager
from utils.colors import Colors, step, success, error, warning, info, summary



def backup_build_files(repo_path: Path) -> Dict[str, str]:
    """
    Backup build files before checkout.
    
    Args:
        repo_path: Path to the repository
        
    Returns:
        Dictionary mapping build type to file content
    """
    backup_files = {}
    
    # Backup Gradle files
    if (repo_path / 'build.gradle').exists():
        backup_files['gradle'] = (repo_path / 'build.gradle').read_text()
    
    # Backup Maven files  
    if (repo_path / 'pom.xml').exists():
        backup_files['maven'] = (repo_path / 'pom.xml').read_text()
    
    return backup_files


def restore_build_files(repo_path: Path, backup_files: Dict[str, str]):
    """
    Restore build files after checkout.
    
    Args:
        repo_path: Path to the repository
        backup_files: Dictionary mapping build type to file content
    """
    for build_type, content in backup_files.items():
        if build_type == 'gradle':
            (repo_path / 'build.gradle').write_text(content)
        elif build_type == 'maven':
            (repo_path / 'pom.xml').write_text(content)


def test_single_bug_assessment(
    test_file: Path, 
    repo_path: Path, 
    build_system: str,
    package: str
) -> str:
    """
    Test if a single assertion-failing test reveals a real bug.
    
    Args:
        test_file: Path to the test file
        repo_path: Path to the repository
        build_system: Build system type ("gradle" or "maven")
        package: Package name for the test
        
    Returns:
        Result string: "bug_revealed", "assertion_error", "runtime_error", "timeout", "invalid_filename"
    """
    print(f"   {info('Testing:')} {test_file.name}")
    
    # Read the test content to extract the actual class name
    test_content = test_file.read_text()
    
    # Extract class name from the file content
    import re
    class_match = re.search(r'public\s+class\s+(\w+)', test_content)
    if not class_match:
        print(f"   {warning('Could not extract class name from test file')}")
        return "invalid_filename"
    class_name = class_match.group(1)
    
    # Extract test method name from the file content
    # Handle multiple @Test annotation formats:
    # 1. @Test (JUnit 5)
    # 2. @Test(expected = Exception.class) (JUnit 4)
    # 3. Multi-line @Test annotations
    method_match = re.search(
        r'@Test\s*\n\s*public\s+void\s+(\w+)\s*\(|'  # Multi-line @Test
        r'@Test\s+public\s+void\s+(\w+)\s*\(|'       # Single-line @Test
        r'@Test\([^)]*\)\s*\n\s*public\s+void\s+(\w+)\s*\(|'  # Multi-line @Test(expected = ...)
        r'@Test\([^)]*\)\s+public\s+void\s+(\w+)\s*\('       # Single-line @Test(expected = ...)
    , test_content, re.MULTILINE)
    if method_match:
        method_name = method_match.group(1) or method_match.group(2) or method_match.group(3) or method_match.group(4)
    else:
        # Fallback: extract method name from filename since it matches the method name
        # Format: {method_name}_{class}Test_{number}Test.java
        filename_without_ext = test_file.stem  # Remove .java extension
        # Remove the class suffix pattern: __{class}Test_{number}Test
        method_name_match = re.search(r'^(.+?)_.+Test_\d+Test$', filename_without_ext)
        if method_name_match:
            method_name = method_name_match.group(1)
        else:
            print(f"   {warning('Could not extract method name from test file')}")
            return "invalid_filename"
    
    # Use the global test file path from config
    target_path = Path(test_config.get_test_file_path())
    
    # Replace the filename part with the actual filename from the potential bug file
    target_path = target_path.parent / test_file.name
    
    # Copy the file content to the target path
    target_path.write_text(test_content)
    
    try:
        # Run the test using existing run_individual_test function
        success, output = run_individual_test(
            test_class=f"{package}.{class_name}",
            test_method=method_name,
            repo_path=repo_path,
            build_system=build_system,
            timeout=30
        )
        
        if success:
            return "bug_revealed"  # Test passes on fix commit!
        else:
            # Categorize the failure
            failure_type = categorize_test_failure(output, build_system)
            return failure_type  # "assertion_error", "runtime_error", "timeout"
            
    finally:
        # Clean up the injected test file
        if target_path.exists():
            target_path.unlink()


def run_final_test_suite_on_fix_commit(
    repo_path: Path,
    output_dir: Path,
    build_system: str,
    package: str
) -> Dict[str, int]:
    """
    Run the final test suite on the fix commit to detect regressions.
    
    Args:
        repo_path: Path to fix commit repository (already cloned)
        output_dir: Output directory containing test_suite folder
        build_system: Build system type ("gradle" or "maven")
        package: Package name
        
    Returns:
        Dict with pass/fail counts
    """
    
    # Find the final test suite file in the test_suite folder
    # Check if output_dir is already the test_suite directory or if we need to append it
    if output_dir.name == "test_suite":
        test_suite_dir = output_dir
    else:
        test_suite_dir = output_dir / "test_suite"
    
    if not test_suite_dir.exists():
        print(f"   {warning('Test suite directory not found at')} {test_suite_dir}")
        return {"passed": 0, "failed": 0}
    
    # Look for the .java file in the test_suite directory
    java_files = list(test_suite_dir.glob("*.java"))
    if not java_files:
        print(f"   {warning('No .java files found in test suite directory')} {test_suite_dir}")
        return {"passed": 0, "failed": 0}
    
    # Use the first .java file found (should be the only one)
    final_test_file = java_files[0]
    
    # Write the test file to the correct location in the freshly cloned repository
    # Extract class name from the test file content
    test_content = final_test_file.read_text()
    import re
    class_match = re.search(r'public\s+class\s+(\w+)', test_content)
    if not class_match:
        print(f"   {warning('Could not extract class name from final test suite')}")
        return {"passed": 0, "failed": 0}
    
    class_name = class_match.group(1)
    
    # Construct the target path in the repository
    # The test file should be in src/test/java/package/ClassName.java
    package_path = package.replace('.', '/')
    target_test_file = repo_path / "src" / "test" / "java" / package_path / final_test_file.name
    
    # Ensure the target directory exists
    target_test_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Delete any existing test file with the same name before writing the new one
    if target_test_file.exists():
        target_test_file.unlink()
    
    # Write the test file content to the target path
    target_test_file.write_text(test_content)
    
    try:
        # Run the test suite using the same approach as run_tests_with_coverage
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
        
        # Build command based on build system (same as run_tests_with_coverage but without coverage)
        if build_system == "gradle":
            # Check for Gradle wrapper
            gradle_wrapper = repo_path / "gradlew"
            if gradle_wrapper.exists():
                gradle_wrapper.chmod(0o755)
                if class_name:
                    # Run only the specific test class
                    cmd = [str(gradle_wrapper), "clean", "test", f"--tests={package}.{class_name}"]
                else:
                    # Run all tests (fallback)
                    cmd = [str(gradle_wrapper), "clean", "test"]
            else:
                if class_name:
                    cmd = ["gradle", "clean", "test", f"--tests={package}.{class_name}"]
                else:
                    cmd = ["gradle", "clean", "test"]
                
        elif build_system == "maven":
            # Check if the project uses Surefire plugin (same logic as run_tests_with_coverage)
            pom_path = repo_path / "pom.xml"
            uses_surefire = False
            if pom_path.exists():
                try:
                    import xml.etree.ElementTree as ET
                    tree = ET.parse(pom_path)
                    root = tree.getroot()
                    # Define namespace
                    ns = {'mvn': 'http://maven.apache.org/POM/4.0.0'}
                    
                    # Look for maven-surefire-plugin in plugins section
                    plugins = root.findall('.//mvn:plugin', ns)
                    for plugin in plugins:
                        artifact_id = plugin.find('mvn:artifactId', ns)
                        if artifact_id is not None and artifact_id.text == 'maven-surefire-plugin':
                            uses_surefire = True
                            break
                except Exception as e:
                    print(f"WARNING: Could not parse POM.xml to check for Surefire: {e}")
            
            if uses_surefire:
                # Project uses Surefire, use standard approach
                if class_name:
                    # Extract class name from fully qualified name for Maven
                    class_name = class_name  # Already extracted
                    # Use a simple approach: run the full Maven lifecycle
                    cmd = ["mvn", "clean", "test", 
                           f"-Dtest={class_name}", 
                           "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true", "-Denforcer.skip=true"]
                else:
                    cmd = ["mvn", "clean", "test", 
                           "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true", "-Denforcer.skip=true"]
            else:
                # Project doesn't use Surefire, use vanilla approach
                
                # For projects without Surefire, just run the vanilla setup
                if class_name:
                    class_name = class_name  # Already extracted
                    cmd = ["mvn", "clean", "test", 
                           f"-Dtest={class_name}", 
                           "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true", "-Denforcer.skip=true"]
                else:
                    cmd = ["mvn", "clean", "test", 
                           "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true", "-Denforcer.skip=true"]
            
        else:
            raise ValueError(f"Unsupported build system: {build_system}")
        
        # Run the command (same as run_tests_with_coverage)
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout (same as run_tests_with_coverage)
            env=env
        )
        
        # Combine stdout and stderr
        output = result.stdout + "\n" + result.stderr
        
        # Simple success/failure logic (same as run_tests_with_coverage)
        success = result.returncode == 0
        
        # Determine regression results
        if success:
            # No regression - test suite passed
            passed = 1
            failed = 0
        else:
            # Regression detected - test suite failed
            passed = 0
            failed = 1
        
        return {"passed": passed, "failed": failed}
        
    except subprocess.TimeoutExpired:
        return {"passed": 0, "failed": 1}  # Timeout = regression
    except Exception as e:
        return {"passed": 0, "failed": 1}  # Exception = regression
    finally:
        # Clean up the test file to leave the repo clean
        if target_test_file.exists():
            target_test_file.unlink()


def run_final_test_suite_on_fix_commit_enhanced(
    repo_path: Path,
    output_dir: Path,
    build_system: str,
    package: str,
    json_logger = None
) -> Dict[str, any]:
    """
    Enhanced regression detection using existing parsing methods.
    
    Args:
        repo_path: Path to fix commit repository (already cloned)
        output_dir: Output directory containing test_suite folder
        build_system: Build system type ("gradle" or "maven")
        package: Package name
        json_logger: Optional JSON logger to update with regression results
        
    Returns:
        Dict with detailed regression results
    """
    
    # Find the final test suite file in the test_suite folder
    # Check if output_dir is already the test_suite directory or if we need to append it
    if output_dir.name == "test_suite":
        test_suite_dir = output_dir
    else:
        test_suite_dir = output_dir / "test_suite"
    
    if not test_suite_dir.exists():
        print(f"   {warning('Test suite directory not found at')} {test_suite_dir}")
        return {"regression_detected": False, "total_tests": 0, "passed": 0, "failed": 0, "failures": []}
    
    # Look for the .java file in the test_suite directory
    java_files = list(test_suite_dir.glob("*.java"))
    if not java_files:
        print(f"   {warning('No .java files found in test suite directory')} {test_suite_dir}")
        return {"regression_detected": False, "total_tests": 0, "passed": 0, "failed": 0, "failures": []}
    
    # Use the first .java file found (should be the only one)
    final_test_file = java_files[0]
    
    # Write the test file to the correct location in the freshly cloned repository
    # Extract class name from the test file content
    test_content = final_test_file.read_text()
    import re
    class_match = re.search(r'public\s+class\s+(\w+)', test_content)
    if not class_match:
        print(f"   {warning('Could not extract class name from final test suite')}")
        return {"regression_detected": False, "total_tests": 0, "passed": 0, "failed": 0, "failures": []}
    
    class_name = class_match.group(1)
    
    # REUSE: Extract test method names from the test file
    from .test_result_parser import extract_test_method_names
    test_methods = extract_test_method_names(test_content)
    
    if not test_methods:
        print(f"   {warning('No test methods found in final test suite')}")
        return {"regression_detected": False, "total_tests": 0, "passed": 0, "failed": 0, "failures": []}
    
    # Construct the target path in the repository
    # The test file should be in src/test/java/package/ClassName.java
    package_path = package.replace('.', '/')
    target_test_file = repo_path / "src" / "test" / "java" / package_path / final_test_file.name
    
    # Ensure the target directory exists
    target_test_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Delete any existing test file with the same name before writing the new one
    if target_test_file.exists():
        target_test_file.unlink()
    
    # Write the test file content to the target path
    target_test_file.write_text(test_content)
    
    try:
        # Run the test suite using the same approach as run_tests_with_coverage
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
        
        # Build command based on build system (same as run_tests_with_coverage but without coverage)
        if build_system == "gradle":
            # Check for Gradle wrapper
            gradle_wrapper = repo_path / "gradlew"
            if gradle_wrapper.exists():
                gradle_wrapper.chmod(0o755)
                if class_name:
                    # Run only the specific test class
                    cmd = [str(gradle_wrapper), "clean", "test", f"--tests={package}.{class_name}"]
                else:
                    # Run all tests (fallback)
                    cmd = [str(gradle_wrapper), "clean", "test"]
            else:
                if class_name:
                    cmd = ["gradle", "clean", "test", f"--tests={package}.{class_name}"]
                else:
                    cmd = ["gradle", "clean", "test"]
                
        elif build_system == "maven":
            # Check if the project uses Surefire plugin (same logic as run_tests_with_coverage)
            pom_path = repo_path / "pom.xml"
            uses_surefire = False
            if pom_path.exists():
                try:
                    import xml.etree.ElementTree as ET
                    tree = ET.parse(pom_path)
                    root = tree.getroot()
                    # Define namespace
                    ns = {'mvn': 'http://maven.apache.org/POM/4.0.0'}
                    
                    # Look for maven-surefire-plugin in plugins section
                    plugins = root.findall('.//mvn:plugin', ns)
                    for plugin in plugins:
                        artifact_id = plugin.find('mvn:artifactId', ns)
                        if artifact_id is not None and artifact_id.text == 'maven-surefire-plugin':
                            uses_surefire = True
                            break
                except Exception as e:
                    print(f"WARNING: Could not parse POM.xml to check for Surefire: {e}")
            
            if uses_surefire:
                # Project uses Surefire, use standard approach
                if class_name:
                    # Extract class name from fully qualified name for Maven
                    class_name = class_name  # Already extracted
                    # Use a simple approach: run the full Maven lifecycle
                    cmd = ["mvn", "clean", "test", 
                           f"-Dtest={class_name}", 
                           "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true", "-Denforcer.skip=true"]
                else:
                    cmd = ["mvn", "clean", "test", 
                           "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true", "-Denforcer.skip=true"]
            else:
                # Project doesn't use Surefire, use vanilla approach
                
                # For projects without Surefire, just run the vanilla setup
                if class_name:
                    class_name = class_name  # Already extracted
                    cmd = ["mvn", "clean", "test", 
                           f"-Dtest={class_name}", 
                           "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true", "-Denforcer.skip=true"]
                else:
                    cmd = ["mvn", "clean", "test", 
                           "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true", "-Denforcer.skip=true"]
            
        else:
            raise ValueError(f"Unsupported build system: {build_system}")
        
        # Run the command (same as run_tests_with_coverage)
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout (same as run_tests_with_coverage)
            env=env
        )
        
        # Combine stdout and stderr
        output = result.stdout + "\n" + result.stderr
        
        # REUSE: Clean output for parsing
        from .test_executor import remove_ansi_colors
        clean_output = remove_ansi_colors(output)
        
        # REUSE: Parse test output using existing function
        from .test_result_parser import parse_test_output
        parsed_results = parse_test_output(clean_output, build_system)
        
        # Calculate results using existing parsing logic
        total_tests = len(test_methods)
        failing_tests = []
        
        # Process parsed results
        for method_name in test_methods:
            if method_name in parsed_results:
                if not parsed_results[method_name]:  # Test failed
                    failing_tests.append(method_name)
        
        passed_tests = total_tests - len(failing_tests)
        failed_tests = len(failing_tests)
        regression_detected = failed_tests > 0
        
        # Update JSON logger if provided
        if json_logger:
            json_logger.update_regression_detection(
                regression_detected=regression_detected,
                total_tests=total_tests,
                passed=passed_tests,
                failed=failed_tests,
                failures=failing_tests
            )
        
        return {
            "regression_detected": regression_detected,
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "failures": failing_tests
        }
        
    except subprocess.TimeoutExpired:
        # Timeout = regression
        if json_logger:
            json_logger.update_regression_detection(
                regression_detected=True,
                total_tests=len(test_methods),
                passed=0,
                failed=len(test_methods),
                failures=test_methods
            )
        return {"regression_detected": True, "total_tests": len(test_methods), "passed": 0, "failed": len(test_methods), "failures": test_methods}
    except Exception as e:
        # Exception = regression
        if json_logger:
            json_logger.update_regression_detection(
                regression_detected=True,
                total_tests=len(test_methods),
                passed=0,
                failed=len(test_methods),
                failures=test_methods
            )
        return {"regression_detected": True, "total_tests": len(test_methods), "passed": 0, "failed": len(test_methods), "failures": test_methods}
    finally:
        # Clean up the test file to leave the repo clean
        if target_test_file.exists():
            target_test_file.unlink()


def test_potential_bugs_in_existing_repo(
    repo_path: Path,
    potential_bugs_dir: Path,
    build_system: str,
    package: str
) -> Dict[str, str]:
    """
    Test potential bug-revealing tests in an existing repository (no cloning needed).
    
    Args:
        repo_path: Path to the repository (already cloned and set up)
        potential_bugs_dir: Directory containing potential bug-revealing tests
        build_system: Build system type ("gradle" or "maven")
        package: Package name for the tests
        
    Returns:
        Dict mapping test filename to result: "bug_revealed", "still_failing", "timeout", "runtime_error"
    """
    results = {}
    
    # Copy potential bug test files to the repository
    # Use the global test file path from config to determine where to place them
    target_test_dir = Path(test_config.get_test_file_path()).parent
    
    # Ensure the target directory exists
    target_test_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy each potential bug test file
    for test_file in potential_bugs_dir.glob("*.java"):
        target_file = target_test_dir / test_file.name
        target_file.write_text(test_file.read_text())
    
    # Test each potential bug-revealing test
    for test_file in potential_bugs_dir.glob("*.java"):
        # Use the copied file in the repository
        target_file = target_test_dir / test_file.name
        test_result = test_single_bug_assessment(
            target_file, repo_path, build_system, package
        )
        results[test_file.name] = test_result
    
    return results


def test_bug_assessment(
    repo_path: Path, 
    fix_commit_hash: str, 
    potential_bugs_dir: Path,
    build_system: str,
    package: str,
    repo_url: str,
    output_dir: Path,
    run_potential_bugs: bool = True,
    json_logger = None
) -> Tuple[Dict[str, int], Dict[str, str]]:
    """
    Run regression detection and optionally potential bugs testing with a single repository clone.
    
    Args:
        repo_path: Path to the repository
        fix_commit_hash: Commit hash of the bug fix
        potential_bugs_dir: Directory containing potential bug-revealing tests
        build_system: Build system type ("gradle" or "maven")
        package: Package name for the tests
        repo_url: Repository URL for fresh cloning
        output_dir: Output directory for regression detection
        run_potential_bugs: Whether to run potential bugs testing
        json_logger: Optional JSON logger to update with regression results
        
    Returns:
        Tuple of (regression_results, bug_results)
    """
    # 1. Backup build files before deleting the repo
    backup_files = backup_build_files(repo_path)
    
    try:
        # 2. Delete the bug commit repo
        import shutil
        shutil.rmtree(repo_path)
        
        # 3. Clone fresh repo on fix commit hash
        repo_manager = RepositoryManager(repo_path.parent)
        repo_path = repo_manager.clone_repository(repo_url, fix_commit_hash)
        
        # 4. Restore build files (with our dependencies)
        restore_build_files(repo_path, backup_files)
        
        # 5. Run enhanced regression detection
        regression_results = run_final_test_suite_on_fix_commit_enhanced(
            repo_path=repo_path,
            output_dir=output_dir,
            build_system=build_system,
            package=package,
            json_logger=json_logger
        )
        
        # 6. Clean up test suite for potential bugs testing
        if run_potential_bugs and potential_bugs_dir.exists():
            # Delete the test suite file to get a clean slate
            target_test_file = Path(test_config.get_test_file_path())
            if target_test_file.exists():
                target_test_file.unlink()
            
            # 7. Run potential bugs testing in the same repository
            bug_results = test_potential_bugs_in_existing_repo(
                repo_path=repo_path,
                potential_bugs_dir=potential_bugs_dir,
                build_system=build_system,
                package=package
            )
        else:
            bug_results = {}
            
    finally:
        # No cleanup needed - we're using in-memory storage
        pass
    
    return regression_results, bug_results


def display_bug_assessment_results(bug_results: Dict[str, str]):
    """
    Display the bug assessment results.
    
    Args:
        bug_results: Dictionary mapping test filename to result
    """
    bug_revealed_count = sum(1 for result in bug_results.values() if result == "bug_revealed")
    still_failing_count = len(bug_results) - bug_revealed_count
    bug_found = bug_revealed_count > 0
    
    print(f"\n{summary('Bug Assessment Results:')}")
    print("─" * 50)
    print(f"   Total potential bug-revealing tests: {len(bug_results)}")
    print(f"   {info('Bug successfully revealed:')} {'Yes' if bug_found else 'No'}")
    print(f"   {error('Still failing:')} {still_failing_count}")
    
    if bug_found:
        print(f"\n   {success('SUCCESS! The following tests revealed real bugs:')}")
        for test_file, result in bug_results.items():
            if result == "bug_revealed":
                print(f"      • {test_file}")
    
    # Show detailed breakdown of failures
    if still_failing_count > 0:
        failure_counts = {
            "assertion_error": 0,
            "runtime_error": 0,
            "timeout": 0,
            "invalid_filename": 0
        }
        
        for result in bug_results.values():
            if result in failure_counts:
                failure_counts[result] += 1
        
        print(f"\n   {info('Failure Breakdown:')}")
        for failure_type, count in failure_counts.items():
            if count > 0:
                readable_type = failure_type.replace("_", " ").title()
                print(f"      • {readable_type}: {count}") 