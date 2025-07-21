import os
import logging
import javalang
from pathlib import Path

logger = logging.getLogger(__name__)

def normalize_qualifier(qualifier: str) -> str:
    """
    Normalize a class qualifier to match Java class naming conventions.
    First letter capitalized, rest of the name preserved.
    """
    if not qualifier:
        return qualifier
    return qualifier[0].upper() + qualifier[1:]

def detect_repo_structure(repo_root: str) -> str:
    """
    Detect the repository structure and return the adjusted repo_root.
    This function checks for common Java project structures and returns
    the path that should be used as the base for all file operations.
    """
    # Check for standard Maven/Gradle structure
    if os.path.exists(os.path.join(repo_root, 'src', 'main', 'java')):
        return os.path.join(repo_root, 'src', 'main', 'java')
        
    # Check for src/main structure
    if os.path.exists(os.path.join(repo_root, 'src', 'main')):
        return os.path.join(repo_root, 'src', 'main')
        
    # Check for src structure
    if os.path.exists(os.path.join(repo_root, 'src')):
        return os.path.join(repo_root, 'src')
        
    # If no standard structure found, return original repo_root
    return repo_root

def resolve_source_file(repo_root: str, imports: dict, src_package: str, qualifier: str) -> str:
    """
    Given a class qualifier, find its .java file path using imports or package structure.
    Handles both regular classes and nested types (when package ends with uppercase class name).
    """
    # First, detect the repository structure
    adjusted_root = detect_repo_structure(repo_root)
    
    # Normalize the qualifier to match Java class naming conventions
    normalized_qualifier = normalize_qualifier(qualifier)
    
    # Helper function to check if a package path indicates a nested type
    def is_nested_type(pkg: str) -> bool:
        parts = pkg.split('.')
        return len(parts) > 0 and parts[-1][0].isupper()
    
    # Helper function to get outer class info from nested type package
    def get_outer_class_info(pkg: str) -> tuple[str, str]:
        parts = pkg.split('.')
        outer_class = parts[-1]
        outer_pkg = '.'.join(parts[:-1])
        return outer_pkg, outer_class
    
    # 1) if imported explicitly - try both original and normalized qualifier
    if qualifier in imports:
        pkg = imports[qualifier]
        
        # Check if this is a nested type
        if is_nested_type(pkg):
            outer_pkg, outer_class = get_outer_class_info(pkg)
            path = os.path.join(adjusted_root, *outer_pkg.split('.'), f'{outer_class}.java')
        else:
            path = os.path.join(adjusted_root, *pkg.split('.'), f'{normalized_qualifier}.java')
            
        if os.path.isfile(path):
            return path
        
    elif normalized_qualifier in imports:
        pkg = imports[normalized_qualifier]
        
        # Check if this is a nested type
        if is_nested_type(pkg):
            outer_pkg, outer_class = get_outer_class_info(pkg)
            path = os.path.join(adjusted_root, *outer_pkg.split('.'), f'{outer_class}.java')
        else:
            path = os.path.join(adjusted_root, *pkg.split('.'), f'{normalized_qualifier}.java')
            
        if os.path.isfile(path):
            return path
    
    # 2) if in same package - try both original and normalized qualifier
    # Check if source package indicates a nested type
    if is_nested_type(src_package):
        outer_pkg, outer_class = get_outer_class_info(src_package)
        path = os.path.join(adjusted_root, *outer_pkg.split('.'), f'{outer_class}.java')
    else:
        path = os.path.join(adjusted_root, *src_package.split('.'), f'{normalized_qualifier}.java')
        
    if os.path.isfile(path):
        return path
    
    # 3) if in repository - try both original and normalized qualifier
    for root, _, files in os.walk(adjusted_root):
        if f"{normalized_qualifier}.java" in files:
            candidate = os.path.join(root, f"{normalized_qualifier}.java")
            return candidate
    
    return ""