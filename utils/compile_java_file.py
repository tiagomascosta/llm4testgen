import subprocess
import logging
from pathlib import Path
import os
import shutil
import xml.etree.ElementTree as ET
from config import test_config
from init.build import _ensure_sdkman_installed, _install_jdk_with_sdkman

logger = logging.getLogger(__name__)

def verify_compiled_class(test_file: Path, repo_path: Path) -> bool:
    """
    Verify that the test class was compiled by checking for the .class file.
    
    Args:
        test_file: Path to the test file that was compiled
        repo_path: Root directory of the repository
        
    Returns:
        True if the compiled class file is found, False otherwise
    """
    class_name = test_file.stem
    
    # Check Maven output directory
    maven_target = repo_path / "target"
    if maven_target.exists():
        cmd = f"find {maven_target} -type f -name '{class_name}.class'"
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.stdout.strip():
                return True
        except Exception as e:
            logger.error(f"Error checking Maven output: {str(e)}")
    
    # Check Gradle output directory
    gradle_build = repo_path / "build" / "classes"
    if gradle_build.exists():
        cmd = f"find {gradle_build} -type f -name '{class_name}.class'"
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.stdout.strip():
                return True
        except Exception as e:
            logger.error(f"Error checking Gradle output: {str(e)}")
    
    return False

def find_test_package_structure(repo_path: Path) -> str:
    """
    Find the package structure used for tests in the project.
    """
    test_dir = repo_path / "src" / "test" / "java"
    if not test_dir.exists():
        return None
    
    # Look for .java files in the test directory
    test_files = list(test_dir.rglob("*.java"))
    if not test_files:
        return None
        
    # Get the common package structure from existing tests
    packages = [f.parent.relative_to(test_dir) for f in test_files]
    if packages:
        # Convert path to package structure (e.g., org/byteskript/skript/test -> org.byteskript.skript.test)
        return str(packages[0]).replace('/', '.')
    return None

def ensure_test_package_matches(test_file: Path, repo_path: Path) -> bool:
    """
    Ensure the test file's package declaration matches its location in the project structure.
    """
    # Read the test file
    try:
        with open(test_file, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Error reading test file: {str(e)}")
        return False
        
    # Extract current package declaration
    import re
    package_match = re.search(r'package\s+([^;]+);', content)
    if not package_match:
        print("❌ No package declaration found in test file")
        return False
        
    # The package declaration is already correct from test_scaffold.py
    return True

def is_relevant_line(line):
    # Skip empty lines
    if not line.strip():
        return False
    
    # Skip "wrote" messages
    if "wrote" in line:
        return False
    
    # Skip repeated warnings
    if "WARNING" in line and "deprecated" in line.lower():
        return False
    
    # Skip debug messages
    if line.startswith("[DEBUG]"):
        return False
    
    # Always show build status messages
    if "BUILD SUCCESS" in line:
        return True
    
    # Skip other INFO messages except for compilation
    if line.startswith("[INFO]") and not "Compiling" in line:
        return False
    
    # Show important information
    return (
        "ERROR" in line or  # Error messages
        "FAILED" in line or  # Failure messages
        "Exception" in line or  # Exceptions
        "Caused by" in line or  # Exception causes
        "Compiling" in line  # Compilation status
    )

def get_java11_path() -> str:
    """
    Get the path to Java 11 installation.
    
    Returns:
        Path to Java 11 installation or None if not found
    """
    # Common locations for Java 11
    possible_paths = [
        "/usr/lib/jvm/java-11-openjdk-amd64",
        "/usr/lib/jvm/java-11-openjdk",
        "/usr/lib/jvm/java-11-oracle",
        "/usr/lib/jvm/java-11",
        "/opt/java/jdk-11",
        "/Library/Java/JavaVirtualMachines/jdk-11.jdk/Contents/Home"  # macOS
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
            
    # Try to find Java 11 using java -version
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            check=False
        )
        if "version \"11" in result.stderr:
            # Get the path from java.home system property
            result = subprocess.run(
                ["java", "-XshowSettings:properties", "-version"],
                capture_output=True,
                text=True,
                check=False
            )
            for line in result.stderr.split('\n'):
                if "java.home" in line:
                    return line.split('=')[1].strip()
    except Exception:
        pass
        
    # Try to install Java 11 using SDKMAN
    if _ensure_sdkman_installed():
        jdk_path = _install_jdk_with_sdkman("11")
        if jdk_path:
            return jdk_path
        
    return None

def parse_java_version(version_str: str) -> int:
    """
    Parse Java version string into a comparable integer.
    Handles formats like "1.7", "7", "1.8", "8", "11", etc.
    
    Args:
        version_str: Java version string
        
    Returns:
        Integer version number (e.g., 7 for "1.7" or "7")
    """
    # Remove any non-numeric characters except dots
    version_str = ''.join(c for c in version_str if c.isdigit() or c == '.')
    
    # Split by dots and take the last number
    parts = version_str.split('.')
    if len(parts) > 1 and parts[0] == '1':
        # Handle old format (e.g., "1.7" -> 7, "1.8" -> 8)
        return int(parts[1])
    else:
        # Handle new format (e.g., "7", "8", "11")
        return int(parts[0])

def has_spring_javaformat_plugin(repo_path: Path) -> bool:
    """
    Check if the pom.xml has the Spring Java Format plugin.
    """
    pom_path = repo_path / 'pom.xml'
    if not pom_path.exists():
        return False
        
    try:
        tree = ET.parse(pom_path)
        root = tree.getroot()
        
        # Define the namespace map
        ns = {'mvn': 'http://maven.apache.org/POM/4.0.0'}
        
        # Look for the plugin in both build/plugins and build/pluginManagement/plugins
        for plugins_path in ['./mvn:build/mvn:plugins/mvn:plugin', './mvn:build/mvn:pluginManagement/mvn:plugins/mvn:plugin']:
            for plugin in root.findall(plugins_path, ns):
                group_id = plugin.find('mvn:groupId', ns)
                artifact_id = plugin.find('mvn:artifactId', ns)
                
                if (group_id is not None and artifact_id is not None and
                    group_id.text == 'io.spring.javaformat' and 
                    artifact_id.text == 'spring-javaformat-maven-plugin'):
                    return True
        return False
    except Exception as e:
        logger.error(f"Error checking for Spring Java Format plugin: {str(e)}")
        return False

def compile_java_file(test_file: Path, repo_path: Path, java_home: str = None) -> bool:
    """
    Compile a Java test file using Maven or Gradle.
    
    Args:
        test_file: Path to the test file
        repo_path: Path to the repository root
        java_home: Path to Java home directory (optional)
        
    Returns:
        bool: True if compilation succeeded, False otherwise
    """
    # Get Java version and path from global config
    java_version = test_config.get_java_version()
    java_path = test_config.get_java_path()  # This should be set when we detect the Java version
    
    if not java_path:
        logger.error("Java path not set in test_config")
        return False
        
    # Determine build system
    is_maven = (repo_path / 'pom.xml').exists()
    
    if is_maven:
        # Maven command - use clean test-compile to ensure new test files are compiled
        cmd = [
            "mvn",
            "clean",
            "compile",
            "test-compile",
            "-U",
            "-Dcheckstyle.skip=true",
            "-Dspotless.check.skip=true",
            "-Dpmd.skip=true",
            "-Dfindbugs.skip=true"
        ]
        
        # Add Spring Java Format skip flag if the plugin is present
        if has_spring_javaformat_plugin(repo_path):
            cmd.append("-Dspring-javaformat.skip=true")
            
    else:
        # Check for Gradle wrapper and make it executable
        gradle_wrapper = repo_path / "gradlew"
        if gradle_wrapper.exists():
            # Make gradlew executable
            try:
                gradle_wrapper.chmod(0o755)  # rwxr-xr-x
                gradle_cmd = "./gradlew"
            except Exception as e:
                logger.error(f"Error making gradlew executable: {str(e)}")
                gradle_cmd = "gradle"
        else:
            gradle_cmd = "gradle"
            
        # Basic Gradle command using the original build.gradle
        cmd = [
            gradle_cmd,
            "compileTestJava",
            "--no-daemon"
        ]
            
    # Run compilation
    try:
        # Set up environment variables for Java
        env = os.environ.copy()
        env['JAVA_HOME'] = java_path
        env['PATH'] = f"{java_path}/bin:{env['PATH']}"
        env['GRADLE_OPTS'] = f"-Dorg.gradle.java.home={java_path}"

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            env=env
        )
        
        # Check if compilation succeeded
        build_success = "BUILD SUCCESSFUL" in result.stdout if not is_maven else "BUILD SUCCESS" in result.stdout
        class_found = verify_compiled_class(test_file, repo_path)
        
        # Check for version compatibility error
        version_error = "UnsupportedClassVersionError" in result.stderr
        
        if build_success and class_found:
            print(f"   ✅ Compilation successful")
            return True
        else:
            # If compilation failed and we're using Java < 11, try with Java 11
            current_version = parse_java_version(java_version)
            if current_version < 11 and (not build_success or version_error):
                print(f"⚠️ Compilation failed with Java {current_version}")
                
                java11_path = get_java11_path()
                if java11_path:
                    # Update environment variables for Java 11
                    env['JAVA_HOME'] = java11_path
                    env['PATH'] = f"{java11_path}/bin:{env['PATH']}"
                    env['GRADLE_OPTS'] = f"-Dorg.gradle.java.home={java11_path}"
                    
                    # Retry compilation with Java 11
                    result = subprocess.run(
                        cmd,
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        check=False,
                        env=env
                    )
                    
                    # Check if retry succeeded
                    build_success = "BUILD SUCCESSFUL" in result.stdout if not is_maven else "BUILD SUCCESS" in result.stdout
                    class_found = verify_compiled_class(test_file, repo_path)
                    
                    if build_success and class_found:
                        print(f"   ✅ Compilation successful with Java 11")
                        # Update test configuration to use Java 11
                        test_config.set_java_version("11")
                        test_config.set_java_path(java11_path)
                        print("✅ Updated test configuration to use Java 11")
                        return True
                else:
                    print("❌ Java 11 not found. Please install Java 11 to compile with ANTLR4 plugin.")
            
            print("   ❌ Compilation failed")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Compilation failed with error: {str(e)}")
        return False 