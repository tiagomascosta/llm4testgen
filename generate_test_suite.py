#!/usr/bin/env python3

# Run this script from the implementation directory for imports to work correctly

import sys
from pathlib import Path
from collections import defaultdict
import requests
from typing import Tuple
import argparse
import re
import os
import time
import json
import logging
import subprocess
import shutil
from datetime import datetime

from cli.arguments import parse_args
from init.repository import RepositoryManager
from init.repository_analyzer import RepositoryAnalyzer
from init.gradle import GradleConfig
from init.gradle_build import GradleBuildManager
from utils.logging import setup_logging
from utils.json_logger import TestGenerationLogger
from init.maven_build import MavenBuildManager
from source_analysis import (
    slice_method,
    extract_dependencies,
    find_flow_control_deps,
    extract_method_slice,
    load_source,
    parse_method_node,
    generate_test_scaffold
)
from prompting.scenario_list_prompt import build_scenario_list_prompt, RawScenarios
from prompting.clustering_prompt import build_clustering_prompt, ScenarioList
from prompting.test_case_prompt import build_test_case_prompt, TestMethodOnly
from llm import OllamaClient
from init.maven import MavenConfig
from utils import compile_java_file
from utils.compiler import assemble_and_compile_test
from source_analysis.source_resolver import detect_repo_structure
from config import test_config
from init.build import _ensure_sdkman_installed, _install_jdk_with_sdkman

# New imports for test execution
from utils.build_system_detector import detect_build_system
from utils.test_executor import run_test_class, run_all_tests
from utils.test_result_parser import extract_test_method_names
from utils.compile_fix_loop import count_errors

# Global variable to hold the base message of the current sub-step for overwriting
_current_sub_step_line_base_message = ""

def print_header():
    """Prints the LLM4TestGen header with ASCII art."""
    print('''
██╗     ██╗     ███╗   ███╗██╗  ██╗████████╗███████╗███████╗████████╗ ██████╗ ███████╗███╗   ██╗
██║     ██║     ████╗ ████║██║  ██║╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝██╔════╝ ██╔════╝████╗  ██║
██║     ██║     ██╔████╔██║███████║   ██║   █████╗  ███████╗   ██║   ██║  ███╗█████╗  ██╔██╗ ██║
██║     ██║     ██║╚██╔╝██║╚════██║   ██║   ██╔══╝  ╚════██║   ██║   ██║   ██║██╔══╝  ██║╚██╗██║
███████╗███████╗██║ ╚═╝ ██║     ██║   ██║   ███████╗███████║   ██║   ╚██████╔╝███████╗██║ ╚████║
╚══════╝╚══════╝╚═╝     ╚═╝     ╚═╝   ╚═╝   ╚══════╝╚══════╝   ╚═╝    ╚═════╝ ╚══════╝╚═╝  ╚═══╝
                                                                                                
                                           Version Beta
''')
    print("") # Add a newline for spacing

def print_step(step_name: str, step_number: int):
    """Print a major step with box-style formatting."""
    # Fixed width for the box
    box_width = 40  # Reduced from 40 to 38 to fix alignment
    # Adjust spacing based on number of digits in step_number
    digit_adjustment = len(str(step_number)) - 1  # 0 for 1-digit, 1 for 2-digit
    print(f"\n\n╭{'─' * box_width}╮")
    print(f"│ 🧩  Step {step_number}: {step_name}{' ' * (box_width - len(step_name) - 13 - digit_adjustment)}│")
    print(f"╰{'─' * box_width}╯\n")

def print_success(message: str):
    """Print a success message with checkmark."""
    print(f"   ✓ {message}")

def print_warning(message: str):
    """Print a warning message."""
    print(f"   ⚠️ {message}")

def print_error(message: str):
    """Print an error message."""
    print(f"   ❌ {message}")

def print_dependency_summary(deps: dict, flow_control: set):
    """Print a concise summary of dependencies."""
    # Count dependencies by category
    category_counts = {cat: len(sigs) for cat, sigs in deps.items()}
    flow_control_count = len(flow_control)
    
    # Check if we have any dependencies
    total_deps = sum(category_counts.values())
    if total_deps == 0:
        print("\n📊 Summary:")
        print("   → No dependencies found")
        return
    
    # Print summary with improved formatting
    print("\n📊 Summary:")
    for category, count in category_counts.items():
        # Convert category name to a more readable format
        category_name = category.replace('_', ' ').title()
        print(f"   • {category_name} – {count}")
    
    # Print flow control count only if there are any
    if flow_control_count > 0:
        print(f"\n   → {flow_control_count} are flow control-related")

def print_java_versions(versions: str):
    """Print available Java versions in a tree-like format."""
    print("\n   ✓ Java versions available:")
    if versions and versions != "No Java version manager found":
        # Split versions into lines and format each line
        version_lines = versions.strip().split('\n')
        for i, line in enumerate(version_lines):
            if i == len(version_lines) - 1:
                prefix = "     └─ "
            else:
                prefix = "     ├─ "
            # Split the line into name and version
            parts = line.split('→')
            if len(parts) == 2:
                name = parts[0].strip()
                version = parts[1].strip()
                # Format with proper spacing
                print(f"{prefix}{name:<30} → {version}")
            else:
                print(f"{prefix}{line}")
    else:
        print("     └─ No Java versions found")

def print_selected_java(version: str, source: str):
    """Print the selected Java version with source."""
    # Convert version format (e.g., 1.8.0_442 -> 8)
    if version.startswith('1.'):
        version = version.split('.')[1]
    elif '.' in version:
        version = version.split('.')[0]
    print(f"   ✅ Selected Java version: {version} ({source})\n")

def print_dependencies(dependencies: list):
    """Print added dependencies in a tree-like format."""
    print("\n   📦 Dependencies added:")
    for i, dep in enumerate(dependencies):
        if i == len(dependencies) - 1:
            prefix = "     └─ "
        else:
            prefix = "     ├─ "
        print(f"{prefix}{dep}")

def normalize_java_version(version):
    """Normalize Java version to major version number."""
    if not version:
        return "unknown"
    if version.startswith('1.'):
        return version.split('.')[1]  # Convert 1.7 to 7, 1.8 to 8
    return version.split('.')[0]  # Convert 7.0.442 to 7, 8.0.442 to 8

def generate_test_suite(repo_path: Path, output_dir: Path):
    """
    Generate a test suite for the repository.
    
    Args:
        repo_path: Path to the repository
        output_dir: Path to write the test suite to
    """
    # Initialize project config based on build system
    if (repo_path / 'pom.xml').exists():
        from .init.maven import MavenConfig
        project_config = MavenConfig(repo_path)
    else:
        from .init.gradle_build import GradleBuildManager
        project_config = GradleBuildManager(repo_path)
        
    # Get JUnit version and update global config
    junit_version = project_config.get_junit_version()
    if junit_version:
        test_config.set_junit_version(junit_version)
        
    # Get Java version and update global config
    java_version = project_config.get_java_version()
    if java_version:
        test_config.set_java_version(java_version)
        
    # Now all modules can access:
    # - JUnit version via test_config.get_junit_version()
    # - Test framework via test_config.get_test_framework()
    # - Java version via test_config.get_java_version()
    
    # Continue with test generation...

def extract_repo_name(repo_url: str = None, local_path: str = None) -> str:
    """
    Extract repository name from URL or local path.
    
    Args:
        repo_url: GitHub repository URL
        local_path: Local repository path
        
    Returns:
        Repository name
    """
    if repo_url:
        # Extract from GitHub URL: https://github.com/user/repo.git -> repo
        repo_name = repo_url.rstrip('/').split('/')[-1]
        # Remove .git extension if present
        if repo_name.endswith('.git'):
            repo_name = repo_name[:-4]
        return repo_name
    elif local_path:
        # Extract from local path: /path/to/repo -> repo
        return Path(local_path).name
    else:
        return "unknown_repo"


def get_output_directory(user_output_dir: str = None) -> Path:
    """
    Determine the output directory based on user input.
    
    Args:
        user_output_dir: User-specified output directory (can be None)
        
    Returns:
        Path to the output directory
    """
    if user_output_dir:
        # User specified a path - assume it's absolute
        user_path = Path(user_output_dir)
        
        # Check if the directory exists
        if user_path.exists():
            return user_path
        else:
            # Directory doesn't exist, fall back to default with warning
            print_warning(f"Specified output directory '{user_output_dir}' does not exist. Using default 'output' directory.")
            return Path("output")
    else:
        # Default relative path
        return Path("output")


def get_numbered_filename(base_filename: str, output_dir: Path) -> Tuple[str, str]:
    """
    Generate a numbered filename if the base filename already exists in the output directory.
    
    Args:
        base_filename: The base filename (e.g., "method_ClassTest.java")
        output_dir: The output directory to check for existing files
        
    Returns:
        Tuple of (numbered_filename, numbered_class_name)
    """
    # Extract the class name from the filename (remove .java extension)
    class_name = base_filename[:-5]  # Remove .java
    
    # Check if the file already exists
    if (output_dir / base_filename).exists():
        # Find the next available number
        existing_files = [f.name for f in output_dir.glob("*.java")]
        existing_numbers = []
        
        # Extract numbers from existing files with the same base name
        for file in existing_files:
            # Check if it's a numbered version of our file (e.g., method_Class_01Test.java)
            if file.startswith(class_name) and "_" in file and file.endswith("Test.java"):
                # Check if it has a number suffix before "Test.java"
                parts = file.split("_")
                if len(parts) >= 2:
                    last_part = parts[-1]
                    if last_part.endswith("Test.java"):
                        number_part = last_part[:-9]  # Remove "Test.java"
                        if number_part.isdigit():
                            try:
                                num = int(number_part)
                                existing_numbers.append(num)
                            except ValueError:
                                pass
            elif file == base_filename:
                # The base file exists, so we need numbering
                existing_numbers.append(0)  # Use 0 to indicate base file exists
        
        # Find the next available number
        next_number = 1
        while next_number in existing_numbers:
            next_number += 1
        
        # Format with new naming convention
        numbered_filename = f"{class_name}_{next_number:02d}Test.java"
        numbered_class_name = f"{class_name}_{next_number:02d}Test"
        
        return numbered_filename, numbered_class_name
    else:
        # No numbering needed - file doesn't exist
        return base_filename, class_name


def create_structured_output_path(base_output_dir: Path, repo_name: str, retain_test_suites: bool = False) -> Path:
    """
    Create the structured output path with repository folder and test_suite subdirectory.
    
    Args:
        base_output_dir: Base output directory
        repo_name: Repository name
        retain_test_suites: Whether to retain existing test suites in output folder
        
    Returns:
        Path to the repository-specific output directory with test_suite subdirectory
    """
    repo_output_dir = base_output_dir / repo_name
    test_suite_dir = repo_output_dir / "test_suite"
    
    if retain_test_suites:
        # If retaining test suites, keep only the test_suite directory and JSON files in reports
        # Delete everything else (potential_bugs, coverage_reports, etc.)
        if repo_output_dir.exists():
            import shutil
            # Save test_suite content temporarily if it exists
            temp_test_suite = None
            if test_suite_dir.exists():
                temp_test_suite = Path(f"/tmp/temp_test_suite_{repo_name}")
                shutil.copytree(test_suite_dir, temp_test_suite)
            
            # Save only JSON files from reports folder temporarily if it exists
            temp_json_files = []
            reports_dir = repo_output_dir / "reports"
            if reports_dir.exists():
                # Create temporary directory for JSON files
                temp_json_dir = Path(f"/tmp/temp_json_files_{repo_name}")
                temp_json_dir.mkdir(exist_ok=True)
                
                # Copy only JSON files from reports directory
                for json_file in reports_dir.glob("*.json"):
                    shutil.copy2(json_file, temp_json_dir)
                    temp_json_files.append(json_file.name)
            
            # Delete entire repository directory
            shutil.rmtree(repo_output_dir)
            
            # Recreate repository directory
            repo_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Restore test_suite content if it existed
            if temp_test_suite and temp_test_suite.exists():
                shutil.copytree(temp_test_suite, test_suite_dir)
                shutil.rmtree(temp_test_suite)
            else:
                # Create fresh test_suite directory
                test_suite_dir.mkdir(parents=True, exist_ok=True)
            
            # Restore JSON files to reports directory if they existed
            if temp_json_files:
                reports_dir.mkdir(parents=True, exist_ok=True)
                temp_json_dir = Path(f"/tmp/temp_json_files_{repo_name}")
                for json_filename in temp_json_files:
                    source_file = temp_json_dir / json_filename
                    if source_file.exists():
                        shutil.copy2(source_file, reports_dir / json_filename)
                # Clean up temporary JSON directory
                shutil.rmtree(temp_json_dir)
        else:
            # Create fresh repository directory and test_suite subdirectory
            test_suite_dir.mkdir(parents=True, exist_ok=True)
    else:
        # Remove entire repository output directory if it exists to ensure clean slate
        if repo_output_dir.exists():
            import shutil
            shutil.rmtree(repo_output_dir)
        
        # Create fresh repository directory and test_suite subdirectory
        test_suite_dir.mkdir(parents=True, exist_ok=True)
    
    return test_suite_dir

def get_numbered_json_report_filename(base_filename: str, reports_dir: Path) -> str:
    """
    Generate a numbered JSON report filename if the base filename already exists in the reports directory.
    Args:
        base_filename: The base filename (e.g., "Leetcode_report.json")
        reports_dir: The reports directory to check for existing files
    Returns:
        Numbered filename (e.g., "Leetcode_report_01.json")
    """
    if not (reports_dir / base_filename).exists():
        return base_filename
    # Find the next available number
    import re
    existing_files = [f.name for f in reports_dir.glob("*.json")]
    base_prefix = base_filename[:-5]  # Remove .json
    existing_numbers = []
    for file in existing_files:
        match = re.match(rf"{re.escape(base_prefix)}_(\d\d)\.json", file)
        if match:
            try:
                num = int(match.group(1))
                existing_numbers.append(num)
            except ValueError:
                pass
        elif file == base_filename:
            existing_numbers.append(0)
    next_number = 1
    while next_number in existing_numbers:
        next_number += 1
    return f"{base_prefix}_{next_number:02d}.json"

def main():
    """Main entry point for the test suite generator."""
    
    # Parse command line arguments
    args = parse_args()
    
    # Create output directory
    base_output_dir = get_output_directory(args.output_dir)
    repo_name = extract_repo_name(args.repo_url, args.local_path)
    structured_output_dir = create_structured_output_path(base_output_dir, repo_name, args.retain_test_suites)
    
    # Start timing
    start_time = time.time()

    print_header()

    try:
        # Step 1: Repository Setup
        print_step("Repository Setup", 1)
        
        # Determine output directory structure
        base_output_dir = get_output_directory(args.output_dir)
        repo_name = extract_repo_name(args.repo_url, args.local_path)
        structured_output_dir = create_structured_output_path(base_output_dir, repo_name, args.retain_test_suites)
        
        # Initialize JSON logger for tracking the entire pipeline
        target_class = args.method.split('#')[0].split('.')[-1]
        target_method = args.method.split('#')[-1]
        json_logger = TestGenerationLogger(repo_name, target_class, target_method)
        
        # Log LLM models and CLI options (available from command line arguments)
        json_logger.update_llm_models(args.code_model, args.non_code_model)
        json_logger.update_cli_options(args.max_fix_attempts, args.max_compile_fix_examples, args.max_scaffold_examples)
        
        print_success(f"Output directory: {structured_output_dir}")
        
        repo_manager = RepositoryManager(structured_output_dir)
        
        current_working_directory = Path.cwd()

        if args.repo_url:
            repo_path = repo_manager.clone_repository(args.repo_url, args.commit_hash)
            relative_repo_path = repo_path.relative_to(current_working_directory)
            print_success(f"Cloned to: {relative_repo_path}")
            
            # Update JSON logger with repository info
            json_logger.update_repository_info(
                repo_url=args.repo_url,
                commit_hash=args.commit_hash or "unknown",
                build_system=""  # Will be updated later when build system is detected
            )
        else:
            repo_path = repo_manager.use_local_repository(args.local_path)
            relative_repo_path = repo_path.relative_to(current_working_directory)
            print_success(f"Using local repository at: {relative_repo_path}")
            
            # Update JSON logger with repository info for local repo
            json_logger.update_repository_info(
                repo_url="local",
                commit_hash="local",
                build_system=""  # Will be updated later when build system is detected
            )
            
        # Detect build system
        gradle_build = (repo_path / 'build.gradle').exists()
        if gradle_build:
            build_system = "Gradle"
            build_config = GradleConfig(repo_path)
            build_manager = GradleBuildManager(repo_path)
        else:
            build_system = "Maven"
            build_config = MavenConfig(repo_path)
            build_manager = MavenBuildManager(repo_path)
        print_success(f"Build system: {build_system}")
        
        # Update JSON logger with build system info
        json_logger.update_field("build_system", build_system)
        
        # Show all available Java versions
        repo_analyzer = RepositoryAnalyzer(repo_path)
        _, available_versions = repo_analyzer.detect_java_version()
        print_java_versions(available_versions)
        
        # Detect Java version
        if gradle_build:
            java_version = build_manager._detect_required_jdk_version()
        else:
            java_version = build_manager.required_jdk_version
        
        # Log Java version from project detection (now guaranteed to be set)
        json_logger.update_field("java_repo_version", normalize_java_version(java_version))
        
        # Get the source of the Java version
        java_source = "system"
        java_path = None
        
        if available_versions and available_versions != "No Java version manager found" and java_version:
            required_version = normalize_java_version(java_version)
            # First try to find Temurin version
            temurin_found = False
            for line in available_versions.split('\n'):
                if 'temurin' in line.lower():
                    version_match = re.search(r'\(([^)]+)\)', line)
                    if version_match:
                        available_version = normalize_java_version(version_match.group(1))
                        if available_version == required_version:
                            path_match = re.match(r'([^(]+)', line)
                            if path_match:
                                java_source = path_match.group(1).strip()
                                java_path = java_source
                                temurin_found = True
                                break
            
            # If Temurin not found, fall back to any matching version
            if not temurin_found:
                for line in available_versions.split('\n'):
                    version_match = re.search(r'\(([^)]+)\)', line)
                    if version_match:
                        available_version = normalize_java_version(version_match.group(1))
                        if available_version == required_version:
                            path_match = re.match(r'([^(]+)', line)
                            if path_match:
                                java_source = path_match.group(1).strip()
                                java_path = java_source
                                break
            
            # Only try SDKMAN if we haven't found the version we need
            if not java_path:
                print_warning(f"Required Java version {required_version} not found. Attempting to install via SDKMAN...")
                if _ensure_sdkman_installed():
                    print("   → SDKMAN is installed, attempting to install Java...")
                    try:
                        java_path = _install_jdk_with_sdkman(required_version)
                        if java_path:
                            java_source = "sdkman"
                            print_success(f"Successfully installed Java {required_version} via SDKMAN at {java_path}")
                        else:
                            print_error(f"Failed to install Java {required_version} via SDKMAN - installation returned no path")
                    except Exception as e:
                        print_error(f"Failed to install Java {required_version} via SDKMAN: {str(e)}")
                else:
                    print_error("SDKMAN not available for Java installation - ensure SDKMAN is installed and configured")
        
        # Set Java version and path in test_config
        test_config.set_java_version(java_version)
        if java_path:
            test_config.set_java_path(java_path)
            # Set environment variables for the current process and all subprocesses
            os.environ['JAVA_HOME'] = java_path
            os.environ['PATH'] = f"{java_path}/bin:{os.environ['PATH']}"
            # Also set JAVA_HOME for Gradle
            os.environ['GRADLE_OPTS'] = f"-Dorg.gradle.java.home={java_path}"
        
        # Detect JUnit version
        if gradle_build:
            junit_version = build_config._detect_junit_version(build_config.gradle_file.read_text())
        else:
            junit_version = build_config.get_junit_version()
        print_success(f"JUnit version: {junit_version}")
        
        # Analyze dependencies
        if gradle_build:
            build_config.configure()
        else:
            build_config.configure()
            
        # Print added dependencies
        if build_config.added_dependencies:
            print_dependencies(build_config.added_dependencies)
            
        print_success("Build file updated with required dependencies")
        
        # Log JUnit version from global config (now guaranteed to be set)
        json_logger.update_field("junit_version", test_config.get_junit_version())
        
        # Step 2: Dependency Analysis
        print_step("Dependency Analysis", 2)
        
        # Initialize method info
        method_info = {
            'method_name': args.method.split('#')[-1],
            'class_name': args.method.split('#')[0].split('.')[-1],
            'package': '.'.join(args.method.split('#')[0].split('.')[:-1])
        }
        
        # Get class code using detected repository structure
        adjusted_root = detect_repo_structure(str(repo_path))
        class_file = Path(adjusted_root) / method_info['package'].replace('.', '/') / f"{method_info['class_name']}.java"
        if not class_file.exists():
            print_error(f"Could not find class file: {class_file}")
            return
        method_info['class_code'] = class_file.read_text()
        
        # Slice method implementation
        method_impl = slice_method(repo_path, args.method)
        if not method_impl:
            print_error(f"Could not find method: {args.method}")
            return
        method_info['implementation'] = method_impl
        method_info['method_code'] = method_impl
        method_info['method_signature'] = method_impl.split('{')[0].strip()
        
        # Parse method node
        class_node, method_node = parse_method_node(method_info['class_code'], method_info['method_name'])
        
        # Detect if method is inside a nested class
        import javalang
        tree = javalang.parse.parse(method_info['class_code'])

        # Find the outer class (should match the class_name)
        outer_class = None
        for type_decl in tree.types:
            if isinstance(type_decl, javalang.tree.ClassDeclaration) and type_decl.name == method_info['class_name']:
                outer_class = type_decl
                break

        # Check if the method is actually in a nested class
        inner_class_name = None
        if outer_class:
            for member in outer_class.body:
                if isinstance(member, javalang.tree.ClassDeclaration):
                    # Check if this nested class contains our method
                    for method in member.methods:
                        if method.name == method_info['method_name']:
                            inner_class_name = member.name
                            break
                    if inner_class_name:
                        break

        # Set the inner class information
        if inner_class_name:
            method_info['inner_class'] = inner_class_name
        else:
            method_info['inner_class'] = None
        
        # Extract dependencies
        deps = extract_dependencies(method_info['class_code'], method_info['method_name'])
        print_success("Dependencies extracted")
        
        # Analyze flow control
        flow_control = find_flow_control_deps(method_node)
        
        # Log total number of dependencies extracted (including flow control)
        total_dependencies = sum(len(dependency_set) for dependency_set in deps.values()) + len(flow_control)
        json_logger.update_field("dependency_analysis", total_dependencies)
        
        # Print concise dependency summary to console
        print_dependency_summary(deps, flow_control)
        
        # Build qualifier map
        from source_analysis.qualifier_builder import build_qualifier_map
        qualifier_map = build_qualifier_map(class_node, method_node)
        
        # Step 3: Scaffold Generation
        print_step("Scaffold Generation", 3)
        
        # Generate test scaffold
        test_scaffold, test_file = generate_test_scaffold(
            class_imports=load_source(str(class_file))['imports'],
            dependencies=deps,
            junit_version=junit_version,
            class_name=method_info['class_name'],
            repo_path=repo_path
        )
        print_success("Test scaffold generated")
        # Print the relative path where the test scaffold was saved
        if test_file.is_absolute():
            # If it's an absolute path, make it relative to the current working directory
            try:
                relative_path = test_file.relative_to(current_working_directory)
            except ValueError:
                # If it's not a subpath, just show the absolute path
                relative_path = test_file
        else:
            # If it's already a relative path, use it as is
            relative_path = test_file
        print_success(f"Test scaffold saved at: {relative_path}")
        
        # Save and compile scaffold
        if compile_java_file(test_file, repo_path, java_home=build_manager.java_home):
            pass
        else:
            pass
            
        # Store scaffold for later use
        method_info['test_scaffold'] = test_scaffold
        
        # Log actual Java version used (may differ from project requirement due to compilation fallbacks)
        json_logger.update_field("java_version_used", normalize_java_version(test_config.get_java_version()))
        
        # Step 4: Test Scenario List
        print_step("Test Scenario List", 4)
        
        # Build scenario list prompt
        system_message, scenario_prompt = build_scenario_list_prompt(method_info)
        
        # Print the prompt
        #print("📝 Prompt:")
        #print("─" * 38)
        #print(scenario_prompt)
        #print("─" * 38 + "\n")
        
        # Initialize Ollama client
        llm_client = OllamaClient(
            base_url="http://localhost:11435/api/chat",
            code_model=args.code_model,
            non_code_model=args.non_code_model
        )
        
        raw_scenarios = llm_client.call_structured(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": scenario_prompt}
            ],
            schema=RawScenarios.model_json_schema(),
            is_code_task=False
        )
        raw_scenarios = RawScenarios.model_validate_json(raw_scenarios)
        
        # Log raw scenarios
        json_logger.add_raw_scenarios(raw_scenarios.scenarios)
        
        # Print the response
        print("📝 Response:")
        print("─" * 38)
        for idx, scenario in enumerate(raw_scenarios.scenarios, 1):
            print(f"{idx}. {scenario}")
        print("─" * 38 + "\n")
        print_success(f"Generated {len(raw_scenarios.scenarios)} raw scenarios")
        
        # Cluster scenarios
        print_step("Clustering Scenarios", 5)
        system_message, clustering_prompt = build_clustering_prompt(
            raw_scenarios.scenarios,
            method_info['method_name'],
            junit_version,
            method_info  # Pass the method_info for MUT delimiting
        )
        
        # Print the prompt
        #print("📝 Prompt:")
        #print("─" * 38)
        #print(clustering_prompt)
        #print("─" * 38 + "\n")
        
        clustered_scenarios = llm_client.call_structured(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": clustering_prompt}
            ],
            schema=ScenarioList.model_json_schema(),
            is_code_task=False
        )
        clustered_scenarios = ScenarioList.model_validate_json(clustered_scenarios)
        
        # Log clustered scenarios (convert to theme format)
        themes = [{"title": scenario.title, "description": scenario.description} for scenario in clustered_scenarios.scenarios]
        json_logger.update_themes(themes)
        
        # Print the response
        print("📝 Response:")
        print("─" * 38)
        for idx, scenario in enumerate(clustered_scenarios.scenarios, 1):
            print(f"{idx}. {scenario.title}")
            print(f"   {scenario.description}")
        print("─" * 38 + "\n")

        print_success(f"Clustered into {len(clustered_scenarios.scenarios)} scenarios")
        
        # Generate test cases for all clustered scenarios
        print_step("Test Case Generation", 6)
        
        # Initialize tracking variables
        final_tests = []  # Collect successful test methods
        recent_successful_tests = []  # Track recent successes for compile-fix examples
        compile_results = []  # Track compilation results for each scenario
        dynamic_scaffold = method_info['test_scaffold']  # Start with original scaffold
        
        # Process each scenario
        for idx, scenario in enumerate(clustered_scenarios.scenarios, 1):
            print(f"\n📝 Processing scenario {idx}/{len(clustered_scenarios.scenarios)}")
            print(f"   Theme: {scenario.title}")
            print(f"   Description: {scenario.description}")
            
            # Update scaffold with recent successful examples (max 5)
            if recent_successful_tests and args.max_scaffold_examples > 0:
                examples_block = "\n// === EXAMPLE TEST METHODS ===\n"
                for idx_example, method_body in enumerate(recent_successful_tests[-args.max_scaffold_examples:], start=1):
                    examples_block += f"// Example {idx_example}:\n{method_body}\n\n"
                
                # Insert examples into the scaffold
                indented_examples = "\n".join("    " + line for line in examples_block.splitlines())
                last_brace_index = dynamic_scaffold.rfind("}")
                if last_brace_index != -1:
                    dynamic_scaffold = (
                        dynamic_scaffold[:last_brace_index] +
                        "\n" +
                        indented_examples + "\n" +
                        "    // INSERT TEST METHOD HERE\n" +
                        dynamic_scaffold[last_brace_index:]
                    )
            
            # Build test case prompt with updated scaffold
            system_message, test_case_prompt = build_test_case_prompt(
                mut_sig=method_info['method_signature'],
                mut_body=method_info['method_code'],
                scaffold=dynamic_scaffold,  # Use dynamic scaffold with examples
                scenario=scenario,
                helpers=method_info.get('helpers', []),
                junit_version=junit_version,
                deps=deps,
                qualifier_map=qualifier_map,
                flow_control=flow_control,
                class_code=method_info['class_code'],
                repo_root=str(repo_path),
                imports=load_source(str(class_file))['imports'],
                src_package=method_info['package'],
                class_name=method_info['class_name']
            )
            
            # Send prompt to LLM and get response
            test_method = llm_client.call_structured(
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": test_case_prompt}
                ],
                schema=TestMethodOnly.model_json_schema(),
                is_code_task=True
            )
            test_method = TestMethodOnly.model_validate_json(test_method)
            
            print_success("Generated test method")
            
            # Try to compile the test method
            success, assembled_source, compilation_errors = assemble_and_compile_test(
                scaffold=method_info['test_scaffold'],  # Use original scaffold for compilation
                test_method=test_method.testMethod,
                repo_path=repo_path,
                java_home=build_manager.java_home
            )
            
            if success:
                print_success("Test method compiled successfully on first attempt")
                final_tests.append((scenario, test_method.testMethod))
                recent_successful_tests.append(test_method.testMethod)
                compile_results.append((scenario.title, True, 1))  # (title, success, attempts)
                
                # Log successful compilation on first attempt
                json_logger.add_test_generation_scenario(
                    scenario_name=scenario.title,
                    compiled=True,
                    compiled_on_first_attempt=True,
                    fix_attempts=0,  # Fixed: should be 0 when compiled on first attempt
                    initial_compile_errors=0  # No errors on first attempt
                )
                
                # Keep only the last 5 successful tests for examples
                if len(recent_successful_tests) > args.max_scaffold_examples:
                    recent_successful_tests.pop(0)
            else:
                # Import the compile-fix loop
                from utils.compile_fix_loop import compile_fix_loop
                
                # Count initial compilation errors for logging
                initial_error_count = count_errors(compilation_errors)
                
                # Run the compile-fix loop with the compilation errors
                fix_success, final_test_method, attempts_made = compile_fix_loop(
                    test_method=test_method.testMethod,
                    scaffold=method_info['test_scaffold'],  # Use original scaffold for compilation
                    repo_path=repo_path,
                    java_home=build_manager.java_home,
                    class_code=method_info['class_code'],
                    junit_version=junit_version,
                    llm_client=llm_client,
                    compilation_errors=compilation_errors,  # Pass the compilation errors
                    max_attempts=args.max_fix_attempts,
                    recent_successful_tests=recent_successful_tests,
                    max_examples=args.max_compile_fix_examples
                )
                
                if fix_success:
                    final_tests.append((scenario, final_test_method))
                    recent_successful_tests.append(final_test_method)
                    compile_results.append((scenario.title, True, attempts_made + 1))  # Add 1 for initial attempt
                    
                    # Log successful compilation after fix attempts
                    json_logger.add_test_generation_scenario(
                        scenario_name=scenario.title,
                        compiled=True,
                        compiled_on_first_attempt=False,
                        fix_attempts=attempts_made,
                        initial_compile_errors=initial_error_count
                    )
                    
                    # Keep only the last 5 successful tests for examples
                    if len(recent_successful_tests) > args.max_scaffold_examples:
                        recent_successful_tests.pop(0)
                else:
                    print_error(f"Test method failed to compile after {attempts_made} fix attempts")
                    compile_results.append((scenario.title, False, attempts_made + 1))  # Add 1 for initial attempt
                    
                    # Log failed compilation after fix attempts
                    json_logger.add_test_generation_scenario(
                        scenario_name=scenario.title,
                        compiled=False,
                        compiled_on_first_attempt=False,
                        fix_attempts=attempts_made,
                        initial_compile_errors=initial_error_count
                    )
        
        # Print summary of results
        print("\n📊 Test Generation Summary:")
        print("─" * 38)
        print(f"   Total scenarios processed: {len(clustered_scenarios.scenarios)}")
        print(f"   Successful tests: {len(final_tests)}")
        print(f"   Failed tests: {len(clustered_scenarios.scenarios) - len(final_tests)}")
        
        if compile_results:
            print(f"\n   Detailed Results:")
            for title, success, attempts in compile_results:
                status = "✅" if success else "❌"
                print(f"     {status} {title} ({attempts} attempts)")
        
        # Step 7: Test Execution & Filtering
        if final_tests:
            print_step("Test Execution & Filtering", 7)
            
            # Detect build system
            try:
                build_system = detect_build_system(repo_path)
            except ValueError as e:
                print_error(f"Build system detection failed: {e}")
                print_warning("Skipping test execution - proceeding with all compiled tests")
                build_system = None
            
            if build_system:
                # Use the test file that was already created and compiled
                # This is the correct test file path from our system
                test_file_path = test_file  # This is the Path object from generate_test_scaffold
                
                # Run the test class and get individual results
                # Use the source package for the fully qualified class name
                test_package = method_info['package']
                test_class_name = test_file_path.stem
                fully_qualified_class = f"{test_package}.{test_class_name}"
                
                individual_results, individual_failures, group_failures = run_test_class(
                    fully_qualified_class,
                    repo_path,
                    build_system,
                    final_tests=final_tests,  # Pass the tuple directly
                    scaffold=method_info['test_scaffold'],  # Pass the scaffold
                    test_file_path=test_file_path,
                    output_dir=structured_output_dir.parent,  # Use parent to create potential_bugs at same level
                    json_logger=json_logger,  # Pass the JSON logger
                    # Add new parameters for runtime fix loop
                    class_code=method_info['class_code'],
                    junit_version=junit_version,
                    llm_client=llm_client,
                    args=args,
                    mut_body=method_info['method_code']  # Pass the method body for MUT delimiting
                )
                
                
                # Filter tests based on execution results
                passing_tests = []
                execution_results = []
                failure_types = {}  # Track failure types for detailed summary
                
                # Store the original total number of tests before filtering
                total_tests_generated = len(final_tests)
                
                for idx, (scenario, test_method) in enumerate(final_tests, 1):
                    # Extract test method name from the method content
                    method_name_match = re.search(r'public\s+void\s+(\w+)\s*\(', test_method)
                    if method_name_match:
                        method_name = method_name_match.group(1)
                        
                        # Check if this method passed individual execution
                        individual_passed = method_name in individual_results and individual_results[method_name]
                        
                        # Check if this method had a timeout (we want to exclude timeout tests from final file)
                        failure_type = individual_failures.get(method_name, "assertion_error")
                        is_timeout = failure_type == "timeout"
                        
                        # Check if this method failed in group execution (we want to exclude flaky tests)
                        group_failed = method_name in group_failures and group_failures[method_name] is not None
                        
                        if individual_passed and not is_timeout and not group_failed:
                            passing_tests.append((scenario, test_method))
                            execution_results.append((scenario.title, True, 1))
                        else:
                            # Use the correct failure type from individual_failures
                            failure_types[method_name] = failure_type
                            execution_results.append((scenario.title, False, 1))
                            if is_timeout:
                                print_error(f"Test '{method_name}' timed out - excluding from final file")
                            elif group_failed:
                                # Test failed in group execution - silently exclude it
                                pass
                    else:
                        # If we can't extract method name, assume it failed
                        execution_results.append((scenario.title, False, 1))
                        print_error(f"Could not extract method name for test {idx}")
                
                # Update final_tests with only passing tests (excluding timeouts)
                final_tests = passing_tests
                
                # Show which tests were excluded due to timeouts
                timeout_tests = [method for method, failure_type in failure_types.items() if failure_type == "timeout"]
                if timeout_tests:
                    print(f"\n⚠️ Tests Excluded from Final File (Timeouts):")
                    for i, method_name in enumerate(timeout_tests, 1):
                        print(f"   {i}. {method_name}")
                
                # Print enhanced execution summary with failure types
                print("\n📊 General Test Execution Summary:")
                print("─" * 50)
                print(f"   Total tests executed: {total_tests_generated}")
                print(f"   ✅ Passing tests: {len(passing_tests)}")
                
                # Add failure breakdown to the failed count line
                if failure_types:
                    # Initialize failure_counts with all error types set to 0
                    failure_counts = {
                        "assertion_error": 0,
                        "runtime_error": 0,
                        "timeout": 0
                    }
                    # Count the actual failures
                    for failure_type in failure_types.values():
                        if failure_type in failure_counts:
                            failure_counts[failure_type] += 1
                    
                    failure_breakdown_parts = []
                    for failure_type, count in failure_counts.items():
                        readable_type = failure_type.replace("_", " ").title()
                        failure_breakdown_parts.append(f"{count} {readable_type}")
                    
                    failure_info = f" ({', '.join(failure_breakdown_parts)})"
                    print(f"   ❌ Failing tests: {total_tests_generated - len(passing_tests)}{failure_info}")
                    
                    # Add detailed failure information with renamed section
                    print(f"\n   📋 Failure Breakdown:")
                    for method_name, failure_type in failure_types.items():
                        if failure_type is not None:
                            readable_type = failure_type.replace("_", " ").title()
                            print(f"      • {method_name}: {readable_type}")
                        else:
                            print(f"      • {method_name}: Unknown Error")
                else:
                    print(f"   ❌ Failing tests: {total_tests_generated - len(passing_tests)}")
                
                # Log general test execution summary
                if failure_types:
                    # Convert failure_types to the format expected by JSON logger
                    failures_dict = {}
                    for method_name, failure_type in failure_types.items():
                        if failure_type is not None:
                            if failure_type == "assertion_error":
                                failures_dict[method_name] = "Assertion Error"
                            elif failure_type == "runtime_error":
                                failures_dict[method_name] = "Runtime Error"
                            elif failure_type == "timeout":
                                failures_dict[method_name] = "Timeout"
                            else:
                                failures_dict[method_name] = "Unknown Error"
                        else:
                            failures_dict[method_name] = "Unknown Error"
                    
                    json_logger.update_test_execution_summary(
                        total_tests=total_tests_generated,
                        passed=len(passing_tests),
                        assertion_errors=failure_counts["assertion_error"],
                        runtime_errors=failure_counts["runtime_error"],
                        timeout_errors=failure_counts["timeout"],
                        failures=failures_dict
                    )
                else:
                    # No failures
                    json_logger.update_test_execution_summary(
                        total_tests=total_tests_generated,
                        passed=len(passing_tests),
                        assertion_errors=0,
                        runtime_errors=0,
                        timeout_errors=0,
                        failures={}
                    )
        
                # Save the final test file with only passing tests to the repository
                if passing_tests:
                    # Assemble the final test file with only passing tests
                    final_test_file_content = method_info['test_scaffold']
                    
                    # Insert all passing test methods before the closing brace
                    last_brace_index = final_test_file_content.rfind("}")
                    if last_brace_index != -1:
                        # Build the test methods block
                        test_methods_block = []
                        for idx, (scenario, test_method) in enumerate(passing_tests, 1):
                            test_methods_block.append(f"    // Test {idx}: {scenario.title}")
                            test_methods_block.append(f"    // {scenario.description}")
                            # Add the test method with proper indentation
                            for line in test_method.splitlines():
                                if line.strip():
                                    test_methods_block.append("    " + line)
                                else:
                                    test_methods_block.append("")
                            test_methods_block.append("")  # Add blank line between methods
                        
                        # Insert the test methods before the closing brace
                        final_test_file_content = (
                            final_test_file_content[:last_brace_index] +
                            "\n" +
                            "\n".join(test_methods_block).rstrip() + "\n" +
                            final_test_file_content[last_brace_index:]
                        )
                        
                        # Create the new filename and class name for both repository and output
                        class_name = method_info['class_name']
                        method_name = method_info['method_name']
                        base_filename = f"{method_name}_{class_name}Test.java"
                        base_class_name = f"{method_name}_{class_name}Test"
                        
                        # Apply numbering if retention is enabled and file exists
                        if args.retain_test_suites:
                            new_filename, new_class_name = get_numbered_filename(base_filename, structured_output_dir)
                        else:
                            new_filename = base_filename
                            new_class_name = base_class_name
                        
                        # Store the actual filename used for later reference in Step 9
                        method_info['actual_output_filename'] = new_filename
                        
                        # Update the class name inside the file content
                        updated_content = final_test_file_content.replace(
                            f"public class {class_name}Test",
                            f"public class {new_class_name}"
                        )
                        
                        # Write the updated test file to the repository's test directory
                        # Update the test file path to use the new filename
                        new_test_file_path = test_file_path.parent / new_filename
                        new_test_file_path.write_text(updated_content, encoding='utf-8')
                        
                        # Also save the same file as an output artifact in our structured output directory
                        output_test_file = structured_output_dir / new_filename
                        output_test_file.write_text(updated_content, encoding='utf-8')
                        
                        # Update the test_file_path variable for later use
                        test_file_path = new_test_file_path
                        
                        # Verify the files were written correctly
                        if not test_file_path.exists() or test_file_path.stat().st_size == 0:
                            print_error("Failed to write test file to repository")
                            return
                            
                        if not output_test_file.exists() or output_test_file.stat().st_size == 0:
                            print_error("Failed to write test file to output directory")
                            return
                        
                        # Log final summary information
                        # Extract test method names from passing tests
                        final_test_names = []
                        for scenario, test_method in passing_tests:
                            method_name_match = re.search(r'public\s+void\s+(\w+)\s*\(', test_method)
                            if method_name_match:
                                final_test_names.append(method_name_match.group(1))
                        
                        # Count potential bug revealing tests (files in potential_bugs directory)
                        potential_bugs_dir = structured_output_dir.parent / "potential_bugs"
                        potential_bug_revealing_tests = 0
                        if potential_bugs_dir.exists():
                            potential_bug_revealing_tests = len(list(potential_bugs_dir.glob("*.java")))
                        
                        # Update final test suite in JSON logger
                        json_logger.update_final_test_suite(
                            tests_in_final_test_suite=len(passing_tests),
                            final_test_names=final_test_names
                        )
                        
                        # Count assertions in the final test suite
                        from utils.assertion_counter import count_assertions_in_final_test_suite
                        assertion_count = count_assertions_in_final_test_suite(structured_output_dir)
                        json_logger.update_assertion_count(assertion_count)
                    else:
                        print_warning("No passing tests to save - skipping coverage analysis")
        
        # Step 8: Coverage Analysis
        if final_tests:
            print_step("Coverage Analysis", 8)
            
            # Verify the test file exists in the repository before running coverage
            if not test_file_path.exists():
                print_error(f"Test file not found at {test_file_path} - cannot run coverage analysis")
                return
            
            print_success(f"Test file verified for coverage analysis: {test_file_path}")
            
            # Import coverage modules
            from coverage.jacoco_analyzer import (
                run_tests_with_coverage,
                safe_coverage_analysis,
                display_coverage_results,
                export_coverage_data
            )
            from coverage.report_server import (
                start_report_server,
                generate_report_urls,
                display_report_urls,
                find_html_report_directory,
                find_class_html_file,
                copy_html_reports_to_output
            )
            from coverage.coverage_config import (
                get_coverage_config,
                update_coverage_config
            )
            
            # Set default coverage configuration
            update_coverage_config(
                threshold=80.0,  # Default threshold
                serve_html=True,  # Always serve HTML reports
                report_port=8000  # Default port
            )
            
            coverage_config = get_coverage_config()
            
            # Run tests with coverage enabled
            print_success("Running tests with JaCoCo coverage enabled")
            
            # Use the actual class name from the saved test file
            # Extract the class name from the test file path
            test_class_name_from_file = test_file_path.stem  # This gets the filename without extension
            test_class_name = f"{method_info['package']}.{test_class_name_from_file}"
            
            coverage_success, coverage_output = run_tests_with_coverage(
                repo_path=repo_path,
                build_system=build_system,
                test_class=test_class_name,
                java_home=build_manager.java_home
            )
            
            if coverage_success:
                # Analyze coverage results
                coverage_results = safe_coverage_analysis(
                    repo_path=repo_path,
                    package=method_info['package'],
                    class_name=method_info['class_name'],
                    method_name=method_info['method_name'],
                    inner_class=method_info.get('inner_class')
                )
                
                if coverage_results:
                    # Display coverage metrics
                    display_coverage_results(coverage_results)
                    
                    # Log coverage results to JSON
                    # Find method coverage metrics (filter out class coverage)
                    method_metrics = None
                    for target_name, metrics in coverage_results.items():
                        if metrics.target_type == "method":
                            method_metrics = metrics
                            break
                    
                    if method_metrics:
                        # Log the coverage metrics to JSON
                        json_logger.update_coverage(
                            instructions_covered=method_metrics.instructions_covered,
                            instructions_total=method_metrics.total_instructions,
                            branches_covered=method_metrics.branches_covered,
                            branches_total=method_metrics.total_branches,
                            lines_covered=method_metrics.lines_covered,
                            lines_total=method_metrics.total_lines
                        )
                        print_success("Coverage metrics logged to JSON report")
                    else:
                        print_warning("No method coverage metrics found for JSON logging")
                    
                    # Start report server
                    html_root = find_html_report_directory(repo_path)
                    server = None  # Initialize server variable
                    if html_root:
                        # Copy HTML reports to output directory to prevent them from changing when commit changes
                        copied_html_root = copy_html_reports_to_output(html_root, structured_output_dir.parent)
                        if copied_html_root:
                            server = start_report_server(copied_html_root, coverage_config.report_port)
                        else:
                            # Fallback to original location if copy fails
                            server = start_report_server(html_root, coverage_config.report_port)
                        
                        if server:
                            # Try to find the specific class HTML file
                            class_html_file = find_class_html_file(repo_path, method_info['class_name'], method_info.get('inner_class'))
                            
                            # Generate and display report URLs
                            urls = generate_report_urls(
                                repo_path=repo_path,
                                package=method_info['package'],
                                class_name=method_info['class_name'],
                                port=coverage_config.report_port,
                                inner_class=method_info.get('inner_class')
                            )
                            display_report_urls(urls)
                        else:
                            print_warning("Failed to start HTML report server")
                    else:
                        print_warning("HTML report directory not found")
                else:
                    print_warning("No coverage data found for target class/method")
            else:
                print_error("Failed to generate coverage report")
        
        # Step 9: Final File Assembly (only with passing tests)
        if final_tests:
            print_step("Final File Assembly", 9)
            print_success(f"Final test file assembled with {len(final_tests)} passing test methods")
            
            # The test file has already been saved to the repository in Step 7
            # Just display the final content for verification
            if test_file_path.exists():
                final_content = test_file_path.read_text(encoding='utf-8')
                print("\n📝 Final Test File Content:")
                print("─" * 38)
                print(final_content)
                print("─" * 38)
                print_success(f"Repository test file: {test_file_path}")
                
                # Also show the output artifact location
                # Use the actual filename that was stored in Step 7
                if 'actual_output_filename' in method_info:
                    output_filename = method_info['actual_output_filename']
                else:
                    # Fallback: reconstruct the filename (for backward compatibility)
                    class_name = method_info['class_name']
                    method_name = method_info['method_name']
                    base_filename = f"{method_name}_{class_name}Test.java"
                    
                    # Apply numbering if retention is enabled and file exists
                    if args.retain_test_suites:
                        output_filename, _ = get_numbered_filename(base_filename, structured_output_dir)
                    else:
                        output_filename = base_filename
                
                output_test_file = structured_output_dir / output_filename
                
                if output_test_file.exists():
                    print_success(f"Output artifact: {output_test_file}")
                else:
                    print_warning("Output artifact not found")
            else:
                print_error("Test file not found for display")
        else:
            print_warning("No successful test methods were generated")
            
            # Count assertions even when no tests are generated (should be 0)
            from utils.assertion_counter import count_assertions_in_final_test_suite
            assertion_count = count_assertions_in_final_test_suite(structured_output_dir)
            json_logger.update_assertion_count(assertion_count)
        
        # Get LLM metrics and update JSON logger
        llm_metrics = llm_client.get_metrics()
        json_logger.update_llm_metrics(llm_metrics["request_count"], llm_metrics["total_response_time"])
        
        # Step 10: Bug Assessment (always run regression detection)
        if args.fix_commit_hash:
            print_step("Bug Assessment", 10)
            print_success(f"Testing against fix commit: {args.fix_commit_hash}")
            
            # Import bug assessment module
            from utils.bug_assessment import test_bug_assessment, display_bug_assessment_results
            
            try:
                # Check if there are potential bugs to test
                potential_bugs_dir = structured_output_dir.parent / "potential_bugs"
                run_potential_bugs = potential_bugs_dir.exists() and any(potential_bugs_dir.glob("*.java"))
                
                if run_potential_bugs:
                    print_success(f"Found {len(list(potential_bugs_dir.glob('*.java')))} potential bug-revealing tests")
                else:
                    print_warning("No potential bug-revealing tests found - running only regression detection")
                
                # Run unified bug assessment (regression detection + optional potential bugs)
                regression_results, bug_results = test_bug_assessment(
                    repo_path=repo_path,
                    fix_commit_hash=args.fix_commit_hash,
                    potential_bugs_dir=potential_bugs_dir,
                    build_system=build_system,
                    package=method_info['package'],
                    repo_url=args.repo_url,
                    output_dir=structured_output_dir,
                    run_potential_bugs=run_potential_bugs,
                    json_logger=json_logger
                )
                
                # Display regression results (always shown)
                print(f"\n📊 Regression Detection Results:")
                print("─" * 50)
                regression_detected = regression_results.get('regression_detected', False)
                total_tests = regression_results.get('total_tests', 0)
                passed_tests = regression_results.get('passed', 0)
                failed_tests = regression_results.get('failed', 0)
                failing_tests = regression_results.get('failures', [])
                
                print(f"   Regression detected: {'Yes' if regression_detected else 'No'}")
                print(f"   Total tests: {total_tests}")
                print(f"   ✅ Passed: {passed_tests}")
                print(f"   ❌ Failed: {failed_tests}")
                
                if failing_tests:
                    print(f"   📋 Failing tests: {', '.join(failing_tests)}")
                
                # Display potential bugs results (only if tests were run)
                if run_potential_bugs and bug_results:
                    display_bug_assessment_results(bug_results)
                    
                    # Log bug assessment results to JSON (without regression_detected)
                    potential_bug_revealing_tests = len(list(potential_bugs_dir.glob("*.java")))
                    bug_revealed = any(result == "bug_revealed" for result in bug_results.values())
                    
                    # Collect names of tests that revealed bugs
                    bug_revealing_test_names = []
                    if bug_revealed:
                        for test_file, result in bug_results.items():
                            if result == "bug_revealed":
                                bug_revealing_test_names.append(test_file)
                    
                    json_logger.update_bug_assessment(potential_bug_revealing_tests, bug_revealed, bug_revealing_test_names, bug_results)
                else:
                    # Log empty bug assessment results (without regression_detected)
                    json_logger.update_bug_assessment(0, False, [], {})
                    
            except Exception as e:
                print_error(f"Bug assessment failed: {str(e)}")
                print_warning("Continuing with normal pipeline completion")
        else:
            print_warning("No fix commit provided - cannot run regression detection or test if assertion failures reveal real bugs")
        
        # Save JSON report with total pipeline time (AFTER all steps)
        reports_dir = structured_output_dir.parent / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        base_json_filename = f"{repo_name}_report.json"
        if args.retain_test_suites:
            json_filename = get_numbered_json_report_filename(base_json_filename, reports_dir)
        else:
            json_filename = base_json_filename
        json_logger.save_report(reports_dir, json_filename)
        return
        
    except Exception as e:
        print(f"Error generating test suite: {str(e)}")
        raise

if __name__ == "__main__":
    main()
