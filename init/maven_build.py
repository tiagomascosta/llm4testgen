import re
import logging
from pathlib import Path
from typing import Optional, Tuple
import subprocess
import os
from .maven import MavenConfig

logger = logging.getLogger(__name__)

def _parse_java_major(version: str) -> int:
    if version.startswith('1.'):
        return int(version.split('.')[1])
    return int(version.split('.')[0])

class MavenBuildManager:
    """Manages Maven project building and verification."""
    
    def __init__(self, repo_path: Path):
        """
        Initialize the Maven build manager.
        
        Args:
            repo_path: Path to the repository root
        """
        self.repo_path = repo_path
        self.maven_config = MavenConfig(repo_path)
        self.mvn_cmd = self._detect_maven_command()
        self.required_jdk_version = self._detect_required_jdk_version()
        self.java_home = self._find_or_install_java_home(self.required_jdk_version)

    def _detect_maven_command(self) -> str:
        """
        Detect the Maven command to use.
        
        Returns:
            The Maven command to use (mvn or ./mvnw)
        """
        mvnw = self.repo_path / 'mvnw'
        mvnw_bat = self.repo_path / 'mvnw.cmd'
        if mvnw.exists() and os.access(mvnw, os.X_OK):
            return './mvnw'
        if mvnw_bat.exists():
            logger.warning("Only mvnw.cmd (Windows wrapper) found. Falling back to system 'mvn'.")
        return 'mvn'

    def _detect_required_jdk_version(self) -> Optional[str]:
        """
        Detect the required JDK version from the POM file.
        
        Returns:
            Required JDK version if found, None otherwise
        """
        return self.maven_config.get_java_version()

    def _find_or_install_java_home(self, version: Optional[str]) -> Optional[str]:
        """
        Find or install the required JDK version.
        
        Args:
            version: Required JDK version
            
        Returns:
            Path to JAVA_HOME if found/installed, None otherwise
        """
        if not version:
            return None
            
        # First check if we have a matching JDK in the system
        for base in ['/usr/lib/jvm', '/usr/java', '/Library/Java/JavaVirtualMachines']:
            base_path = Path(base)
            if base_path.exists():
                for d in base_path.iterdir():
                    if d.is_dir() and str(version) in d.name:
                        java_home = d / 'Contents' / 'Home' if 'JavaVirtualMachines' in base else d
                        if (java_home / 'bin' / 'java').exists():
                            return str(java_home)
        
        # If not found, try to install with SDKMAN (with user confirmation)
        from .build import _ensure_sdkman_installed, _install_jdk_with_sdkman, _get_sdkman_identifier, _prompt_user_for_java_installation
        sdkman_identifier = _get_sdkman_identifier(version)
        if sdkman_identifier and _ensure_sdkman_installed():
            if _prompt_user_for_java_installation(version, sdkman_identifier):
                jdk_path = _install_jdk_with_sdkman(version)
                if jdk_path:
                    return jdk_path
            else:
                logger.warning(f"User declined Java installation. Cannot proceed without JDK {version}.")
                
        return None

    def _detect_jdk_version(self) -> Optional[str]:
        """
        Detect the installed JDK version.
        
        Returns:
            JDK version string if found, None otherwise
        """
        try:
            # Try to get Java version
            result = subprocess.run(
                ['java', '-version'],
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            
            # Java version is printed to stderr
            version_output = result.stderr
            
            # Try to extract version number
            version_match = re.search(r'version "([^"]+)"', version_output)
            if version_match:
                version = version_match.group(1)
                logger.info(f"Detected system JDK version: {version}")
                return version
                
            logger.warning("Could not parse Java version from output")
            return None
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to detect JDK version: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error detecting JDK version: {str(e)}")
            return None

    def _verify_jdk_compatibility(self) -> Tuple[bool, Optional[str]]:
        """
        Verify if the installed JDK is compatible with the project requirements.
        
        Returns:
            Tuple of (is_compatible, required_version)
        """
        required_version = self.required_jdk_version
        if not required_version:
            logger.warning("Could not detect required Java version from project files")
            return True, None
            
        # Get installed JDK version
        installed_version = self._detect_jdk_version()
        if not installed_version:
            logger.error("Could not detect installed JDK version")
            return False, required_version
            
        # Extract major version numbers
        installed_major = _parse_java_major(installed_version)
        required_major = _parse_java_major(required_version)
        
        # Compare versions
        is_compatible = installed_major >= required_major
        if not is_compatible:
            logger.error(f"JDK version mismatch. Required: {required_version}, Installed: {installed_version}")
            
        return is_compatible, required_version

    def _has_spring_javaformat_plugin(self) -> bool:
        """
        Check if the project uses the Spring Java Format Maven plugin.
        
        Returns:
            True if the plugin is present in pom.xml, False otherwise
        """
        try:
            pom_path = self.repo_path / 'pom.xml'
            if not pom_path.exists():
                return False
                
            import xml.etree.ElementTree as ET
            tree = ET.parse(pom_path)
            root = tree.getroot()
            
            # Add namespace mapping
            ns = {'': 'http://maven.apache.org/POM/4.0.0'}
            
            # Look for spring-javaformat-maven-plugin in plugins section
            plugins = root.find('.//plugins', ns)
            if plugins is not None:
                for plugin in plugins.findall('plugin', ns):
                    group_id = plugin.find('groupId', ns)
                    artifact_id = plugin.find('artifactId', ns)
                    if (group_id is not None and group_id.text == 'io.spring.javaformat' and
                        artifact_id is not None and artifact_id.text == 'spring-javaformat-maven-plugin'):
                        logger.info("Found Spring Java Format plugin in pom.xml")
                        return True
            return False
        except Exception as e:
            logger.error(f"Error checking for Spring Java Format plugin: {str(e)}")
            return False

    def _run_maven_command(self, command: str) -> subprocess.CompletedProcess:
        """
        Run a Maven command and return the result.
        
        Args:
            command: The Maven command to run
            
        Returns:
            CompletedProcess object with command output
            
        Raises:
            subprocess.CalledProcessError: If the command fails
        """
        env = os.environ.copy()
        if self.java_home:
            env['JAVA_HOME'] = self.java_home
            env['PATH'] = f"{self.java_home}/bin:" + env['PATH']
            logger.info(f"Using JAVA_HOME: {self.java_home}")
        
        # Extract the base command (mvn or ./mvnw) and the rest
        base_cmd = self.mvn_cmd
        rest_cmd = command.replace(self.mvn_cmd, '').strip()
        logger.info(f"Base Maven command: {base_cmd}")
        logger.info(f"Initial rest command: {rest_cmd}")
        
        # Add flags to skip tests
        if not rest_cmd.endswith('test'):
            rest_cmd = f"{rest_cmd} -DskipTests"
            logger.info("Added -DskipTests flag")
            
        # Add Java version specific flags for Java 8
        if self.required_jdk_version == '8':
            rest_cmd = f"{rest_cmd} -Dmaven.compiler.source=1.8 -Dmaven.compiler.target=1.8 -Dmaven.compiler.plugin.version=3.8.0"
            logger.info("Added Java 8 specific flags")
            
        # Add Spring Java Format skip flag if the plugin is present
        if self._has_spring_javaformat_plugin():
            logger.info("Found Spring Java Format plugin, adding skip flag")
            rest_cmd = f"{rest_cmd} -Dspring-javaformat.skip=true"
            
        # Add FindBugs skip flag to prevent analysis failures
        rest_cmd = f"{rest_cmd} -Dfindbugs.skip=true"
        logger.info("Added FindBugs skip flag")
            
        # Reconstruct the full command
        full_cmd = f"{base_cmd} {rest_cmd}"
        logger.info(f"Final Maven command to execute: {full_cmd}")
            
        try:
            logger.info(f"Executing command in directory: {self.repo_path}")
            result = subprocess.run(
                full_cmd,
                cwd=self.repo_path,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
                env=env
            )
            logger.info("Maven command executed successfully")
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Maven command failed with error: {e.stderr}")
            raise

    def build_project(self):
        """
        Build the project and verify the build was successful.
        
        This method:
        1. Verifies JDK compatibility
        2. Cleans the project
        3. Downloads dependencies
        4. Compiles source files
        5. Prepares test environment
        6. Verifies build output
        
        Raises:
            Exception: If build fails or verification fails
        """
        logger.info("Building project...")
        
        # Check JUnit information
        junit_version = self.maven_config.get_junit_version()
        if junit_version:
            logger.info(f"Project uses JUnit version: {junit_version}")
        else:
            logger.info("No JUnit version specified in POM file")
            
        missing_deps = self.maven_config.get_missing_junit_dependencies()
        if missing_deps:
            logger.info(f"Missing JUnit dependencies: {', '.join(dep['artifactId'] for dep in missing_deps)}")
        else:
            logger.info("All required JUnit dependencies are present")
        
        # Verify JDK compatibility
        is_compatible, required_version = self._verify_jdk_compatibility()
        if not is_compatible:
            error_msg = (
                f"JDK version mismatch!\n"
                f"Required version: Java {required_version}\n"
                f"Please install the correct JDK version and ensure it's in your PATH.\n"
                f"You can download it from: https://adoptium.net/ or use SDKMAN (https://sdkman.io/)\n"
            )
            logger.error(error_msg)
            raise SystemExit(error_msg)
        
        if self.required_jdk_version and not self.java_home:
            logger.warning(f"Required JDK {self.required_jdk_version} not found. Please install it and try again.")
        
        # Log JAVA_HOME once at the start of the build
        if self.java_home:
            logger.info(f"Using JAVA_HOME={self.java_home} for build.")
        
        # First, try to clean the project
        try:
            self._run_maven_command(f"{self.mvn_cmd} clean")
        except Exception as e:
            logger.warning(f"Clean failed, continuing with build: {str(e)}")
        
        # Download dependencies
        try:
            logger.info("Downloading dependencies...")
            self._run_maven_command(f"{self.mvn_cmd} dependency:resolve")
            logger.info("Dependencies downloaded successfully!")
        except Exception as e:
            logger.error(f"Failed to download dependencies: {str(e)}")
            raise
        
        # Compile source files
        try:
            logger.info("Compiling source files...")
            result = self._run_maven_command(f"{self.mvn_cmd} compile")
            logger.info("Source files compiled successfully!")
        except Exception as e:
            logger.error(f"Failed to compile source files: {str(e)}")
            raise
        
        # Prepare test environment
        try:
            logger.info("Preparing test environment...")
            self._run_maven_command(f"{self.mvn_cmd} test-compile")
            logger.info("Test environment prepared successfully!")
        except Exception as e:
            logger.error(f"Failed to prepare test environment: {str(e)}")
            raise
        
        # Verify the build output
        target_dir = self.repo_path / "target"
        if not target_dir.exists():
            raise Exception("Target directory not found after build")
            
        # Check for test reports (expected to be missing since we skip tests)
        test_reports_dir = target_dir / "surefire-reports"
        if not test_reports_dir.exists():
            logger.info("No test reports found (tests were skipped)")
            
        # Check for JaCoCo reports (expected to be missing since we skip tests)
        jacoco_reports_dir = target_dir / "site" / "jacoco"
        if not jacoco_reports_dir.exists():
            logger.info("No JaCoCo reports found (tests were skipped)") 