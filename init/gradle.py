import re
import logging
from pathlib import Path
from typing import Optional, Tuple
from config import test_config

# Configure logging to only show errors
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

class GradleConfig:
    """Manages Gradle build file configuration and modifications."""
    
    def __init__(self, repo_path: Path):
        """
        Initialize the Gradle configuration manager.
        
        Args:
            repo_path: Path to the repository root
        """
        self.repo_path = repo_path
        self.gradle_file = self._find_gradle_file()
        self.added_dependencies = []  # Track dependencies we actually add
        self._detected_dependencies = {}  # Cache for detected dependencies
        
    def _find_gradle_file(self) -> Path:
        """
        Find the main Gradle build file in the repository.
        
        Returns:
            Path to the Gradle build file
            
        Raises:
            FileNotFoundError: If no Gradle build file is found
        """
        possible_names = ['build.gradle', 'build.gradle.kts']
        for name in possible_names:
            gradle_file = self.repo_path / name
            if gradle_file.exists():
                return gradle_file
        raise FileNotFoundError("No Gradle build file found in the repository")

    def _detect_mockito_version(self, content: str) -> Optional[str]:
        """
        Detect the version of Mockito being used.
        
        Args:
            content: The current content of the build.gradle file.
            
        Returns:
            '2' if Mockito 2.x is found, '4' if Mockito 4.x is found, None if no Mockito is found
        """
        # Patterns to match Mockito dependencies
        mockito_patterns = [
            # Standard format: testImplementation "org.mockito:mockito-core:version"
            r'(?:testImplementation|testCompile|implementation|compile)\s+[\'"]org\.mockito:mockito-(?:core|junit-jupiter):([^"\']+)[\'"]',
            # Group format: testCompile group: 'org.mockito', name: 'mockito-core', version: 'version'
            r'(?:testImplementation|testCompile|implementation|compile)\s+group:\s*[\'"]org\.mockito[\'"].*name:\s*[\'"]mockito-(?:core|junit-jupiter)[\'"].*version:\s*[\'"]([^"\']+)[\'"]'
        ]
        
        for pattern in mockito_patterns:
            match = re.search(pattern, content)
            if match:
                version = match.group(1)
                if version.startswith('2.'):
                    return '2'
                elif version.startswith('4.'):
                    return '4'
        return None

    def _detect_junit_version(self, content: str) -> Optional[str]:
        """
        Detect if JUnit is already configured and which version.
        
        Args:
            content: The current content of the build.gradle file.

        Returns:
            '4' or '5' if JUnit is detected, None otherwise
        """
        # First check if we have Mockito 2.x, which constrains us to JUnit 4
        mockito_version = self._detect_mockito_version(content)
        if mockito_version == '2':
            return '4'
            
        # Check for JUnit 5
        if re.search(r'junit-jupiter', content) or re.search(r'useJUnitPlatform\(\)', content):
            return '5'
            
        # Check for JUnit 4 in different formats
        junit4_patterns = [
            r'junit:junit:4',  # Standard format
            r"['\"]junit['\"]\..*4\\.\d+",  # String format
            r"group:\s*['\"]junit['\"].*version:\s*['\"]4\.",  # Group format
            r"name:\s*['\"]junit['\"].*version:\s*['\"]4\.",  # Name format
            r"testCompile.*junit.*4\.",  # testCompile format
            r"testImplementation.*junit.*4\.",  # testImplementation format
            r"implementation.*junit.*4\."  # implementation format
        ]
        
        for pattern in junit4_patterns:
            if re.search(pattern, content):
                return '4'
                
        return None

    def _detect_java_version(self, content: str) -> Optional[str]:
        """
        Detect the Java version from the Gradle file content.
        
        Args:
            content: The current content of the build.gradle file.

        Returns:
            Java version number if found, None otherwise
        """
        # Look for sourceCompatibility or targetCompatibility
        version_match = re.search(r'(?:source|target)Compatibility\s*=\s*["\']?(\d+(?:\.\d+)?)["\']?', content)
        if version_match:
            version = version_match.group(1)
            # Convert to major version if needed (e.g., 1.8 -> 8)
            if version.startswith('1.'):
                version = version.split('.')[1]
            return version
        return None

    def _has_apply_plugin(self, content: str) -> bool:
        return bool(re.search(r"apply plugin:", content))

    def _add_repositories(self, content: str) -> str:
        if 'repositories {' not in content:
            content += """
repositories {
    mavenCentral()
    maven { url 'https://repo.maven.apache.org/maven2/' }
    maven { url 'https://plugins.gradle.org/m2/' }
}
"""
        return content

    def _add_or_patch_plugins(self, content: str) -> str:
        """
        Add or patch plugins in the Gradle file.
        Only adds 'java' and 'jacoco' plugins if they don't exist.
        Preserves all existing plugins.
        """
        # Check if java and jacoco plugins are already present
        has_java = bool(re.search(r'id\s+[\'"]java[\'"]', content) or re.search(r"apply\s+plugin:\s*['\"]java['\"]", content))
        has_jacoco = bool(re.search(r'id\s+[\'"]jacoco[\'"]', content) or re.search(r"apply\s+plugin:\s*['\"]jacoco['\"]", content))

        # If both plugins are present, no need to modify
        if has_java and has_jacoco:
            return content

        # Check which plugin declaration style is being used
        uses_plugins_block = bool(re.search(r'plugins\s*\{', content))
        uses_apply_plugin = bool(re.search(r'apply\s+plugin:', content))

        # If using plugins block
        if uses_plugins_block:
            if not has_java or not has_jacoco:
                # Find the plugins block
                match = re.search(r'(plugins\s*\{.*?)\}', content, re.DOTALL)
                if match:
                    plugins_block = match.group(1)
                    # Add missing plugins
                    if not has_java:
                        plugins_block += "\n    id 'java'"
                    if not has_jacoco:
                        plugins_block += "\n    id 'jacoco'"
                    # Replace the old plugins block with the new one
                    content = content.replace(match.group(0), plugins_block + "\n}")
                else:
                    # If plugins block not found, create a new one
                    plugins_block = "plugins {\n"
                    if not has_java:
                        plugins_block += "    id 'java'\n"
                    if not has_jacoco:
                        plugins_block += "    id 'jacoco'\n"
                    plugins_block += "}\n\n"
                    content = plugins_block + content
        # If using apply plugin style
        else:
            plugins_to_add = []
            if not has_java:
                plugins_to_add.append("apply plugin: 'java'")
            if not has_jacoco:
                plugins_to_add.append("apply plugin: 'jacoco'")
            if plugins_to_add:
                content = "\n".join(plugins_to_add) + "\n\n" + content

        return content

    def _add_jacoco_config(self, content: str) -> str:
        # Add JaCoCo plugin if not present
        if 'jacoco' not in content:
            content += "\napply plugin: 'jacoco'\n"

        # Use the older, more compatible syntax for JaCoCo configuration
        jacoco_config = '''
jacoco {
    toolVersion = "0.8.10"
}

test {
    finalizedBy jacocoTestReport
}

jacocoTestReport {
    reports {
        xml.enabled = true
        html.enabled = true
    }
}
'''
        # Add jacoco configuration only if the jacoco block is not present AND jacocoTestReport block is not present
        if 'jacoco {' not in content and 'jacocoTestReport {' not in content:
            content += jacoco_config
            self.added_dependencies.append('org.jacoco:jacoco-maven-plugin:0.8.10')
        return content

    def _update_mockito_dependencies(self, content: str) -> str:
        """
        Update any existing Mockito dependencies to version 4.11.0.
        This should only be called when we're adding mockito-junit-jupiter.
        
        Args:
            content: The current content of the build.gradle file.
            
        Returns:
            The modified content with updated Mockito versions.
        """
        # Patterns to match different Mockito dependency formats
        mockito_patterns = [
            # Standard format: testImplementation "org.mockito:mockito-core:version"
            r'(testImplementation|testCompile|implementation|compile)\s+[\'"]org\.mockito:mockito-(?:core|junit-jupiter):[^"\']+[\'"]',
            # Group format: testCompile group: 'org.mockito', name: 'mockito-core', version: 'version'
            r'(testImplementation|testCompile|implementation|compile)\s+group:\s*[\'"]org\.mockito[\'"].*name:\s*[\'"]mockito-(?:core|junit-jupiter)[\'"].*version:\s*[\'"][^"\']+[\'"]'
        ]
        
        # Replace any existing Mockito dependencies with our version
        for pattern in mockito_patterns:
            content = re.sub(
                pattern,
                r'\1 "org.mockito:mockito-core:4.11.0"',
                content
            )
        
        return content

    def _add_junit_dependencies(self, content: str, version: str) -> str:
        """
        Add JUnit dependencies based on the version.
        
        Args:
            content: The current content of the build.gradle file.
            version: JUnit version ('4' or '5')
        
        Returns:
            The modified content of the build.gradle file.
        """
        # Update global config with the JUnit version we're using
        test_config.set_junit_version(version)
        logger.debug(f"Setting JUnit version to: {version}")
        
        # Only add dependencies if missing
        def has_dep(dep_name):
            # Check if we've already detected this dependency
            if dep_name in self._detected_dependencies:
                return self._detected_dependencies[dep_name]
            
            # Convert dependency string to artifact name
            artifact = dep_name.split(':')[1] if ':' in dep_name else dep_name
            
            # First check if the artifact exists in any format
            patterns = [
                # Standard format: testImplementation "org:artifact:version"
                rf'(?:testImplementation|testCompile|implementation|compile)\s+[\'"][^:]+:{artifact}[:"]',
                # Group format: testCompile group: 'org', name: 'artifact', version: 'version'
                rf'(?:testImplementation|testCompile|implementation|compile)\s+group:\s*[\'"][^\'"]+[\'"].*name:\s*[\'"]{artifact}[\'"]',
                # Name format: name: 'artifact'
                rf'name:\s*[\'"]{artifact}[\'"]',
                # Direct artifact reference: artifact
                rf'\b{artifact}\b'
            ]
            
            # If we find the artifact, check its version
            if any(re.search(pattern, content) for pattern in patterns):
                # Extract version from standard format
                version_match = re.search(rf'[\'"][^:]+:{artifact}:([\d\.]+)[\'"]', content)
                if version_match:
                    self._detected_dependencies[dep_name] = True
                    return True
                    
                # Extract version from group format
                version_match = re.search(rf'name:\s*[\'"]{artifact}[\'"].*version:\s*[\'"]([\d\.]+)[\'"]', content)
                if version_match:
                    self._detected_dependencies[dep_name] = True
                    return True
                    
                # If we found the artifact but couldn't determine version, assume it exists
                self._detected_dependencies[dep_name] = True
                return True
                
            self._detected_dependencies[dep_name] = False
            return False
        
        # Define dependencies in different formats
        junit4_formats = [
            'testImplementation "junit:junit:4.13.2"',
            "testCompile group: 'junit', name: 'junit', version: '4.13.2'"
        ]
        
        # Get Java version to determine Mockito version
        java_version = self._detect_java_version(content)
        # Handle both "1.8" and "8" formats for Java 8
        mockito_version = '3.12.4' if java_version in ['8', '1.8'] else '4.11.0'
        
        mockito4_formats = [
            f'testImplementation "org.mockito:mockito-core:{mockito_version}"',
            f"testCompile group: 'org.mockito', name: 'mockito-core', version: '{mockito_version}'"
        ]
        assertj_formats = [
            'testImplementation "org.assertj:assertj-core:3.11.1"',
            "testCompile group: 'org.assertj', name: 'assertj-core', version: '3.11.1'"
        ]
        junit5_formats = [
            'testImplementation "org.junit.jupiter:junit-jupiter-api:5.9.2"',
            'testRuntimeOnly "org.junit.jupiter:junit-jupiter-engine:5.9.2"',
            "testCompile group: 'org.junit.jupiter', name: 'junit-jupiter-api', version: '5.9.2'",
            "testRuntimeOnly group: 'org.junit.jupiter', name: 'junit-jupiter-engine', version: '5.9.2'"
        ]
        mockito5_formats = [
            f'testImplementation "org.mockito:mockito-junit-jupiter:{mockito_version}"',
            f"testCompile group: 'org.mockito', name: 'mockito-junit-jupiter', version: '{mockito_version}'"
        ]
        powermock_formats = [
            'testImplementation "org.powermock:powermock-api-mockito2:2.0.9"',
            'testImplementation "org.powermock:powermock-module-junit4:2.0.9"',
            "testCompile group: 'org.powermock', name: 'powermock-api-mockito2', version: '2.0.9'",
            "testCompile group: 'org.powermock', name: 'powermock-module-junit4', version: '2.0.9'"
        ]
        
        deps_to_add = []
        if version == '5':
            # For JUnit 5, add JUnit Jupiter dependencies if missing
            if not has_dep('junit-jupiter-api'): 
                deps_to_add.append(junit5_formats[0])  # Use standard format
                self.added_dependencies.append('org.junit.jupiter:junit-jupiter-api:5.9.2')
            if not has_dep('junit-jupiter-engine'): 
                deps_to_add.append(junit5_formats[1])  # Use standard format
                self.added_dependencies.append('org.junit.jupiter:junit-jupiter-engine:5.9.2')
            # Add Mockito JUnit Jupiter integration if missing
            if not has_dep('mockito-junit-jupiter'): 
                # First update any existing Mockito dependencies to our version
                content = self._update_mockito_dependencies(content)
                deps_to_add.append(mockito5_formats[0])  # Use standard format
                self.added_dependencies.append('org.mockito:mockito-junit-jupiter:4.11.0')
            # Add AssertJ if missing
            if not has_dep('assertj-core'): 
                deps_to_add.append(assertj_formats[0])  # Use standard format
                self.added_dependencies.append('org.assertj:assertj-core:3.11.1')
            # Add useJUnitPlatform() to test block if not present
            if 'useJUnitPlatform()' not in content:
                # Find the test block and add useJUnitPlatform() inside
                match = re.search(r'(test\s*\{.*?)\}', content, re.DOTALL)
                if match:
                    test_block_start = match.group(1)
                    content = content.replace(match.group(0), test_block_start + '\n    useJUnitPlatform()\n}')
                else:
                    # If test block not found, add a basic one with useJUnitPlatform()
                    content += """
test {
    useJUnitPlatform()
}
"""
        else:
            # For JUnit 4, add JUnit 4 dependencies if missing
            if not has_dep('junit'): 
                deps_to_add.append(junit4_formats[0])  # Use standard format
                self.added_dependencies.append('junit:junit:4.13.2')
            # Add Mockito core if missing
            if not has_dep('mockito-core'): 
                deps_to_add.append(mockito4_formats[0])  # Use standard format
                self.added_dependencies.append('org.mockito:mockito-core:4.11.0')
            # Add AssertJ if missing
            if not has_dep('assertj-core'): 
                deps_to_add.append(assertj_formats[0])  # Use standard format
                self.added_dependencies.append('org.assertj:assertj-core:3.11.1')
            # Add PowerMock dependencies if missing
            if not has_dep('powermock-api-mockito2'):
                deps_to_add.append(powermock_formats[0])  # Use standard format
                self.added_dependencies.append('org.powermock:powermock-api-mockito2:2.0.9')
            if not has_dep('powermock-module-junit4'):
                deps_to_add.append(powermock_formats[1])  # Use standard format
                self.added_dependencies.append('org.powermock:powermock-module-junit4:2.0.9')
        
        # Add dependencies to the dependencies block
        if deps_to_add:
            if 'dependencies {' in content:
                # Split content into blocks and find the main dependencies block
                blocks = re.split(r'(buildscript\s*\{[^}]*\}|dependencies\s*\{[^}]*\})', content, flags=re.DOTALL)
                main_deps_block = None
                main_deps_index = -1
                in_buildscript = False
                
                for i, block in enumerate(blocks):
                    if block.strip().startswith('buildscript {'):
                        in_buildscript = True
                        continue
                    elif block.strip().startswith('}'):
                        in_buildscript = False
                        continue
                    elif block.strip().startswith('dependencies {'):
                        if not in_buildscript:
                            main_deps_block = block
                            main_deps_index = i
                            break
                
                if main_deps_block:
                    # Split the block into lines and remove the closing brace
                    lines = main_deps_block.rstrip().split('\n')
                    # Remove the closing brace line
                    if lines and lines[-1].strip() == '}':
                        lines.pop()
                    
                    # Add new dependencies with proper indentation
                    for dep in deps_to_add:
                        lines.append('    ' + dep)
                    
                    # Add the closing brace
                    lines.append('}')
                    
                    # Join the lines back together
                    new_content = '\n'.join(lines)
                    blocks[main_deps_index] = new_content
                    content = ''.join(blocks)
                else:
                    # Fallback: create a new dependencies block
                    dependency_block_content = '\n'.join(f'    {dep}' for dep in deps_to_add)
                    content += f"""

dependencies {{
{dependency_block_content}
}}
"""
            else:
                # Create a new dependencies block
                dependency_block_content = '\n'.join(f'    {dep}' for dep in deps_to_add)
                content += f"""

dependencies {{
{dependency_block_content}
}}
"""
        
        return content

    def _add_missing_dependencies(self, content: str) -> str:
        """
        Add missing dependencies to the build.gradle file.
        
        Args:
            content: The current content of the build.gradle file.
            
        Returns:
            The modified content of the build.gradle file.
        """
        # Only add dependencies if missing
        def has_dep(dep_name):
            # Check if we've already detected this dependency
            if dep_name in self._detected_dependencies:
                return self._detected_dependencies[dep_name]
            
            # Convert dependency string to artifact name
            artifact = dep_name.split(':')[1] if ':' in dep_name else dep_name
            
            # First check if the artifact exists in any format
            patterns = [
                # Standard format: testImplementation "org:artifact:version"
                rf'(?:testImplementation|testCompile|implementation|compile)\s+[\'"][^:]+:{artifact}[:"]',
                # Group format: testCompile group: 'org', name: 'artifact', version: 'version'
                rf'(?:testImplementation|testCompile|implementation|compile)\s+group:\s*[\'"][^\'"]+[\'"].*name:\s*[\'"]{artifact}[\'"]',
                # Name format: name: 'artifact'
                rf'name:\s*[\'"]{artifact}[\'"]',
                # Direct artifact reference: artifact
                rf'\b{artifact}\b'
            ]
            
            # If we find the artifact, check its version
            if any(re.search(pattern, content) for pattern in patterns):
                # Extract version from standard format
                version_match = re.search(rf'[\'"][^:]+:{artifact}:([\d\.]+)[\'"]', content)
                if version_match:
                    self._detected_dependencies[dep_name] = True
                    return True
                    
                # Extract version from group format
                version_match = re.search(rf'name:\s*[\'"]{artifact}[\'"].*version:\s*[\'"]([\d\.]+)[\'"]', content)
                if version_match:
                    self._detected_dependencies[dep_name] = True
                    return True
                    
                # If we found the artifact but couldn't determine version, assume it exists
                self._detected_dependencies[dep_name] = True
                return True
                
            self._detected_dependencies[dep_name] = False
            return False
        
        # Define dependencies
        deps_to_add = []
        
        # Add Mockito if missing and not using JUnit 5
        if not has_dep('org.mockito:mockito-core') and not has_dep('org.mockito:mockito-junit-jupiter'):
            deps_to_add.append('testImplementation "org.mockito:mockito-core:4.11.0"')
        
        # Add dependencies to the dependencies block
        if deps_to_add:
            if 'dependencies {' in content:
                content = re.sub(r'(dependencies\s*\{)', r'\1\n    ' + '\n    '.join(deps_to_add), content, count=1)
            else:
                dependency_block_content = '\n'.join(f'    {dep}' for dep in deps_to_add)
                content += f"""

dependencies {{
{dependency_block_content}
}}
"""
        
        return content

    def _remove_testng_config(self, content: str) -> str:
        """
        Remove test.useTestNG() configuration from the Gradle file.
        
        Args:
            content: The current content of the build.gradle file.
            
        Returns:
            The modified content with test.useTestNG() removed.
        """
        # Remove the test.useTestNG() line
        content = re.sub(r'\s*test\.useTestNG\(\)\s*\n?', '\n', content)
        return content

    def configure(self):
        """
        Configure the Gradle file with necessary dependencies and settings.
        
        This method:
        1. Adds repositories
        2. Adds or patches plugins
        3. Detects and configures JUnit
        4. Adds JaCoCo configuration
        5. Detects Java version
        6. Adds missing dependencies
        """
        content = self.gradle_file.read_text()
        
        # 1. Add repositories
        content = self._add_repositories(content)
        
        # 2. Add or patch plugins
        content = self._add_or_patch_plugins(content)
        
        # 3. Detect JUnit version (needs to happen before adding dependencies)
        junit_version = self._detect_junit_version(content)
        
        # 4. Add JUnit dependencies
        if not junit_version:
            content = self._add_junit_dependencies(content, '5')
        else:
            content = self._add_junit_dependencies(content, junit_version)
            
        # 5. Add JaCoCo config
        content = self._add_jacoco_config(content)
        
        # 6. Add missing dependencies
        content = self._add_missing_dependencies(content)
        
        # 7. Detect Java version (using the final content for detection)
        java_version = self._detect_java_version(content)

        # 8. Remove test.useTestNG() configuration
        content = self._remove_testng_config(content)

        # Write the final configured content back to the file
        self.gradle_file.write_text(content) 