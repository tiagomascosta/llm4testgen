"""
Test scaffold generation module for creating test class templates with necessary imports.
"""

from typing import Dict, Set, List, Tuple, Any
import re
from pathlib import Path
from config import test_config
import logging
import javalang

logger = logging.getLogger(__name__)

# JUnit 4 imports
JUNIT4_IMPORTS = [
    "import static org.junit.Assert.*;",
    "import static org.mockito.Mockito.*;",
    "import static org.mockito.ArgumentMatchers.*;",
    "import org.junit.Test;",
    "import org.junit.Before;"
]

# JUnit 5 imports
JUNIT5_IMPORTS = [
    "import static org.assertj.core.api.Assertions.*;",
    "import static org.mockito.Mockito.*;",
    "import static org.mockito.ArgumentMatchers.*;",
    "import org.junit.jupiter.api.Test;",
    "import org.junit.jupiter.api.BeforeEach;",
    "import static org.junit.jupiter.api.Assertions.*;"
]

def get_test_directory(repo_path: Path, package: str) -> Path:
    """
    Get the test directory path for a given package.
    
    Args:
        repo_path: Root directory of the repository
        package: Package name
        
    Returns:
        Path to the test directory
    """
    # First check pom.xml for testSourceDirectory configuration
    pom_path = repo_path / 'pom.xml'
    if pom_path.exists():
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(pom_path)
            root = tree.getroot()
            
            # Add namespace mapping
            ns = {'': 'http://maven.apache.org/POM/4.0.0'}
            
            # Look for testSourceDirectory in build section
            test_dir_elem = root.find('.//build/testSourceDirectory', ns)
            if test_dir_elem is not None and test_dir_elem.text:
                # Convert ${basedir} to actual path if present
                test_dir = test_dir_elem.text.replace('${basedir}', str(repo_path))
                test_dir = Path(test_dir) / package.replace('.', '/')
                if test_dir.exists():
                    return test_dir
                # Create the directory if it doesn't exist
                test_dir.mkdir(parents=True, exist_ok=True)
                return test_dir
        except Exception as e:
            logger.error(f"Error parsing pom.xml: {str(e)}")
    
    # If no custom test directory found in pom.xml, proceed with standard detection
    # First check the source directory structure
    main_dir = repo_path / "src" / "main"
    first_package = package.split('.')[0]
    
    # If source is directly in main/ without java/, mirror that structure
    if (main_dir / first_package).exists():
        test_dir = repo_path / 'src' / 'test' / package.replace('.', '/')
        if test_dir.exists():
            return test_dir
        # Create the directory if it doesn't exist
        test_dir.mkdir(parents=True, exist_ok=True)
        return test_dir

    # Try standard Maven/Gradle structure
    test_dir = repo_path / 'src' / 'test' / 'java' / package.replace('.', '/')
    if test_dir.exists():
        return test_dir
        
    # Try test/java as fallback
    test_dir = repo_path / 'test' / 'java' / package.replace('.', '/')
    if test_dir.exists():
        return test_dir
        
    # Create src/test/java if neither exists
    test_dir = repo_path / 'src' / 'test' / 'java' / package.replace('.', '/')
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir

def extract_package_from_imports(imports: Dict[str, str]) -> Set[str]:
    """
    Extract package names from imports dictionary.
    
    Args:
        imports: Dictionary of imports from the class under test
        
    Returns:
        Set of package names
    """
    packages = set()
    for imp in imports.values():
        if imp:
            pkg = imp.rsplit('.', 1)[0]
            packages.add(pkg)
    return packages

def load_source(path: str) -> Dict[str, Any]:
    """
    Load and parse a Java source file to extract package and imports.
    
    Args:
        path: Path to the Java source file
        
    Returns:
        Dictionary containing source, package, and import mappings
    """
    src = Path(path).read_text(encoding="utf-8", errors="ignore")
    pkg_m = re.search(r'^\s*package\s+([\w\.]+);', src, re.MULTILINE)
    pkg = pkg_m.group(1) if pkg_m else ''
    
    # Extract all imports exactly as they appear in the file
    imports = []
    # Match the entire import statement including the semicolon
    for match in re.finditer(r'^\s*import\s+([\w\.]+);', src, re.MULTILINE):
        full_import = match.group(1)
        # Skip wildcard imports
        if not full_import.endswith('.*'):
            imports.append(full_import)
    
    return {
        "source": src,
        "package": pkg,
        "imports": imports,
        "wildcards": []  # We don't need wildcards for test generation
    }

def find_test_package_structure(repo_path: Path, source_package: str) -> str:
    """
    Find the package structure used for tests in the project.
    
    Args:
        repo_path: Root directory of the repository
        source_package: Package of the source class being tested
        
    Returns:
        The package structure for tests or None if not found
    """
    logger.debug(f"Finding test package structure for source package: {source_package}")
    logger.debug(f"Repository path: {repo_path}")

    # First check the source directory structure
    main_dir = repo_path / "src" / "main"
    logger.debug(f"Checking main directory structure: {main_dir}")
    
    # Check if this is a standard Maven/Gradle structure (src/main/java)
    if (main_dir / "java").exists():
        logger.debug("Found standard Maven/Gradle structure (src/main/java)")
        # Verify test directory exists
        test_dir = repo_path / "src" / "test" / "java" / source_package.replace('.', '/')
        if test_dir.exists():
            logger.debug(f"Found matching test directory: {test_dir}")
            return source_package
        logger.debug("No matching test directory found for standard structure")
    
    # If not standard structure, check if source is directly in main/
    first_package = source_package.split('.')[0]
    if (main_dir / first_package).exists():
        logger.debug(f"Found non-standard structure in main: {main_dir / first_package}")
        # Verify test directory exists
        test_dir = repo_path / "src" / "test" / first_package
        if test_dir.exists():
            logger.debug(f"Found matching test directory: {test_dir}")
            return source_package
        logger.debug("No matching test directory found for non-standard structure")

    # If not found, try to infer from existing test files
    test_dir = repo_path / "src" / "test"
    logger.debug(f"Checking for existing test files in: {test_dir}")
    if not test_dir.exists():
        logger.debug("No test directory found")
        return None
    
    # Look for .java files in the test directory
    test_files = list(test_dir.rglob("*.java"))
    logger.debug(f"Found {len(test_files)} test files")
    if not test_files:
        logger.debug("No test files found")
        return None
        
    # Get the common package structure from existing tests
    packages = [f.parent.relative_to(test_dir) for f in test_files]
    if packages:
        # Convert path to package structure
        package = str(packages[0]).replace('/', '.')
        logger.debug(f"Inferred package structure: {package}")
        # Verify this structure exists in test
        test_dir = repo_path / "src" / "test" / package.replace('.', '/')
        if test_dir.exists():
            logger.debug(f"Found matching test directory: {test_dir}")
            return package
        logger.debug("No matching test directory found for inferred structure")
    logger.debug("No package structure could be inferred")
    return None

def get_base_test_package(source_package: str, test_dir: Path) -> str:
    """
    Get the base test package from the source package and test directory.
    
    Args:
        source_package: Package of the source class being tested
        test_dir: Path to the test directory
        
    Returns:
        The base test package (e.g., 'com.ezylang.evalex' from 'com.ezylang.evalex.parser')
    """
    # Get the relative path from src/test/java to the test directory
    test_root = test_dir.parent.parent.parent  # Go up to src/test/java
    rel_path = test_dir.relative_to(test_root)
    
    # Convert path to package structure
    base_package = str(rel_path).replace('/', '.')
    return base_package

def generate_test_scaffold(
    class_imports: List[str],
    dependencies: Dict[str, Set[str]],
    junit_version: int,
    class_name: str,
    repo_path: Path
) -> Tuple[str, Path]:
    """
    Generate a minimal test class scaffold with essential imports.
    
    Args:
        class_imports: List of imports from the class under test
        dependencies: Dictionary of dependencies found during analysis
        junit_version: JUnit version (4 or 5) detected from build configuration
        class_name: Name of the class under test
        repo_path: Root directory of the repository
        
    Returns:
        Tuple of (scaffold string, test file path)
    """
    logger.debug(f"Generating test scaffold for class: {class_name}")
    logger.debug(f"Repository path: {repo_path}")

    # Find the source file in the repository
    source_file = None
    for path in repo_path.rglob(f"{class_name}.java"):
        source_file = path
        logger.debug(f"Found source file: {path}")
        break
    
    if not source_file or not source_file.exists():
        logger.error(f"Could not find source file for class {class_name}")
        raise ValueError(f"Could not find source file for class {class_name}")
    
    # Read the source file and extract package
    content = source_file.read_text()
    package_match = re.search(r'package\s+([\w\.]+);', content)
    if not package_match:
        logger.error(f"Could not find package declaration in {source_file}")
        raise ValueError(f"Could not find package declaration in {source_file}")
    
    source_package = package_match.group(1)
    logger.debug(f"Extracted source package: {source_package}")
    
    # Get test directory and create test file path
    test_dir = get_test_directory(repo_path, source_package)
    test_file = test_dir / f"{class_name}Test.java"
    
    # Build the scaffold
    scaffold = []
    
    # Add package declaration using the source file's package
    scaffold.append(f"package {source_package};")
    scaffold.append("")
    
    if junit_version == '5':
        scaffold.extend(JUNIT5_IMPORTS)
    else:
        scaffold.extend(JUNIT4_IMPORTS)

    # Add imports from the class under test
    # First, get all imports from the source file
    other_package_imports = []
    static_imports = []
    wildcard_imports = []
    
    for match in re.finditer(r'import\s+(?:static\s+)?([\w\.]+(?:\*)?);', content):
        full_import = match.group(1)
        if '*' in full_import:
            wildcard_imports.append(full_import)
        elif 'static' in match.group(0):
            static_imports.append(full_import)
        elif not full_import.startswith(source_package):  # Only import from other packages
            other_package_imports.append(full_import)
    
    # Add imports from other packages
    for imp in other_package_imports:
        scaffold.append(f"import {imp};")
    
    # Add static imports
    for static_imp in static_imports:
        scaffold.append(f"import static {static_imp};")
    
    # Add wildcard imports
    for wildcard in wildcard_imports:
        scaffold.append(f"import {wildcard};")
    
    # Add commonly useful imports (before deduplication to catch any that might already exist)
    useful_imports = [
        # Java Reflection (commonly used in decoders/parsers)
        "import java.lang.reflect.*;",
        
        # Java Time (commonly used in decoders/parsers)
        "import java.time.*;",
        "import java.time.format.*;",
        "import java.time.temporal.*;",
        "import java.time.zone.*;",
        "import java.time.chrono.*;",
        "import java.time.zone.*;",

        # Java IO (commonly used in decoders/parsers)
        "import java.io.InputStream;",
        "import java.io.OutputStream;",
        "import java.io.ByteArrayInputStream;",
        "import java.io.ByteArrayOutputStream;",
        "import java.io.IOException;",
        # Java Util – for collections and helpers
        "import java.util.List;",
        "import java.util.ArrayList;",
        "import java.util.Arrays;",
        "import java.util.Map;",
        "import java.util.HashMap;"
    ]
    
    scaffold.extend(useful_imports)
    
    # Also get all imports as they appear in the source file to catch any we might have missed
    all_imports = set()
    for match in re.finditer(r'import\s+(?:static\s+)?([\w\.]+(?:\*)?);', content):
        full_import = match.group(0)  # Get the entire import statement
        all_imports.add(full_import)
    
    # Add any imports we might have missed (they'll be deduplicated by the set)
    for imp in sorted(all_imports):
        if imp not in scaffold:  # Only add if not already added
            scaffold.append(imp)
    
    scaffold.append("")
    
    # Add empty test class with the correct name
    test_class_name = f"{class_name}Test"
    scaffold.append(f"public class {test_class_name} {{")
    scaffold.append("")
    scaffold.append("}")
    
    # Convert scaffold to string
    scaffold_str = "\n".join(scaffold)
    
    # Search for and delete any existing test file with the same name
    existing_test_files = list(repo_path.rglob(f"{class_name}Test.java"))
    if existing_test_files:
        for existing_file in existing_test_files:
            try:
                existing_file.unlink()
                print(f"   🗑️  Deleted existing test file: {existing_file.relative_to(repo_path)}")
            except Exception as e:
                print(f"   ⚠️  Could not delete existing test file {existing_file.relative_to(repo_path)}: {e}")
    
    # Write the test file to disk (this will overwrite if file exists)
    test_file.write_text(scaffold_str, encoding='utf-8')
    
    # Store the test file path in the global config
    test_config.set_test_file_path(str(test_file))
    
    return scaffold_str, test_file 