import re
import logging
from pathlib import Path
from typing import Optional, Tuple
import subprocess
import os
from .gradle import GradleConfig
from config import test_config

# Configure logging to only show errors
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

def _parse_java_major(version: str) -> int:
    """
    Parse the major version number from a Java version string.
    Handles both old format (1.8) and new format (8, 11, 17, etc.)
    """
    if version.startswith('1.'):
        # For old format (1.8), return the second number
        return int(version.split('.')[1])
    # For new format (8, 11, 17), return the first number
    return int(version.split('.')[0])

def _ensure_sdkman_installed() -> bool:
    sdkman_dir = Path.home() / '.sdkman'
    if sdkman_dir.exists():
        # Check if sdk command is available by sourcing init script and running 'sdk version'
        check_cmd = 'source "$HOME/.sdkman/bin/sdkman-init.sh" && sdk version'
        result = subprocess.run(['/bin/bash', '-c', check_cmd], capture_output=True, text=True, check=False)
        if result.returncode == 0:
             return True
        else:
             logger.warning(f"SDKMAN seems installed but not fully initialized. Output: {result.stderr}")
             # Attempt re-installation or proceed assuming it will be sourced later
             # For now, let's proceed assuming subsequent sourced commands will work
             return True # Assume installed even if version check fails
    
    install_cmd = 'curl -s "https://get.sdkman.io" | bash' # Simplified install command
    result = subprocess.run(install_cmd, shell=True, executable='/bin/bash')
    if result.returncode != 0:
        logger.error(f"Failed to install SDKMAN. Return code: {result.returncode}")
        return False
    # After installation, source the init script in a new subprocess to check
    check_cmd = 'source "$HOME/.sdkman/bin/sdkman-init.sh" && sdk version'
    result = subprocess.run(['/bin/bash', '-c', check_cmd], capture_output=True, text=True, check=False)
    if result.returncode == 0:
         return True
    else:
         logger.error(f"SDKMAN installed, but initialization check failed. Output: {result.stderr}")
         # This might happen in some environments, but subsequent calls might still work.
         return sdkman_dir.exists() # Return based on directory existence as a fallback

def _install_jdk_with_sdkman(version: str) -> Optional[str]:
    # Use the major version for SDKMAN (e.g., 8, 11, 17)
    major = _parse_java_major(version)
    
    # First, list available candidates to find the latest version
    list_cmd = f'source "$HOME/.sdkman/bin/sdkman-init.sh" && sdk list java'
    result = subprocess.run(list_cmd, shell=True, executable='/bin/bash', capture_output=True, text=True)
    
    # Find the latest version for the requested major version
    latest_version = None
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if f"| {major}." in line and "tem" in line:  # Look for Temurin versions
                parts = line.split("|")
                if len(parts) >= 4:
                    version_str = parts[2].strip()
                    if version_str and not "local" in line:  # Skip local versions
                        latest_version = f"{version_str}-tem"
    
    if not latest_version:
        logger.error(f"No suitable Java {major} Temurin version found in SDKMAN")
        return None
    
    # Install JDK using the found version
    install_cmd = f'source "$HOME/.sdkman/bin/sdkman-init.sh" && sdk install java {latest_version}'
    env = os.environ.copy()
    env['SDKMAN_AUTO_ANSWER'] = 'true'
    
    try:
        # Use Popen to get real-time output
        process = subprocess.Popen(
            install_cmd,
            shell=True,
            executable='/bin/bash',
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True
        )
        
        # Read output in real-time from both stdout and stderr
        import select
        import sys
        
        # Set up file descriptors for select
        stdout_fd = process.stdout.fileno()
        stderr_fd = process.stderr.fileno()
        
        # Read until process is done and all output is consumed
        while True:
            # Check if process is still running
            if process.poll() is not None:
                # Process has finished, read any remaining output
                for line in process.stdout:
                    pass
                for line in process.stderr:
                    pass
                break
                
            # Wait for output with a timeout
            readable, _, _ = select.select([stdout_fd, stderr_fd], [], [], 1.0)
            
            # Read from stdout
            if stdout_fd in readable:
                line = process.stdout.readline()
                if line:
                    pass
            
            # Read from stderr
            if stderr_fd in readable:
                line = process.stderr.readline()
                if line:
                    pass
        
        # Get the return code
        return_code = process.wait(timeout=300)  # 5 minute timeout
        
        if return_code != 0:
            error_output = process.stderr.read()
            logger.error(f"Failed to install JDK {major} with SDKMAN.")
            logger.error(f"Error output: {error_output}")
            return None
            
    except subprocess.TimeoutExpired:
        logger.error("JDK installation timed out after 5 minutes")
        process.kill()  # Ensure the process is terminated
        return None
    except Exception as e:
        logger.error(f"Unexpected error during installation: {str(e)}")
        return None
    
    # Get the installation path using sdk home
    home_cmd = f'source "$HOME/.sdkman/bin/sdkman-init.sh" && sdk home java {latest_version}'
    try:
        result = subprocess.run(
            home_cmd, 
            shell=True, 
            executable='/bin/bash', 
            capture_output=True, 
            text=True,
            timeout=30  # 30 second timeout for path retrieval
        )
    except subprocess.TimeoutExpired:
        logger.error("Getting JDK path timed out after 30 seconds")
        return None
    
    if result.returncode == 0:
        jdk_path = result.stdout.strip()
        if Path(jdk_path).exists():
            return jdk_path
        else:
            logger.error(f"JDK path {jdk_path} does not exist after installation")
    else:
        logger.error(f"Failed to get JDK path. Error: {result.stderr}")
        logger.error(f"Command output: {result.stdout}")
    
    return None

class GradleBuildManager:
    """Manages Gradle build configuration."""
    
    def __init__(self, repo_path: Path):
        """
        Initialize the Gradle build manager.
        
        Args:
            repo_path: Path to the repository root
        """
        self.repo_path = repo_path
        self.build_gradle_path = repo_path / 'build.gradle'
        self._junit_version = None  # Cache for JUnit version
        self.gradle_config = GradleConfig(repo_path)
        self.gradle_cmd = self._detect_gradle_command()
        self.required_jdk_version = self._detect_required_jdk_version()
        self.java_home = self._find_or_install_java_home(self.required_jdk_version)

    def _detect_gradle_command(self) -> str:
        gradlew = self.repo_path / 'gradlew'
        gradlew_bat = self.repo_path / 'gradlew.bat'
        if gradlew.exists() and os.access(gradlew, os.X_OK):
            return './gradlew'
        if gradlew_bat.exists():
            logger.warning("Only gradlew.bat (Windows wrapper) found. Falling back to system 'gradle'.")
        return 'gradle'

    def _detect_required_jdk_version(self) -> Optional[str]:
        # 1. Check build.gradle for sourceCompatibility/targetCompatibility
        gradle_file = self.repo_path / 'build.gradle'
        if gradle_file.exists():
            content = gradle_file.read_text()
            # sourceCompatibility = JavaVersion.VERSION_1_8.toString()
            match = re.search(r'sourceCompatibility\s*=\s*JavaVersion\.VERSION_(\d+)_(\d+)\.toString\(\)', content)
            if match:
                major = match.group(1)
                minor = match.group(2)
                version = f"{major}.{minor}"
                return version
            # sourceCompatibility = "11" or 11 or 1.8
            match = re.search(r'sourceCompatibility\s*=\s*["\']?(\d+(?:\.\d+)?)["\']?', content)
            if match:
                version = match.group(1)
                return version
            # java.toolchain.languageVersion
            match = re.search(r'languageVersion\s*=\s*JavaLanguageVersion.of\((\d+)\)', content)
            if match:
                version = match.group(1)
                return version
            # sourceCompatibility = JavaVersion.VERSION_11
            match = re.search(r'sourceCompatibility\s*=\s*JavaVersion\.VERSION_(\d+)', content)
            if match:
                version = match.group(1)
                return version
            # sourceCompatibility = JavaVersion (without version)
            if re.search(r'sourceCompatibility\s*=\s*JavaVersion\b', content):
                logger.warning("Found JavaVersion without specific version, defaulting to Java 11")
                return "11"
        # 2. Check gradle.properties for org.gradle.java.home
        gradle_props = self.repo_path / 'gradle.properties'
        if gradle_props.exists():
            content = gradle_props.read_text()
            match = re.search(r'org.gradle.java.home\s*=\s*(.*)', content)
            if match:
                # Try to extract version from path
                path = match.group(1).strip()
                version_match = re.search(r'jdk-?(\d+)', path)
                if version_match:
                    version = version_match.group(1)
                    return version
        # 3. .java-version or .sdkmanrc
        for fname in ['.java-version', '.sdkmanrc']:
            f = self.repo_path / fname
            if f.exists():
                version = f.read_text().strip()
                if version.isdigit():
                    return version
                # .sdkmanrc format: java=11.0.11.hs-adpt
                match = re.search(r'java=(\d+)', version)
                if match:
                    version = match.group(1)
                    return version
        
        # If no version is detected, use Java 11 as default since it's a modern LTS version
        # with good compatibility and support
        logger.warning("No Java version detected in project files, defaulting to Java 11")
        return "11"

    def _find_or_install_java_home(self, version: Optional[str]) -> Optional[str]:
        if not version:
            return None
        # 1. Check SDKMAN
        sdkman_dir = Path.home() / '.sdkman' / 'candidates' / 'java'
        if sdkman_dir.exists():
            for d in sdkman_dir.iterdir():
                if d.is_dir() and d.name.startswith(str(version)):
                    return str(d)
        # 2. Check common system locations
        for base in ['/usr/lib/jvm', '/usr/java', '/Library/Java/JavaVirtualMachines']:
            base_path = Path(base)
            if base_path.exists():
                for d in base_path.iterdir():
                    if d.is_dir() and str(version) in d.name:
                        java_home = d / 'Contents' / 'Home' if 'JavaVirtualMachines' in base else d
                        if (java_home / 'bin' / 'java').exists():
                            return str(java_home)
        # 3. Try to auto-install with SDKMAN (with user confirmation)
        from .build import _get_sdkman_identifier, _prompt_user_for_java_installation, _install_jdk_with_sdkman as _install_jdk_with_sdkman_build, _ensure_sdkman_installed as _ensure_sdkman_installed_build
        sdkman_identifier = _get_sdkman_identifier(version)
        if sdkman_identifier and _ensure_sdkman_installed_build():
            if _prompt_user_for_java_installation(version, sdkman_identifier):
                jdk_path = _install_jdk_with_sdkman_build(version)
                if jdk_path:
                    return jdk_path
            else:
                logger.warning(f"User declined Java installation. Cannot proceed without JDK {version}.")
        logger.warning(f"Could not find or install JDK {version} in SDKMAN or common system locations.")
        return None

    def _detect_jdk_version(self) -> Optional[str]:
        """
        Detect the version of the installed JDK.
        
        Returns:
            Optional[str]: The detected JDK version or None if not found
        """
        try:
            # Try using java -version first
            result = subprocess.run(
                ["java", "-version"],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.stderr:
                version_output = result.stderr
            else:
                version_output = result.stdout
                
            # Try to extract version from output
            version_match = re.search(r'version\s+"([^"]+)"', version_output)
            if version_match:
                version = version_match.group(1)
                return version
                
            # If java -version fails, try using JAVA_HOME
            java_home = os.environ.get("JAVA_HOME")
            if java_home:
                java_exe = os.path.join(java_home, "bin", "java")
                if os.path.exists(java_exe):
                    result = subprocess.run(
                        [java_exe, "-version"],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    if result.stderr:
                        version_output = result.stderr
                    else:
                        version_output = result.stdout
                        
                    version_match = re.search(r'version\s+"([^"]+)"', version_output)
                    if version_match:
                        version = version_match.group(1)
                        return version
                        
            logger.warning("Could not detect Java version from java -version or JAVA_HOME")
            return None
            
        except Exception as e:
            logger.error(f"Error detecting JDK version: {str(e)}")
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
            logger.error(f"JDK version mismatch. Required: {required_version} (major: {required_major}), Installed: {installed_version} (major: {installed_major})")
            
        return is_compatible, required_version

    def _run_gradle_command(self, command: str) -> subprocess.CompletedProcess:
        """
        Run a Gradle command and return the result.
        
        Args:
            command: The Gradle command to run
            
        Returns:
            CompletedProcess object with command output
            
        Raises:
            subprocess.CalledProcessError: If the command fails
        """
        env = os.environ.copy()
        if self.java_home:
            env['JAVA_HOME'] = self.java_home
            env['PATH'] = f"{self.java_home}/bin:" + env['PATH']
        
        # Add flags to skip checkstyle and tests
        if not command.endswith('checkstyleMain'):
            command = f"{command} -x checkstyleMain -x test"
            
        try:
            result = subprocess.run(
                command,
                cwd=self.repo_path,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
                env=env
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Gradle command failed: {e.stderr}")
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
        
        # First, try to clean the project
        try:
            self._run_gradle_command(f"{self.gradle_cmd} clean")
        except Exception as e:
            logger.warning(f"Clean failed, continuing with build: {str(e)}")
        
        # Download dependencies
        try:
            self._run_gradle_command(f"{self.gradle_cmd} dependencies")
        except Exception as e:
            logger.error(f"Failed to download dependencies: {str(e)}")
            raise
        
        # Compile source files
        try:
            self._run_gradle_command(f"{self.gradle_cmd} compileJava")
        except Exception as e:
            logger.error(f"Failed to compile source files: {str(e)}")
            raise
        
        # Prepare test environment
        try:
            logger.info("Preparing test environment...")
            self._run_gradle_command(f"{self.gradle_cmd} compileTestJava")
            logger.info("Test environment prepared successfully!")
        except Exception as e:
            logger.error(f"Failed to prepare test environment: {str(e)}")
            raise
        
        # Verify the build output
        build_dir = self.repo_path / "build"
        if not build_dir.exists():
            raise Exception("Build directory not found after build")
            
        # Check for test reports (expected to be missing since we skip tests)
        test_reports_dir = build_dir / "reports" / "tests"
        if not test_reports_dir.exists():
            pass
            
        # Check for JaCoCo reports (expected to be missing since we skip tests)
        jacoco_reports_dir = build_dir / "reports" / "jacoco"
        if not jacoco_reports_dir.exists():
            pass

    def get_junit_version(self) -> Optional[str]:
        """
        Get the JUnit version from the build.gradle file.
        
        Returns:
            '4' or '5' if JUnit is found, None otherwise
        """
        # Return cached version if available
        if self._junit_version is not None:
            return self._junit_version

        if not self.build_gradle_path.exists():
            logger.error("build.gradle file not found")
            return None

        try:
            with open(self.build_gradle_path, 'r') as f:
                content = f.read()
                
            # Look for JUnit version in dependencies
            junit_pattern = r"junit.*['\"]([0-9.]+)['\"]"
            match = re.search(junit_pattern, content)
            if match:
                version = match.group(1)
                # Convert to major version
                major_version = '5' if version.startswith('5') else '4'
                self._junit_version = major_version
                test_config.set_junit_version(major_version)  # Update global config
                return major_version
                
            # If no version found, use default
            default_version = '5'  # Default to JUnit 5
            self._junit_version = default_version
            test_config.set_junit_version(default_version)  # Update global config
            return default_version
            
        except Exception as e:
            logger.error(f"Error reading build.gradle: {str(e)}")
            return None 