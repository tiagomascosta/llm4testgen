"""
JaCoCo coverage analysis module.

This module provides functionality to:
- Run tests with JaCoCo coverage enabled
- Parse JaCoCo XML reports
- Extract coverage metrics for specific classes and methods
"""

import subprocess
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from .coverage_metrics import CoverageMetrics, CoverageReport
from .coverage_config import get_coverage_config
import re

# Try to import build system detector, but make it optional for testing
try:
    from utils.build_system_detector import detect_build_system
except ImportError:
    # For testing purposes, provide a dummy function
    def detect_build_system(repo_path):
        """Dummy function for testing when final_implementation is not available."""
        return "gradle"  # Default to gradle for testing


def xml_path_for_jacoco(repo_root: Path) -> Path:
    """
    Build path to JaCoCo XML report.
    
    First checks the build files (build.gradle or pom.xml) for configured output paths,
    then falls back to standard locations.
    
    Args:
        repo_root: Path to the repository root
        
    Returns:
        Path to the JaCoCo XML report
    """
    # First, try to find the configured path from build files
    configured_path = _get_configured_jacoco_path(repo_root)
    if configured_path and configured_path.exists():
        return configured_path
    
    # Fallback to standard paths
    # Standard Gradle JaCoCo location
    standard_path = repo_root / "build" / "reports" / "jacoco" / "test" / "jacocoTestReport.xml"
    if standard_path.exists():
        return standard_path
    
    # Check for custom coverage.xml location (common in some projects)
    custom_path = repo_root / "build" / "reports" / "coverage.xml"
    if custom_path.exists():
        return custom_path
    
    # Check for alternative Gradle location
    alt_path = repo_root / "build" / "reports" / "jacoco" / "jacocoTestReport.xml"
    if alt_path.exists():
        return alt_path
    
    # Default to standard path (will be checked for existence by caller)
    return standard_path


def _get_configured_jacoco_path(repo_root: Path) -> Optional[Path]:
    """
    Extract configured JaCoCo XML output path from build files.
    
    Args:
        repo_root: Path to the repository root
        
    Returns:
        Configured path if found, None otherwise
    """
    # Check for Gradle build file
    gradle_file = repo_root / "build.gradle"
    if gradle_file.exists():
        return _get_gradle_jacoco_path(gradle_file, repo_root)
    
    # Check for Maven POM file
    pom_file = repo_root / "pom.xml"
    if pom_file.exists():
        return _get_maven_jacoco_path(pom_file, repo_root)
    
    return None


def _get_gradle_jacoco_path(gradle_file: Path, repo_root: Path) -> Optional[Path]:
    """
    Extract JaCoCo XML output path from Gradle build file.
    
    Args:
        gradle_file: Path to build.gradle file
        repo_root: Repository root path
        
    Returns:
        Configured path if found, None otherwise
    """
    try:
        content = gradle_file.read_text()
        
        # Look for xml.outputLocation configuration (newer Gradle syntax)
        # Pattern: xml.outputLocation = file("path/to/file.xml")
        output_location_match = re.search(r'xml\.outputLocation\s*=\s*file\s*\(\s*["\']([^"\']+)["\']\s*\)', content)
        if output_location_match:
            relative_path = output_location_match.group(1)
            # Remove quotes and resolve relative to repo root
            relative_path = relative_path.strip('"\'')
            # Handle Gradle variables
            relative_path = relative_path.replace('$buildDir', 'build')
            configured_path = repo_root / relative_path
            return configured_path
        
        # Look for xml.destination configuration (older Gradle syntax)
        # Pattern: xml.destination = new File("path/to/file.xml")
        destination_match = re.search(r'xml\.destination\s*=\s*new\s+File\s*\(\s*["\']([^"\']+)["\']\s*\)', content)
        if destination_match:
            relative_path = destination_match.group(1)
            # Remove quotes and resolve relative to repo root
            relative_path = relative_path.strip('"\'')
            # Handle Gradle variables
            relative_path = relative_path.replace('$buildDir', 'build')
            configured_path = repo_root / relative_path
            return configured_path
        
        # Look for xml.required = true or xml.enabled = true (standard location)
        if 'xml.required = true' in content or 'xml.enabled = true' in content:
            # Use standard Gradle location
            standard_path = repo_root / "build" / "reports" / "jacoco" / "test" / "jacocoTestReport.xml"
            return standard_path
            
    except Exception as e:
        print(f"Warning: Could not parse Gradle file for JaCoCo path: {e}")
    
    return None


def _get_maven_jacoco_path(pom_file: Path, repo_root: Path) -> Optional[Path]:
    """
    Extract JaCoCo XML output path from Maven POM file.
    
    Args:
        pom_file: Path to pom.xml file
        repo_root: Repository root path
        
    Returns:
        Configured path if found, None otherwise
    """
    try:
        tree = ET.parse(pom_file)
        root = tree.getroot()
        
        # Define namespace
        ns = {'mvn': 'http://maven.apache.org/POM/4.0.0'}
        
        # Look for jacoco-maven-plugin configuration
        plugins = root.findall('.//mvn:plugin', ns)
        for plugin in plugins:
            artifact_id = plugin.find('mvn:artifactId', ns)
            if artifact_id is not None and artifact_id.text == 'jacoco-maven-plugin':
                # Check for custom output directory in plugin-level configuration
                configuration = plugin.find('mvn:configuration', ns)
                if configuration is not None:
                    output_dir = configuration.find('mvn:outputDirectory', ns)
                    if output_dir is not None:
                        return repo_root / output_dir.text / "jacoco.xml"
                
                # Check for custom output directory in execution configurations
                executions = plugin.findall('.//mvn:execution', ns)
                for execution in executions:
                    exec_config = execution.find('mvn:configuration', ns)
                    if exec_config is not None:
                        output_dir = exec_config.find('mvn:outputDirectory', ns)
                        if output_dir is not None:
                            return repo_root / output_dir.text / "jacoco.xml"
                
                # Default Maven JaCoCo location
                return repo_root / "target" / "site" / "jacoco" / "jacoco.xml"
                
    except Exception as e:
        print(f"Warning: Could not parse POM file for JaCoCo path: {e}")
    
    return None


def make_class_identifier(package: str, class_name: str, inner_class: Optional[str] = None) -> str:
    """
    Create JaCoCo class identifier format.
    
    Args:
        package: Java package name
        class_name: Java class name
        inner_class: Optional inner class name
        
    Returns:
        JaCoCo class identifier string
    """
    slash_pkg = package.replace(".", "/")
    if inner_class:
        return f"{slash_pkg}/{class_name}${inner_class}"
    return f"{slash_pkg}/{class_name}"


def extract_counter(element: ET.Element, counter_type: str) -> Tuple[int, int]:
    """
    Extract covered/missed counts for specific counter type.
    
    Args:
        element: XML element containing counter data
        counter_type: Type of counter to extract (INSTRUCTION, BRANCH, LINE)
        
    Returns:
        Tuple of (covered_count, missed_count)
    """
    for counter in element.findall("counter"):
        if counter.get("type") == counter_type:
            return (
                int(counter.get("covered", "0")),
                int(counter.get("missed", "0"))
            )
    return 0, 0


def _detect_jacoco_profile(pom_file: Path) -> Optional[str]:
    """
    Detect if JaCoCo plugin is configured in a Maven profile.
    
    Args:
        pom_file: Path to pom.xml file
        
    Returns:
        Profile name if JaCoCo is found in a profile, None otherwise
    """
    try:
        tree = ET.parse(pom_file)
        root = tree.getroot()
        ns = {'mvn': 'http://maven.apache.org/POM/4.0.0'}
        
        # Look for profiles section
        profiles = root.findall('.//mvn:profile', ns)
        for profile in profiles:
            profile_id = profile.find('mvn:id', ns)
            if profile_id is not None:
                # Check if this profile contains JaCoCo plugin
                plugins = profile.findall('.//mvn:plugin', ns)
                for plugin in plugins:
                    artifact_id = plugin.find('mvn:artifactId', ns)
                    if artifact_id is not None and artifact_id.text == 'jacoco-maven-plugin':
                        return profile_id.text
        
        return None
    except Exception as e:
        print(f"WARNING: Could not parse POM.xml to check for JaCoCo profiles: {e}")
        return None


def _check_main_build_jacoco_config(pom_file: Path) -> bool:
    """
    Check if main build has a better JaCoCo configuration than profiles.
    
    Args:
        pom_file: Path to pom.xml file
        
    Returns:
        True if main build config is better, False otherwise
    """
    try:
        tree = ET.parse(pom_file)
        root = tree.getroot()
        ns = {'mvn': 'http://maven.apache.org/POM/4.0.0'}
        
        # Look for JaCoCo plugin in main build
        plugins = root.findall('.//mvn:build/mvn:plugins/mvn:plugin', ns)
        for plugin in plugins:
            artifact_id = plugin.find('mvn:artifactId', ns)
            if artifact_id is not None and artifact_id.text == 'jacoco-maven-plugin':
                # Found JaCoCo in main build, now analyze its configuration
                return _analyze_jacoco_config_quality(plugin, ns)
        
        return False  # No JaCoCo in main build
        
    except Exception as e:
        print(f"WARNING: Could not analyze main build JaCoCo config: {e}")
        return False


def _analyze_jacoco_config_quality(jacoco_plugin: ET.Element, ns: dict) -> bool:
    """
    Analyze if JaCoCo configuration is unit-test focused and well-configured.
    
    Args:
        jacoco_plugin: JaCoCo plugin element
        ns: XML namespace dictionary
        
    Returns:
        True if configuration is good for unit tests, False otherwise
    """
    score = 0
    
    # Check executions
    executions = jacoco_plugin.findall('.//mvn:execution', ns)
    for execution in executions:
        # Check if it's unit test focused
        phase = execution.find('mvn:phase', ns)
        if phase is not None:
            if phase.text == 'test':
                score += 3  # Unit test phase - excellent
            elif 'integration' in phase.text:
                score -= 2  # Integration test phase - not what we want
        
        # Check execution ID
        exec_id = execution.find('mvn:id', ns)
        if exec_id is not None:
            if 'unit' in exec_id.text.lower() or 'ut' in exec_id.text.lower():
                score += 2  # Unit test focused
            elif 'integration' in exec_id.text.lower() or 'it' in exec_id.text.lower():
                score -= 1  # Integration test focused
        
        # Check configuration
        config = execution.find('mvn:configuration', ns)
        if config is not None:
            dest_file = config.find('mvn:destFile', ns)
            if dest_file is not None:
                if 'ut' in dest_file.text or 'jacoco.exec' in dest_file.text:
                    score += 1  # Unit test file naming
                elif 'it' in dest_file.text:
                    score -= 1  # Integration test file naming
            
            output_dir = config.find('mvn:outputDirectory', ns)
            if output_dir is not None:
                if 'jacoco-ut' in output_dir.text or 'site/jacoco' in output_dir.text:
                    score += 1  # Standard unit test output
                elif 'jacoco-it' in output_dir.text:
                    score -= 1  # Integration test output
    
    # Check if it has both prepare-agent and report goals
    has_prepare_agent = False
    has_report = False
    for execution in executions:
        goals = execution.findall('.//mvn:goal', ns)
        for goal in goals:
            if goal.text == 'prepare-agent':
                has_prepare_agent = True
            elif goal.text == 'report':
                has_report = True
    
    if has_prepare_agent and has_report:
        score += 2  # Complete configuration
    
    # Check if it's not directly skipped (we'll override property-based skipping)
    config = jacoco_plugin.find('mvn:configuration', ns)
    if config is not None:
        skip = config.find('mvn:skip', ns)
        if skip is not None and skip.text == 'true':
            score -= 5  # Directly skipped configuration is bad
    
    # Decision threshold
    return score >= 2  # Main build is better if score is 2 or higher


def run_tests_with_coverage(
    repo_path: Path,
    build_system: str,
    test_class: Optional[str] = None,
    java_home: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Run tests with JaCoCo coverage enabled.
    
    Args:
        repo_path: Path to the repository root
        build_system: Build system type ("gradle" or "maven")
        test_class: Optional specific test class to run (e.g., "com.example.MyTest")
        java_home: Optional Java home path (deprecated, now uses stored config)
        
    Returns:
        Tuple of (success: bool, output: str)
    """
    try:
        # Set environment variables
        env = os.environ.copy()
        # Get Java version and path from global config (like compile_java_file.py does)
        from config import test_config
        java_version = test_config.get_java_version()
        java_path = test_config.get_java_path()
        
        if java_path:
            env['JAVA_HOME'] = java_path
            env['PATH'] = f"{java_path}/bin:{env['PATH']}"
            if build_system == "gradle":
                env['GRADLE_OPTS'] = f"-Dorg.gradle.java.home={java_path}"
        else:
            print("WARNING: Java path not set in test_config")
        
        # Build command based on build system
        if build_system == "gradle":
            # Check for Gradle wrapper
            gradle_wrapper = repo_path / "gradlew"
            if gradle_wrapper.exists():
                gradle_wrapper.chmod(0o755)
                if test_class:
                    # Run only the specific test class
                    cmd = [str(gradle_wrapper), "clean", "test", f"--tests={test_class}", "jacocoTestReport"]
                else:
                    # Run all tests (fallback)
                    cmd = [str(gradle_wrapper), "clean", "test", "jacocoTestReport"]
            else:
                if test_class:
                    cmd = ["gradle", "clean", "test", f"--tests={test_class}", "jacocoTestReport"]
                else:
                    cmd = ["gradle", "clean", "test", "jacocoTestReport"]
                
        elif build_system == "maven":
            # Check if JaCoCo is in a profile
            pom_path = repo_path / "pom.xml"
            jacoco_profile = None
            if pom_path.exists():
                jacoco_profile = _detect_jacoco_profile(pom_path)
            
            # Step 2: If we found a profile, check if main build has better JaCoCo config
            if jacoco_profile:
                has_better_main_config = _check_main_build_jacoco_config(pom_path)
                if has_better_main_config:
                    print(f"📋 Found JaCoCo in profile '{jacoco_profile}', but main build has better config - using main build")
                    jacoco_profile = None
                else:
                    print(f"📋 Using JaCoCo from profile '{jacoco_profile}' (main build has no/inferior JaCoCo config)")
            
            # Check if the project uses Surefire plugin
            uses_surefire = False
            if pom_path.exists():
                try:
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
                if test_class:
                    # Extract class name from fully qualified name for Maven
                    class_name = test_class.split('.')[-1]
                    # Use a simple approach: run the full Maven lifecycle which should handle JaCoCo properly
                    cmd = ["mvn", "clean", "test", "jacoco:report", 
                           f"-Dtest={class_name}", 
                           "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true"]
                else:
                    cmd = ["mvn", "clean", "test", "jacoco:report", 
                           "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true", "-Denforcer.skip=true"]
            else:
                # Project doesn't use Surefire, use vanilla JaCoCo approach
                print("Project doesn't use Surefire plugin, using vanilla JaCoCo approach")
                
                # For projects without Surefire, just run the vanilla JaCoCo setup
                # The JaCoCo plugin should work with Maven's default test execution
                if test_class:
                    class_name = test_class.split('.')[-1]
                    cmd = ["mvn", "clean", "test", "jacoco:report", 
                           f"-Dtest={class_name}", 
                           "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true", "-Denforcer.skip=true"]
                else:
                    cmd = ["mvn", "clean", "test", "jacoco:report", 
                           "-Dspotless.check.skip=true", "-Dcheckstyle.skip=true", "-Dpmd.skip=true", "-Dfindbugs.skip=true", "-Dspring-javaformat.skip=true", "-Dsortpom.skip=true", "-Denforcer.skip=true"]
            
            # Add JaCoCo skip property overrides to ensure JaCoCo is enabled
            common_jacoco_overrides = [
                "-Djacoco.skip.instrument=false",
                "-Djacoco.skip=false",
                "-Djacoco.skip.report=false"
            ]
            cmd.extend(common_jacoco_overrides)
            
            # Add profile flag if JaCoCo is in a profile
            if jacoco_profile:
                cmd.extend(["-P", jacoco_profile])
                print(f"📋 Using Maven profile '{jacoco_profile}' for JaCoCo")
            
        else:
            raise ValueError(f"Unsupported build system: {build_system}")
        
        # Run the command
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            env=env
        )
        
        # Combine stdout and stderr
        output = result.stdout + "\n" + result.stderr
        
        # Check if JaCoCo XML report was generated
        xml_path = xml_path_for_jacoco(repo_path)
        if not xml_path.exists():
            # Try alternative Maven path
            xml_path = repo_path / "target" / "site" / "jacoco" / "jacoco.xml"
            if not xml_path.exists():
                return False, f"JaCoCo XML report not found at expected locations. Output: {output}"
        
        return result.returncode == 0, output
        
    except subprocess.TimeoutExpired:
        return False, f"Test execution timed out after 5 minutes"
    except Exception as e:
        return False, f"Failed to run tests with coverage: {str(e)}"


def parse_jacoco_xml(xml_path: Path) -> ET.Element:
    """
    Parse JaCoCo XML report and return root element.
    
    Args:
        xml_path: Path to the JaCoCo XML report
        
    Returns:
        XML root element
        
    Raises:
        FileNotFoundError: If XML report doesn't exist
        ET.ParseError: If XML is malformed
    """
    if not xml_path.exists():
        raise FileNotFoundError(f"JaCoCo XML report not found: {xml_path}")
    
    try:
        tree = ET.parse(xml_path)
        return tree.getroot()
    except ET.ParseError as e:
        raise ET.ParseError(f"Failed to parse JaCoCo XML: {e}")


def find_target_class(
    xml_root: ET.Element,
    package: str,
    class_name: str,
    inner_class: Optional[str] = None
) -> Optional[ET.Element]:
    """
    Find target class element in JaCoCo XML.
    
    Args:
        xml_root: XML root element
        package: Java package name
        class_name: Java class name
        inner_class: Optional inner class name
        
    Returns:
        Class element if found, None otherwise
    """
    target_class_name = make_class_identifier(package, class_name, inner_class)
    
    # Search through all packages
    for package_elem in xml_root.findall("package"):
        for class_elem in package_elem.findall("class"):
            class_name_in_xml = class_elem.get("name")
            if class_name_in_xml == target_class_name:
                return class_elem
    
    return None


def extract_method_coverage(
    class_element: ET.Element,
    method_name: str
) -> Optional[CoverageMetrics]:
    """
    Extract coverage metrics for specific method.
    
    Args:
        class_element: Class XML element
        method_name: Method name to extract coverage for
        
    Returns:
        CoverageMetrics object if method found, None otherwise
    """
    # Find the method element
    method_element = None
    for method in class_element.findall("method"):
        if method.get("name") == method_name:
            method_element = method
            break
    
    if not method_element:
        return None
    
    # Extract coverage metrics
    instr_covered, instr_missed = extract_counter(method_element, "INSTRUCTION")
    branch_covered, branch_missed = extract_counter(method_element, "BRANCH")
    line_covered, line_missed = extract_counter(method_element, "LINE")
    
    return CoverageMetrics(
        instructions_covered=instr_covered,
        instructions_missed=instr_missed,
        branches_covered=branch_covered,
        branches_missed=branch_missed,
        lines_covered=line_covered,
        lines_missed=line_missed,
        target_name=method_name,
        target_type="method"
    )


def extract_class_coverage(class_element: ET.Element, class_name: str) -> CoverageMetrics:
    """
    Extract overall coverage metrics for class.
    
    Args:
        class_element: Class XML element
        class_name: Class name for the metrics
        
    Returns:
        CoverageMetrics object
    """
    # Extract coverage metrics from class element
    instr_covered, instr_missed = extract_counter(class_element, "INSTRUCTION")
    branch_covered, branch_missed = extract_counter(class_element, "BRANCH")
    line_covered, line_missed = extract_counter(class_element, "LINE")
    
    return CoverageMetrics(
        instructions_covered=instr_covered,
        instructions_missed=instr_missed,
        branches_covered=branch_covered,
        branches_missed=branch_missed,
        lines_covered=line_covered,
        lines_missed=line_missed,
        target_name=class_name,
        target_type="class"
    )


def analyze_coverage(
    repo_path: Path,
    package: str,
    class_name: str,
    method_name: Optional[str] = None,
    inner_class: Optional[str] = None
) -> Dict[str, CoverageMetrics]:
    """
    Analyze coverage for a specific class and optionally a method.
    
    Args:
        repo_path: Path to the repository root
        package: Java package name
        class_name: Java class name
        method_name: Optional method name to analyze
        inner_class: Optional inner class name
        
    Returns:
        Dictionary mapping target names to CoverageMetrics objects
    """
    results = {}
    
    try:
        # Find JaCoCo XML report
        xml_path = xml_path_for_jacoco(repo_path)
        if not xml_path.exists():
            # Try alternative Maven path
            xml_path = repo_path / "target" / "site" / "jacoco" / "jacoco.xml"
            if not xml_path.exists():
                raise FileNotFoundError(f"JaCoCo XML report not found")
        
        # Parse XML
        xml_root = parse_jacoco_xml(xml_path)
        
        # Find target class
        class_element = find_target_class(xml_root, package, class_name, inner_class)
        if not class_element:
            raise ValueError(f"Target class not found in coverage report")
        
        # Extract class coverage
        class_metrics = extract_class_coverage(class_element, class_name)
        results[f"{class_name}_class"] = class_metrics
        
        # Extract method coverage if requested
        if method_name:
            method_metrics = extract_method_coverage(class_element, method_name)
            if method_metrics:
                results[f"{method_name}_method"] = method_metrics
            else:
                # Method not found, create empty metrics
                results[f"{method_name}_method"] = CoverageMetrics(
                    target_name=method_name,
                    target_type="method"
                )
        
        return results
        
    except Exception as e:
        raise RuntimeError(f"Failed to analyze coverage: {str(e)}")


def safe_coverage_analysis(
    repo_path: Path,
    package: str,
    class_name: str,
    method_name: Optional[str] = None,
    inner_class: Optional[str] = None
) -> Optional[Dict[str, CoverageMetrics]]:
    """
    Safely perform coverage analysis with error handling.
    
    Args:
        repo_path: Path to the repository root
        package: Java package name
        class_name: Java class name
        method_name: Optional method name to analyze
        inner_class: Optional inner class name
        
    Returns:
        Dictionary of coverage metrics if successful, None otherwise
    """
    try:
        return analyze_coverage(repo_path, package, class_name, method_name, inner_class)
    except FileNotFoundError as e:
        print(f"Warning: {e}")
        return None
    except ET.ParseError as e:
        print(f"Error: Failed to parse JaCoCo XML: {e}")
        return None
    except Exception as e:
        print(f"Error: Coverage analysis failed: {e}")
        return None


def display_coverage_results(coverage_results: Dict[str, CoverageMetrics]) -> None:
    """
    Display formatted coverage results.
    
    Args:
        coverage_results: Dictionary of coverage metrics
    """
    from .coverage_metrics import format_coverage_display
    
    print("\n📊 Method Coverage Analysis Results:")
    print("─" * 50)
    
    # Only show method coverage, filter out class coverage
    method_metrics = {name: metrics for name, metrics in coverage_results.items() 
                     if metrics.target_type == "method"}
    
    for target_name, metrics in method_metrics.items():
        print(format_coverage_display(metrics))
        print()


def export_coverage_data(
    coverage_results: Dict[str, CoverageMetrics],
    output_dir: Path,
    formats: List[str] = None
) -> None:
    """
    Export coverage data to various formats.
    
    Args:
        coverage_results: Dictionary of coverage metrics
        output_dir: Directory to save exported files
        formats: List of export formats ("json", "csv")
    """
    if formats is None:
        formats = ["json"]
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create coverage report
    report = CoverageReport()
    for metrics in coverage_results.values():
        report.add_metrics(metrics)
    
    # Export in requested formats
    if "json" in formats:
        json_path = output_dir / "coverage_report.json"
        report.export_to_json(json_path)
    
    if "csv" in formats:
        csv_path = output_dir / "coverage_report.csv"
        report.export_to_csv(csv_path)


def check_coverage_threshold(
    coverage_results: Dict[str, CoverageMetrics],
    threshold: float
) -> Tuple[bool, List[str]]:
    """
    Check if coverage meets the specified threshold.
    
    Args:
        coverage_results: Dictionary of coverage metrics
        threshold: Minimum coverage percentage
        
    Returns:
        Tuple of (meets_threshold: bool, failing_targets: List[str])
    """
    failing_targets = []
    
    for target_name, metrics in coverage_results.items():
        if not metrics.meets_threshold(threshold):
            failing_targets.append(f"{target_name}: {metrics.get_overall_coverage():.1f}%")
    
    meets_threshold = len(failing_targets) == 0
    return meets_threshold, failing_targets 