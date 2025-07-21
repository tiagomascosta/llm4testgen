import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

class RepositoryAnalyzer:
    """Analyzes repository structure and requirements."""
    
    def __init__(self, repo_path: Path):
        """
        Initialize the repository analyzer.
        
        Args:
            repo_path: Path to the repository root
        """
        self.repo_path = repo_path
        
    def detect_java_version(self) -> Tuple[str, str]:
        """
        Detect Java version from build files and system.
        
        Returns:
            Tuple of (detected_version, available_versions)
        """
        # First try to detect from build files
        build_version = self._detect_from_build_files()
        
        # Then check system Java versions
        available_versions = self._get_available_java_versions()
        
        return build_version, available_versions
        
    def _detect_from_build_files(self) -> str:
        """Detect Java version from build files."""
        # Check Gradle properties
        gradle_props = self.repo_path / "gradle.properties"
        if gradle_props.exists():
            with open(gradle_props) as f:
                for line in f:
                    if "org.gradle.java.home" in line:
                        return line.split("=")[1].strip()
                        
        # Check Maven properties
        pom_xml = self.repo_path / "pom.xml"
        if pom_xml.exists():
            # TODO: Parse pom.xml for Java version
            pass
            
        return ""
        
    def _get_available_java_versions(self) -> str:
        """Get list of available Java versions on the system."""
        versions = []
        
        # Check update-java-alternatives
        try:
            result = subprocess.run(
                ["update-java-alternatives", "--list"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        path = parts[1]
                        name = Path(path).name
                        try:
                            java_bin = Path(path) / 'bin' / 'java'
                            if java_bin.exists():
                                result = subprocess.run(
                                    [str(java_bin), '-version'],
                                    stderr=subprocess.PIPE,
                                    text=True
                                )
                                version_match = re.search(r'version "([^"]+)"', result.stderr)
                                if version_match:
                                    versions.append(f"{path} ({version_match.group(1)})")
                        except Exception:
                            pass
        except FileNotFoundError:
            pass
            
        # Check common system locations
        for base in ['/usr/lib/jvm', '/usr/java', '/Library/Java/JavaVirtualMachines']:
            base_path = Path(base)
            if base_path.exists():
                for d in base_path.iterdir():
                    if d.is_dir():
                        # Get Java version
                        java_bin = d / 'bin' / 'java'
                        if java_bin.exists():
                            try:
                                result = subprocess.run(
                                    [str(java_bin), '-version'],
                                    stderr=subprocess.PIPE,
                                    text=True
                                )
                                version_match = re.search(r'version "([^"]+)"', result.stderr)
                                if version_match:
                                    versions.append(f"{d} ({version_match.group(1)})")
                            except Exception:
                                pass
                                
        # Check SDKMAN if available
        sdkman_dir = Path.home() / '.sdkman' / 'candidates' / 'java'
        if sdkman_dir.exists():
            for d in sdkman_dir.iterdir():
                if d.is_dir():
                    java_bin = d / 'bin' / 'java'
                    if java_bin.exists():
                        try:
                            result = subprocess.run(
                                [str(java_bin), '-version'],
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            version_match = re.search(r'version "([^"]+)"', result.stderr)
                            if version_match:
                                versions.append(f"{d} ({version_match.group(1)})")
                        except Exception:
                            pass
        
        if versions:
            return "\n".join(sorted(set(versions)))
        return "No Java versions found"
            
    def detect_build_system(self) -> str:
        """
        Detect the build system used (Gradle or Maven).
        
        Returns:
            'gradle' or 'maven'
        """
        if (self.repo_path / "build.gradle").exists() or (self.repo_path / "gradlew").exists():
            return "gradle"
        elif (self.repo_path / "pom.xml").exists():
            return "maven"
        else:
            raise ValueError("No supported build system detected")
            
    def analyze_dependencies(self) -> Dict[str, List[str]]:
        """
        Analyze build file for missing dependencies.
        
        Returns:
            Dictionary of missing dependencies by category
        """
        build_system = self.detect_build_system()
        missing_deps = {
            "junit": [],
            "jacoco": [],
            "other": []
        }
        
        if build_system == "gradle":
            build_file = self.repo_path / "build.gradle"
            if build_file.exists():
                with open(build_file) as f:
                    content = f.read()
                    if "junit" not in content.lower():
                        missing_deps["junit"].append("junit:junit:4.13.2")
                    if "jacoco" not in content.lower():
                        missing_deps["jacoco"].append("org.jacoco:jacoco-maven-plugin:0.8.7")
                        
        elif build_system == "maven":
            pom_file = self.repo_path / "pom.xml"
            if pom_file.exists():
                with open(pom_file) as f:
                    content = f.read()
                    if "junit" not in content.lower():
                        missing_deps["junit"].append("junit:junit:4.13.2")
                    if "jacoco" not in content.lower():
                        missing_deps["jacoco"].append("org.jacoco:jacoco-maven-plugin:0.8.7")
                        
        return missing_deps 