import re
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
import xml.etree.ElementTree as ET
from config import test_config

# Configure logging to only show errors
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class MavenConfig:
    """Manages Maven project configuration."""
    
    def __init__(self, repo_path: Path):
        """
        Initialize the Maven configuration manager.
        
        Args:
            repo_path: Path to the repository root
        """
        self.repo_path = repo_path
        self.pom_path = repo_path / 'pom.xml'
        self._tree = None
        self._root = None
        self.added_dependencies = []  # Track dependencies we actually add
        self._junit_version = None  # Cache for JUnit version
        self._detected_dependencies = {}  # Cache for detected dependencies
        
    def _load_pom(self):
        """Load the POM file if not already loaded."""
        if self._tree is None and self.pom_path.exists():
            try:
                self._tree = ET.parse(self.pom_path)
                self._root = self._tree.getroot()
                # Add namespace mapping
                self._ns = {'': 'http://maven.apache.org/POM/4.0.0'}
            except Exception as e:
                logger.error(f"Failed to parse POM file: {str(e)}")
                self._tree = None
                self._root = None
                
    def _find_element(self, path: str) -> Optional[ET.Element]:
        """
        Find an element in the POM file using XPath.
        
        Args:
            path: XPath expression to find the element
            
        Returns:
            The found element or None if not found
        """
        self._load_pom()
        if self._root is None:
            logger.error("POM file not loaded or invalid.")
            return None
            
        # Use default namespace
        path = path.replace('mvn:', '')
        
        try:
            # Register the namespace for XPath
            ET.register_namespace('', 'http://maven.apache.org/POM/4.0.0')
            
            # Find the element using the default namespace
            element = self._root.find(path, self._ns)
            return element
        except Exception as e:
            logger.error(f"Failed to find element {path}: {str(e)}")
            return None
            
    def get_java_version(self) -> Optional[str]:
        """
        Get the Java version from the POM file.
        
        Returns:
            Java version if found, None otherwise
        """
        self._load_pom()
        if self._root is None:
            logger.error("POM file not loaded or invalid.")
            return None

        # Try java.version in properties first (most common format)
        properties = self._root.find('.//properties', self._ns)
        if properties is not None:
            java_version = properties.find('java.version', self._ns)
            if java_version is not None and java_version.text:
                return java_version.text

        # Try jdk.version (alternative format)
        jdk_version = self._root.find('.//properties/jdk.version', self._ns)
        if jdk_version is not None and jdk_version.text:
            return jdk_version.text

        # Try maven.compiler.release (newer format)
        release = self._root.find('.//properties/maven.compiler.release', self._ns)
        if release is not None and release.text:
            return release.text

        # Try maven.compiler.source (older format)
        source = self._root.find('.//properties/maven.compiler.source', self._ns)
        if source is not None and source.text:
            return source.text
            
        # Try maven.compiler.target as fallback
        target = self._root.find('.//properties/maven.compiler.target', self._ns)
        if target is not None and target.text:
            return target.text

        # Try jdkTarget (alternative format)
        jdk_target = self._root.find('.//properties/jdkTarget', self._ns)
        if jdk_target is not None and jdk_target.text:
            return jdk_target.text

        # Try javadocSource (alternative format)
        javadoc_source = self._root.find('.//properties/javadocSource', self._ns)
        if javadoc_source is not None and javadoc_source.text:
            return javadoc_source.text
            
        # Try compiler plugin configuration
        plugins = self._root.find('.//plugins', self._ns)
        if plugins is not None:
            for plugin in plugins.findall('plugin', self._ns):
                artifact_id = plugin.find('artifactId', self._ns)
                if artifact_id is not None and artifact_id.text == 'maven-compiler-plugin':
                    config = plugin.find('configuration', self._ns)
                    if config is not None:
                        source = config.find('source', self._ns)
                        if source is not None and source.text:
                            return source.text
                            
                        target = config.find('target', self._ns)
                        if target is not None and target.text:
                            return target.text
                
        # If no version is detected, use Java 11 as default since it's a modern LTS version
        # with good compatibility and support

        return "11"
        
    def get_dependencies(self) -> List[Dict[str, Any]]:
        """
        Get all dependencies from the POM file.
        
        Returns:
            List of dependencies with their groupId, artifactId, and version
        """
        dependencies = []
        deps_elem = self._find_element('.//dependencies')
        if deps_elem is not None:
            for dep in deps_elem.findall('dependency', self._ns):
                group_id = dep.find('groupId', self._ns)
                artifact_id = dep.find('artifactId', self._ns)
                version = dep.find('version', self._ns)
                
                if group_id is not None and artifact_id is not None:
                    dep_info = {
                        'groupId': group_id.text,
                        'artifactId': artifact_id.text,
                        'version': version.text if version is not None else None
                    }
                    dependencies.append(dep_info)
                    
        return dependencies
        
    def has_junit_dependency(self) -> bool:
        """
        Check if the project has JUnit dependencies.
        
        Returns:
            True if JUnit dependencies are found, False otherwise
        """
        return self.get_junit_version() is not None
        
    def has_jacoco_plugin(self) -> bool:
        """
        Check if the project has JaCoCo plugin configured.
        
        Returns:
            True if JaCoCo plugin is found, False otherwise
        """
        # Check cache first
        cache_key = "jacoco-maven-plugin"
        if cache_key in self._detected_dependencies:
            return self._detected_dependencies[cache_key]

        self._load_pom()
        if self._root is None:
            logger.error("POM file not loaded or invalid")
            return False

        # Read the POM file as text
        try:
            with open(self.pom_path, 'r', encoding='utf-8') as f:
                pom_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read POM file: {str(e)}")
            return False

        # Define variations of the JaCoCo plugin identifier
        jacoco_variations = [
            'jacoco-maven-plugin',
            '<artifactId>jacoco-maven-plugin</artifactId>',
            '<dependencies:artifactId>jacoco-maven-plugin</dependencies:artifactId>',
            '"jacoco-maven-plugin"',
            "'jacoco-maven-plugin'",
            'jacoco',
            '<artifactId>jacoco</artifactId>',
            '<dependencies:artifactId>jacoco</dependencies:artifactId>',
            '"jacoco"',
            "'jacoco'"
        ]

        # Check for any variation
        for var in jacoco_variations:
            if var in pom_content:
                self._detected_dependencies[cache_key] = True
                return True

        self._detected_dependencies[cache_key] = False
        return False
        
    def has_sortpom_plugin(self) -> bool:
        """
        Check if the project has sortpom-maven-plugin configured.
        
        Returns:
            True if sortpom-maven-plugin is found, False otherwise
        """
        # Check cache first
        cache_key = "sortpom-maven-plugin"
        if cache_key in self._detected_dependencies:
            return self._detected_dependencies[cache_key]

        self._load_pom()
        if self._root is None:
            logger.error("POM file not loaded or invalid")
            return False

        # Read the POM file as text
        try:
            with open(self.pom_path, 'r', encoding='utf-8') as f:
                pom_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read POM file: {str(e)}")
            return False

        # Define variations of the sortpom plugin identifier
        sortpom_variations = [
            'sortpom-maven-plugin',
            '<artifactId>sortpom-maven-plugin</artifactId>',
            '<dependencies:artifactId>sortpom-maven-plugin</dependencies:artifactId>',
            '"sortpom-maven-plugin"',
            "'sortpom-maven-plugin'",
            'sortpom',
            '<artifactId>sortpom</artifactId>',
            '<dependencies:artifactId>sortpom</dependencies:artifactId>',
            '"sortpom"',
            "'sortpom'",
            'com.github.ekryd.sortpom'
        ]

        # Check for any variation
        for var in sortpom_variations:
            if var in pom_content:
                self._detected_dependencies[cache_key] = True
                return True

        self._detected_dependencies[cache_key] = False
        return False
        
    def configure_sortpom_plugin(self):
        """
        Configure the sortpom-maven-plugin to be skippable.
        Adds skip configuration to existing sortpom plugin.
        """
        if not self.has_sortpom_plugin():
            return
            
        self._load_pom()
        if self._root is None:
            logger.error("Cannot configure sortpom plugin: POM file not loaded")
            return
            
        # Find the sortpom plugin using the same approach as JaCoCo plugin
        # First check in the main build section
        plugins_elem = self._find_element('.//build/plugins')
        if plugins_elem is not None:
            for plugin in plugins_elem.findall('plugin', self._ns):
                group_id = plugin.find('groupId', self._ns)
                artifact_id = plugin.find('artifactId', self._ns)
                
                if (group_id is not None and group_id.text == 'com.github.ekryd.sortpom' and
                    artifact_id is not None and artifact_id.text == 'sortpom-maven-plugin'):
                    
                    # Check if skip configuration already exists
                    config = plugin.find('configuration', self._ns)
                    if config is None:
                        config = ET.SubElement(plugin, '{http://maven.apache.org/POM/4.0.0}configuration')
                    
                    skip_elem = config.find('skip', self._ns)
                    if skip_elem is None:
                        skip_elem = ET.SubElement(config, '{http://maven.apache.org/POM/4.0.0}skip')
                        skip_elem.text = '${sortpom.skip}'
                    
                    # Save changes
                    ET.indent(self._tree, space="    ")
                    self._tree.write(self.pom_path, encoding='utf-8', xml_declaration=True)
                    return
        
        # Also check in profiles
        profiles = self._root.findall('.//profile', self._ns)
        for profile in profiles:
            profile_plugins_elem = profile.find('.//plugins', self._ns)
            if profile_plugins_elem is not None:
                for plugin in profile_plugins_elem.findall('plugin', self._ns):
                    group_id = plugin.find('groupId', self._ns)
                    artifact_id = plugin.find('artifactId', self._ns)
                    
                    if (group_id is not None and group_id.text == 'com.github.ekryd.sortpom' and
                        artifact_id is not None and artifact_id.text == 'sortpom-maven-plugin'):
                        
                        # Check if skip configuration already exists
                        config = plugin.find('configuration', self._ns)
                        if config is None:
                            config = ET.SubElement(plugin, '{http://maven.apache.org/POM/4.0.0}configuration')
                        
                        skip_elem = config.find('skip', self._ns)
                        if skip_elem is None:
                            skip_elem = ET.SubElement(config, '{http://maven.apache.org/POM/4.0.0}skip')
                            skip_elem.text = '${sortpom.skip}'
                        
                        # Save changes
                        ET.indent(self._tree, space="    ")
                        self._tree.write(self.pom_path, encoding='utf-8', xml_declaration=True)
                        return
        
    def add_junit_dependency(self, version: str = '5.9.2'):
        """
        Add JUnit Jupiter dependencies to the POM file.
        
        Args:
            version: JUnit Jupiter version to use
        """
        self._load_pom()
        if self._root is None:
            logger.error("Cannot add JUnit dependency: POM file not loaded")
            return
            
        # Find or create dependencies section
        deps_elem = self._find_element('.//dependencies')
        if deps_elem is None:
            deps_elem = ET.SubElement(self._root, '{http://maven.apache.org/POM/4.0.0}dependencies')
            
        # Add JUnit Jupiter dependencies
        junit_deps = [
            {
                'groupId': 'org.junit.jupiter',
                'artifactId': 'junit-jupiter-api',
                'version': version,
                'scope': 'test'
            },
            {
                'groupId': 'org.junit.jupiter',
                'artifactId': 'junit-jupiter-engine',
                'version': version,
                'scope': 'test'
            }
        ]
        
        for dep in junit_deps:
            # Check if dependency already exists
            existing = False
            for existing_dep in deps_elem.findall('dependency', self._ns):
                group_id = existing_dep.find('groupId', self._ns)
                artifact_id = existing_dep.find('artifactId', self._ns)
                if (group_id is not None and group_id.text == dep['groupId'] and
                    artifact_id is not None and artifact_id.text == dep['artifactId']):
                    existing = True
                    break
            
            if not existing:
                dep_elem = ET.SubElement(deps_elem, '{http://maven.apache.org/POM/4.0.0}dependency')
                for key, value in dep.items():
                    elem = ET.SubElement(dep_elem, f'{{http://maven.apache.org/POM/4.0.0}}{key}')
                    elem.text = value
                self.added_dependencies.append(f"{dep['groupId']}:{dep['artifactId']}:{dep['version']}")
        
        # Save changes with proper indentation and default namespace
        ET.indent(self._tree, space="    ")
        self._tree.write(self.pom_path, encoding='utf-8', xml_declaration=True)
        
    def add_jacoco_plugin(self, version: str = '0.8.10'):
        """
        Add JaCoCo plugin to the POM file.
        
        Args:
            version: JaCoCo plugin version to use
        """
        self._load_pom()
        if self._root is None:
            logger.error("Cannot add JaCoCo plugin: POM file not loaded")
            return
            
        # Check if project already has working JaCoCo + Surefire integration
        if self.has_working_jacoco_surefire_integration():
            return
            
        # First, check if the project uses Surefire plugin
        uses_surefire = False
        plugins_elem = self._find_element('.//build/plugins')
        if plugins_elem is not None:
            for plugin in plugins_elem.findall('plugin', self._ns):
                artifact_id = plugin.find('artifactId', self._ns)
                if artifact_id is not None and artifact_id.text == 'maven-surefire-plugin':
                    uses_surefire = True
                    break
            
        # Find or create build section
        build_elem = self._find_element('.//build')
        if build_elem is None:
            build_elem = ET.SubElement(self._root, '{http://maven.apache.org/POM/4.0.0}build')
            
        # Find or create plugins section
        plugins_elem = build_elem.find('plugins', self._ns)
        if plugins_elem is None:
            plugins_elem = ET.SubElement(build_elem, '{http://maven.apache.org/POM/4.0.0}plugins')
            
        # Add JaCoCo plugin with appropriate configuration
        jacoco_plugin = {
            'groupId': 'org.jacoco',
            'artifactId': 'jacoco-maven-plugin',
            'version': version,
            'executions': [
                {
                    'id': 'prepare-agent',
                    'goals': {
                        'goal': 'prepare-agent'
                    }
                },
                {
                    'id': 'report',
                    'phase': 'test',
                    'goals': {
                        'goal': 'report'
                    }
                }
            ]
        }
        
        # Add propertyName configuration only for projects with Surefire
        if uses_surefire:
            jacoco_plugin['executions'][0]['configuration'] = {
                'propertyName': 'jacocoArgLine'
            }
        
        # Create plugin element
        plugin_elem = ET.SubElement(plugins_elem, '{http://maven.apache.org/POM/4.0.0}plugin')
        
        # Add basic plugin info
        for key, value in jacoco_plugin.items():
            if key != 'executions':
                elem = ET.SubElement(plugin_elem, f'{{http://maven.apache.org/POM/4.0.0}}{key}')
                elem.text = value
                
        # Add executions
        executions_elem = ET.SubElement(plugin_elem, '{http://maven.apache.org/POM/4.0.0}executions')
        for execution in jacoco_plugin['executions']:
            execution_elem = ET.SubElement(executions_elem, '{http://maven.apache.org/POM/4.0.0}execution')
            for key, value in execution.items():
                if key == 'goals':
                    goals_elem = ET.SubElement(execution_elem, '{http://maven.apache.org/POM/4.0.0}goals')
                    goal_elem = ET.SubElement(goals_elem, '{http://maven.apache.org/POM/4.0.0}goal')
                    goal_elem.text = value['goal']
                elif key == 'configuration':
                    # Add configuration element only for Surefire projects
                    config_elem = ET.SubElement(execution_elem, '{http://maven.apache.org/POM/4.0.0}configuration')
                    for config_key, config_value in value.items():
                        config_child = ET.SubElement(config_elem, f'{{http://maven.apache.org/POM/4.0.0}}{config_key}')
                        config_child.text = config_value
                else:
                    elem = ET.SubElement(execution_elem, f'{{http://maven.apache.org/POM/4.0.0}}{key}')
                    elem.text = value
        
        # Track the added plugin
        self.added_dependencies.append(f"{jacoco_plugin['groupId']}:{jacoco_plugin['artifactId']}:{version}")
        
        # Save changes with proper indentation and default namespace
        ET.indent(self._tree, space="    ")
        self._tree.write(self.pom_path, encoding='utf-8', xml_declaration=True)
        
    def _has_dependency(self, group_id: str, artifact_id: str) -> bool:
        """
        Check if a dependency exists in the POM file using fuzzy text search.
        
        Args:
            group_id: The group ID of the dependency
            artifact_id: The artifact ID of the dependency
            
        Returns:
            True if the dependency exists, False otherwise
        """
        # Check cache first
        cache_key = f"{group_id}:{artifact_id}"
        if cache_key in self._detected_dependencies:
            return self._detected_dependencies[cache_key]
            
        # Load POM if not already loaded
        self._load_pom()
        if self._root is None:
            return False
            
        # Find the main dependencies section
        deps_elem = self._find_element('.//dependencies')
        if deps_elem is None:
            return False
            
        # Convert the dependencies section to string for searching
        deps_content = ET.tostring(deps_elem, encoding='unicode')
        
        # Define variations to search for
        group_variations = [
            group_id,
            group_id.replace('.', ':'),  # Some POMs use : instead of .
        ]
        
        artifact_variations = [
            artifact_id,
            artifact_id.replace('-', ''),  # Some POMs omit hyphens
            artifact_id.replace('-', '.')  # Some POMs use dots instead of hyphens
        ]
        
        # Special cases for common dependencies
        if artifact_id == 'mockito-core':
            artifact_variations.extend(['mockito', 'mockito-inline'])
        elif artifact_id == 'assertj-core':
            artifact_variations.extend(['assertj', 'assertj'])
        elif 'powermock' in artifact_id:
            artifact_variations.extend(['powermock'])
        
        # Check for each variation
        for group_var in group_variations:
            for artifact_var in artifact_variations:
                # Look for the dependency in different formats
                patterns = [
                    # Exact namespaced format with all elements
                    f'<dependencies:dependency>.*?<dependencies:groupId>{group_var}</dependencies:groupId>.*?<dependencies:artifactId>{artifact_var}</dependencies:artifactId>.*?<dependencies:version>.*?</dependencies:version>.*?<dependencies:scope>.*?</dependencies:scope>',
                    # Namespaced format with optional elements
                    f'<dependencies:dependency>.*?<dependencies:groupId>{group_var}</dependencies:groupId>.*?<dependencies:artifactId>{artifact_var}</dependencies:artifactId>',
                    f'<dependencies:dependency>.*?<dependencies:artifactId>{artifact_var}</dependencies:artifactId>.*?<dependencies:groupId>{group_var}</dependencies:groupId>',
                    # Regular XML tags with optional version
                    f'<groupId>{group_var}</groupId>.*?<artifactId>{artifact_var}</artifactId>.*?(?:<version>.*?</version>)?',
                    f'<artifactId>{artifact_var}</artifactId>.*?<groupId>{group_var}</groupId>.*?(?:<version>.*?</version>)?',
                    # Namespaced XML tags with optional version
                    f'<dependencies:groupId>{group_var}</dependencies:groupId>.*?<dependencies:artifactId>{artifact_var}</dependencies:artifactId>.*?(?:<dependencies:version>.*?</dependencies:version>)?',
                    f'<dependencies:artifactId>{artifact_var}</dependencies:artifactId>.*?<dependencies:groupId>{group_var}</dependencies:groupId>.*?(?:<dependencies:version>.*?</dependencies:version>)?',
                    # Dependency declarations with optional version
                    f'<dependency>.*?{group_var}.*?{artifact_var}.*?(?:<version>.*?</version>)?',
                    f'<dependency>.*?{artifact_var}.*?{group_var}.*?(?:<version>.*?</version>)?',
                    f'<dependencies:dependency>.*?{group_var}.*?{artifact_var}.*?(?:<dependencies:version>.*?</dependencies:version>)?',
                    f'<dependencies:dependency>.*?{artifact_var}.*?{group_var}.*?(?:<dependencies:version>.*?</dependencies:version>)?'
                ]
                
                for pattern in patterns:
                    if re.search(pattern, deps_content, re.DOTALL | re.IGNORECASE):
                        self._detected_dependencies[cache_key] = True
                        return True
                    
        self._detected_dependencies[cache_key] = False
        return False

    def add_test_dependencies(self):
        """
        Add test dependencies (Mockito, AssertJ, PowerMock) to the POM file.
        The dependencies added depend on whether the project uses JUnit 4 or 5.
        """
        self._load_pom()
        if self._root is None:
            logger.error("Cannot add test dependencies: POM file not loaded")
            return
            
        # Find or create the main dependencies section
        # First try to find the root-level dependencies section
        deps_elem = self._root.find('./dependencies', self._ns)
        
        # If not found, create it
        if deps_elem is None:
            deps_elem = ET.SubElement(self._root, '{http://maven.apache.org/POM/4.0.0}dependencies')
            
        # Get JUnit version to determine which dependencies to add
        junit_version = self.get_junit_version()
        
        # Get Java version to determine Mockito version
        java_version = self.get_java_version()
        # Handle both "1.8" and "8" formats for Java 8
        mockito_version = '3.12.4' if java_version in ['8', '1.8'] else '5.11.0'
            
        # Common test dependencies for both JUnit 4 and 5
        test_deps = [
            {
                'groupId': 'org.mockito',
                'artifactId': 'mockito-core',
                'version': mockito_version,
                'scope': 'test'
            },
            {
                'groupId': 'org.assertj',
                'artifactId': 'assertj-core',
                'version': '3.25.3',
                'scope': 'test'
            }
        ]
        
        # Add version-specific dependencies
        if junit_version == '5':
            test_deps.append({
                'groupId': 'org.mockito',
                'artifactId': 'mockito-junit-jupiter',
                'version': mockito_version,  # Use the same version as mockito-core
                'scope': 'test'
            })
        elif junit_version == '4':
            test_deps.extend([
                {
                    'groupId': 'org.powermock',
                    'artifactId': 'powermock-api-mockito2',
                    'version': '2.0.9',
                    'scope': 'test'
                },
                {
                    'groupId': 'org.powermock',
                    'artifactId': 'powermock-module-junit4',
                    'version': '2.0.9',
                    'scope': 'test'
                }
            ])
        
        # Add each dependency if not already present
        for dep in test_deps:
            if not self._has_dependency(dep['groupId'], dep['artifactId']):
                dep_elem = ET.SubElement(deps_elem, '{http://maven.apache.org/POM/4.0.0}dependency')
                for key, value in dep.items():
                    elem = ET.SubElement(dep_elem, f'{{http://maven.apache.org/POM/4.0.0}}{key}')
                    elem.text = value
                self.added_dependencies.append(f"{dep['groupId']}:{dep['artifactId']}:{dep['version']}")
        
        # Save changes with proper indentation and default namespace
        ET.indent(self._tree, space="    ")
        self._tree.write(self.pom_path, encoding='utf-8', xml_declaration=True)

    def configure(self):
        """
        Configure the Maven project by adding necessary dependencies and plugins.
        This method ensures the project has JUnit, Mockito, AssertJ, PowerMock, and JaCoCo configured.
        """
        # Add JUnit dependencies if missing
        if not self.has_junit_dependency():
            self.add_junit_dependency()
            
        # Add test dependencies (Mockito, AssertJ, PowerMock)
        self.add_test_dependencies()
        
        # Configure sortpom plugin to be skippable
        self.configure_sortpom_plugin()
            
        # Add JaCoCo plugin if missing
        if not self.has_jacoco_plugin():
            self.add_jacoco_plugin()
        else:
            # Update existing JaCoCo plugin configuration if needed
            self.update_jacoco_plugin_configuration()
        
        # Update Surefire plugin configuration to work with JaCoCo
        self.update_surefire_plugin_configuration()

    def get_junit_version(self) -> Optional[str]:
        """
        Get the JUnit version from the POM file.
        
        Returns:
            '4' or '5' if JUnit is found, None otherwise
        """
        # Return cached version if available
        if self._junit_version is not None:
            return self._junit_version

        self._load_pom()
        if self._root is None:
            logger.error("POM file not loaded or invalid.")
            return None
        
        # First check properties for junit-jupiter.version
        properties = self._root.find('.//properties', self._ns)
        if properties is not None:
            version_prop = properties.find('junit-jupiter.version', self._ns)
            if version_prop is not None and version_prop.text:
                self._junit_version = '5'  # Cache the major version
                test_config.set_junit_version('5')  # Update global config
                return '5'

        # Check junit-bom version in dependencyManagement
        bom = self._root.find('.//dependencyManagement//dependency[artifactId="junit-bom"]/version', self._ns)
        if bom is not None and bom.text:
            self._junit_version = '5'  # Cache the major version
            test_config.set_junit_version('5')  # Update global config
            return '5'

        # Check direct dependencies for JUnit
        dependencies = self._root.find('./dependencies', self._ns)
        if dependencies is not None:
            for dep in dependencies.findall('dependency', self._ns):
                group_id = dep.find('groupId', self._ns)
                artifact_id = dep.find('artifactId', self._ns)
                
                if (group_id is not None and group_id.text and 
                    artifact_id is not None and artifact_id.text):
                    
                    # Check for Spring Boot Starter Test (includes JUnit 5)
                    if (group_id.text == 'org.springframework.boot' and 
                        artifact_id.text == 'spring-boot-starter-test'):
                        # Spring Boot 3.0.0+ uses JUnit 5 by default
                        # Check the parent version to determine JUnit version
                        parent = self._root.find('./parent', self._ns)
                        if parent is not None:
                            parent_version = parent.find('version', self._ns)
                            if parent_version is not None and parent_version.text:
                                # Spring Boot 3.0.0+ uses JUnit 5
                                if parent_version.text.startswith('3.'):
                                    self._junit_version = '5'  # Cache the major version
                                    test_config.set_junit_version('5')  # Update global config
                                    return '5'
                                # Spring Boot 2.x uses JUnit 4
                                elif parent_version.text.startswith('2.'):
                                    self._junit_version = '4'  # Cache the major version
                                    test_config.set_junit_version('4')  # Update global config
                                    return '4'
                    
                    # Check for JUnit 5 dependencies
                    if (group_id.text == 'org.junit.jupiter' and 
                        (artifact_id.text == 'junit-jupiter' or 
                         artifact_id.text == 'junit-jupiter-api' or
                         artifact_id.text == 'junit-jupiter-engine')):
                        self._junit_version = '5'  # Cache the major version
                        test_config.set_junit_version('5')  # Update global config
                        return '5'
                    # Check for JUnit 4 dependencies
                    elif (group_id.text == 'junit' and 
                          artifact_id.text == 'junit'):
                        self._junit_version = '4'  # Cache the major version
                        test_config.set_junit_version('4')  # Update global config
                        return '4'
                    
                    # Check for JUnit in exclusions (indicates JUnit 4 usage)
                    exclusions = dep.find('exclusions', self._ns)
                    if exclusions is not None:
                        for exclusion in exclusions.findall('exclusion', self._ns):
                            excl_group_id = exclusion.find('groupId', self._ns)
                            excl_artifact_id = exclusion.find('artifactId', self._ns)
                            
                            if (excl_group_id is not None and excl_group_id.text == 'junit' and
                                excl_artifact_id is not None and excl_artifact_id.text == 'junit'):
                                # Found JUnit 4 in exclusions, which means the project is using JUnit 4
                                self._junit_version = '4'  # Cache the major version
                                test_config.set_junit_version('4')  # Update global config
                                return '4'

        logger.warning("No JUnit version found in POM file.")
        return None

    def get_missing_junit_dependencies(self) -> List[Dict[str, str]]:
        """
        Get a list of missing JUnit dependencies that should be added.
        
        Returns:
            List of dependencies with their groupId, artifactId, and version
        """
        self._load_pom()
        if self._root is None:
            logger.error("POM file not loaded or invalid.")
            return []

        # Get current JUnit version
        junit_version = self.get_junit_version()
        if not junit_version:
            junit_version = "5.9.2"  # Default version if not found

        # Required JUnit dependencies
        required_deps = [
            {
                'groupId': 'org.junit.jupiter',
                'artifactId': 'junit-jupiter-api',
                'version': junit_version,
                'scope': 'test'
            },
            {
                'groupId': 'org.junit.jupiter',
                'artifactId': 'junit-jupiter-engine',
                'version': junit_version,
                'scope': 'test'
            },
            {
                'groupId': 'org.junit.jupiter',
                'artifactId': 'junit-jupiter-params',
                'version': junit_version,
                'scope': 'test'
            }
        ]

        # Check which dependencies are missing
        missing_deps = []
        for required in required_deps:
            found = False
            for dep in self._root.findall('.//{http://maven.apache.org/POM/4.0.0}dependencies/{http://maven.apache.org/POM/4.0.0}dependency'):
                group_id = dep.find('{http://maven.apache.org/POM/4.0.0}groupId')
                artifact_id = dep.find('{http://maven.apache.org/POM/4.0.0}artifactId')
                
                if (group_id is not None and group_id.text == required['groupId'] and
                    artifact_id is not None and artifact_id.text == required['artifactId']):
                    found = True
                    break
            
            if not found:
                missing_deps.append(required)

        return missing_deps

    def update_jacoco_plugin_configuration(self):
        """
        Update existing JaCoCo plugin configuration based on whether the project uses Surefire.
        For projects with Surefire: add propertyName=jacocoArgLine
        For projects without Surefire: use default JaCoCo configuration (no propertyName)
        """
        self._load_pom()
        if self._root is None:
            logger.error("Cannot update JaCoCo plugin: POM file not loaded")
            return
            
        # Check if project already has working JaCoCo + Surefire integration
        if self.has_working_jacoco_surefire_integration():
            return
            
        # First, check if the project uses Surefire plugin
        uses_surefire = False
        plugins_elem = self._find_element('.//build/plugins')
        if plugins_elem is not None:
            for plugin in plugins_elem.findall('plugin', self._ns):
                artifact_id = plugin.find('artifactId', self._ns)
                if artifact_id is not None and artifact_id.text == 'maven-surefire-plugin':
                    uses_surefire = True
                    break
        
        # Find the JaCoCo plugin
        if plugins_elem is None:
            logger.debug("No plugins section found, nothing to update")
            return
            
        # Look for JaCoCo plugin
        for plugin in plugins_elem.findall('plugin', self._ns):
            artifact_id = plugin.find('artifactId', self._ns)
            if artifact_id is not None and artifact_id.text == 'jacoco-maven-plugin':
                # Found JaCoCo plugin, check if it needs updating
                executions_elem = plugin.find('executions', self._ns)
                if executions_elem is not None:
                    for execution in executions_elem.findall('execution', self._ns):
                        execution_id = execution.find('id', self._ns)
                        if execution_id is not None and execution_id.text == 'prepare-agent':
                            config_elem = execution.find('configuration', self._ns)
                            
                            if uses_surefire:
                                # Project uses Surefire - add propertyName=jacocoArgLine
                                if config_elem is None:
                                    # No configuration, add it
                                    config_elem = ET.SubElement(execution, '{http://maven.apache.org/POM/4.0.0}configuration')
                                    property_name_elem = ET.SubElement(config_elem, '{http://maven.apache.org/POM/4.0.0}propertyName')
                                    property_name_elem.text = 'jacocoArgLine'
                                else:
                                    # Configuration exists, check if propertyName is there
                                    property_name_elem = config_elem.find('propertyName', self._ns)
                                    if property_name_elem is None:
                                        # Add propertyName to existing configuration
                                        property_name_elem = ET.SubElement(config_elem, '{http://maven.apache.org/POM/4.0.0}propertyName')
                                        property_name_elem.text = 'jacocoArgLine'
                                    else:
                                        logger.debug("JaCoCo plugin already has propertyName configuration")
                            else:
                                # Project doesn't use Surefire - remove propertyName if it exists
                                if config_elem is not None:
                                    property_name_elem = config_elem.find('propertyName', self._ns)
                                    if property_name_elem is not None:
                                        config_elem.remove(property_name_elem)
                                        
                                        # If configuration is now empty, remove it entirely
                                        if len(config_elem) == 0:
                                            execution.remove(config_elem)
                                    else:
                                        logger.debug("JaCoCo plugin already has correct configuration for non-Surefire project")
                                else:
                                    logger.debug("JaCoCo plugin already has correct configuration for non-Surefire project")
                            
                            # Save changes
                            ET.indent(self._tree, space="    ")
                            self._tree.write(self.pom_path, encoding='utf-8', xml_declaration=True)
                            return
                            
        logger.debug("No JaCoCo plugin found to update")

    def update_surefire_plugin_configuration(self):
        """
        Update maven-surefire-plugin configuration to include jacocoArgLine in argLine.
        This ensures the JaCoCo agent is passed to the test JVM.
        Only updates existing Surefire plugins, does not add new ones.
        """
        self._load_pom()
        if self._root is None:
            logger.error("Cannot update Surefire plugin: POM file not loaded")
            return
            
        # Check if project already has working JaCoCo + Surefire integration
        if self.has_working_jacoco_surefire_integration():
            return
            
        # Find the plugins section
        plugins_elem = self._find_element('.//build/plugins')
        if plugins_elem is None:
            logger.debug("No plugins section found, nothing to update")
            return
            
        # Look for maven-surefire-plugin
        for plugin in plugins_elem.findall('plugin', self._ns):
            artifact_id = plugin.find('artifactId', self._ns)
            if artifact_id is not None and artifact_id.text == 'maven-surefire-plugin':
                # Found Surefire plugin, check if it needs updating
                config_elem = plugin.find('configuration', self._ns)
                if config_elem is None:
                    # No configuration, create it
                    config_elem = ET.SubElement(plugin, '{http://maven.apache.org/POM/4.0.0}configuration')
                    arg_line_elem = ET.SubElement(config_elem, '{http://maven.apache.org/POM/4.0.0}argLine')
                    arg_line_elem.text = '${jacocoArgLine}'
                else:
                    # Configuration exists, check if argLine is there
                    arg_line_elem = config_elem.find('argLine', self._ns)
                    if arg_line_elem is None:
                        # No argLine, add it
                        arg_line_elem = ET.SubElement(config_elem, '{http://maven.apache.org/POM/4.0.0}argLine')
                        arg_line_elem.text = '${jacocoArgLine}'
                    else:
                        # argLine exists, check if it includes jacocoArgLine
                        current_arg_line = arg_line_elem.text or ""
                        if '${jacocoArgLine}' not in current_arg_line:
                            # Add jacocoArgLine to the beginning of existing argLine
                            if current_arg_line.strip():
                                new_arg_line = f"${{jacocoArgLine}} {current_arg_line}"
                            else:
                                new_arg_line = '${jacocoArgLine}'
                            arg_line_elem.text = new_arg_line
                        else:
                            logger.debug("Surefire plugin already has jacocoArgLine in argLine")
                
                # Save changes
                ET.indent(self._tree, space="    ")
                self._tree.write(self.pom_path, encoding='utf-8', xml_declaration=True)
                return
        
        # No Surefire plugin found, that's fine - just log it
        logger.debug("No maven-surefire-plugin found - using vanilla JaCoCo plugin only")

    def _detect_jacoco_pattern(self) -> str:
        """
        Detect which JaCoCo pattern the project uses using fuzzy text search:
        - 'default': No propertyName (sets 'argLine')
        - 'custom': Has propertyName="jacocoArgLine" (sets 'jacocoArgLine')
        - 'none': No JaCoCo plugin
        """
        self._load_pom()
        if self._root is None:
            return 'none'
            
        # Read the POM file as text for fuzzy searching
        try:
            with open(self.pom_path, 'r', encoding='utf-8') as f:
                pom_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read POM file: {str(e)}")
            return 'none'
        
        # Check if JaCoCo plugin exists
        jacoco_patterns = [
            'jacoco-maven-plugin',
            '<artifactId>jacoco-maven-plugin</artifactId>',
            'jacoco',
            '<artifactId>jacoco</artifactId>'
        ]
        
        has_jacoco = any(pattern in pom_content for pattern in jacoco_patterns)
        if not has_jacoco:
            return 'none'
        
        # Check for propertyName configuration using fuzzy search
        property_name_patterns = [
            '<propertyName>jacocoArgLine</propertyName>',
            'propertyName>jacocoArgLine<',
            'propertyName>jacocoArgLine</',
            'propertyName="jacocoArgLine"',
            "propertyName='jacocoArgLine'"
        ]
        
        has_property_name = any(pattern in pom_content for pattern in property_name_patterns)
        if has_property_name:
            return 'custom'
        else:
            return 'default'

    def _detect_surefire_pattern(self) -> str:
        """
        Detect which Surefire pattern the project uses using fuzzy text search:
        - 'argline': Uses @{argLine} or ${argLine}
        - 'jacocoargline': Uses ${jacocoArgLine}
        - 'none': No Surefire plugin
        """
        self._load_pom()
        if self._root is None:
            return 'none'
            
        # Read the POM file as text for fuzzy searching
        try:
            with open(self.pom_path, 'r', encoding='utf-8') as f:
                pom_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read POM file: {str(e)}")
            return 'none'
        
        # Check if Surefire plugin exists
        surefire_patterns = [
            'maven-surefire-plugin',
            '<artifactId>maven-surefire-plugin</artifactId>',
            'surefire',
            '<artifactId>surefire</artifactId>'
        ]
        
        has_surefire = any(pattern in pom_content for pattern in surefire_patterns)
        if not has_surefire:
            return 'none'
        
        # Look for argLine configuration using fuzzy search
        # First, find the argLine section
        argline_patterns = [
            '<argLine>',
            '<argLine ',
            'argLine>',
            'argLine='
        ]
        
        has_argline = any(pattern in pom_content for pattern in argline_patterns)
        if not has_argline:
            return 'none'
        
        # Check for specific patterns in the argLine content
        if '${jacocoArgLine}' in pom_content:
            return 'jacocoargline'
        elif '@{argLine}' in pom_content or '${argLine}' in pom_content:
            return 'argline'
        else:
            return 'none'

    def has_working_jacoco_surefire_integration(self) -> bool:
        """
        Check if the project already has a working JaCoCo + Surefire integration.
        Returns True if no modifications are needed.
        """
        jacoco_pattern = self._detect_jacoco_pattern()
        surefire_pattern = self._detect_surefire_pattern()
        
        # Pattern 1: JaCoCo without propertyName + Surefire with @{argLine}
        if jacoco_pattern == 'default' and surefire_pattern == 'argline':
            return True
            
        # Pattern 2: JaCoCo with propertyName="jacocoArgLine" + Surefire with ${jacocoArgLine}
        if jacoco_pattern == 'custom' and surefire_pattern == 'jacocoargline':
            return True
            
        # Pattern 3: JaCoCo (default) + Surefire (no argLine) → This is also working!
        if jacoco_pattern == 'default' and surefire_pattern == 'none':
            return True
            
        # No working integration detected
        return False 