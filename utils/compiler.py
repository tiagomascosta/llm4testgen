"""
Java compilation utilities for the test suite generator.
"""

import subprocess
import tempfile
import logging
from pathlib import Path
from typing import List, Optional, Union, Tuple
import os
from config import test_config
from init.build import _ensure_sdkman_installed, _install_jdk_with_sdkman
from .compile_java_file import compile_java_file, has_spring_javaformat_plugin, verify_compiled_class

logger = logging.getLogger(__name__)

# Re-export compile_java_file for backward compatibility
__all__ = ['compile_java_file', 'get_project_classpath', 'assemble_and_compile_test']

def get_project_classpath(repo_path: Path) -> List[str]:
    """
    Get the complete classpath for a project including dependencies.
    
    Args:
        repo_path: Path to the repository root
        
    Returns:
        List of classpath entries
    """
    classpath = []
    
    # Add compiled classes
    if (repo_path / "target").exists():  # Maven
        classpath.extend([
            str(repo_path / "target" / "classes"),
            str(repo_path / "target" / "test-classes")
        ])
    elif (repo_path / "build").exists():  # Gradle
        classpath.extend([
            str(repo_path / "build" / "classes" / "java" / "main"),
            str(repo_path / "build" / "classes" / "java" / "test")
        ])
    
    # Add dependencies
    if (repo_path / "pom.xml").exists():  # Maven
        try:
            result = subprocess.run(
                ["mvn", "dependency:build-classpath", "-Dmdep.outputFile=/tmp/classpath.txt"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            if (Path("/tmp/classpath.txt")).exists():
                with open("/tmp/classpath.txt") as f:
                    classpath.extend(f.read().strip().split(":"))
        except Exception as e:
            logger.warning(f"Failed to get Maven classpath: {e}")
            
    elif any(repo_path.glob("build.gradle*")):  # Gradle
        try:
            result = subprocess.run(
                ["./gradlew", "printClasspath"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            classpath.extend(result.stdout.strip().split(":"))
        except Exception as e:
            logger.warning(f"Failed to get Gradle classpath: {e}")
    
    return classpath

def assemble_and_compile_test(
    scaffold: str,
    test_method: str,
    repo_path: Path,
    java_home: str = None
) -> Tuple[bool, str, str]:
    """
    Assemble a test method into the scaffold, save it temporarily, and compile it.
    
    Args:
        scaffold: The test class scaffold
        test_method: The test method to insert
        repo_path: Root directory of the repository
        java_home: Optional path to JAVA_HOME
        
    Returns:
        Tuple of (success, assembled_source, compilation_errors)
    """
    # Find the last closing brace in the scaffold
    last_brace_pos = scaffold.rfind('}')
    if last_brace_pos == -1:
        print("❌ Could not find closing brace in scaffold")
        return False, "Could not find closing brace in scaffold", "Could not find closing brace in scaffold"
        
    # Insert the test method before the last brace
    assembled_source = scaffold[:last_brace_pos] + '\n' + test_method + '\n' + scaffold[last_brace_pos:]
    
    # Get the test file path from config
    test_file_path = test_config.get_test_file_path()
    if not test_file_path:
        print("❌ Could not find test file path in config")
        return False, assembled_source, "Could not find test file path in config"
    
    test_file = Path(test_file_path)
    
    try:
        # Save the assembled source
        test_file.write_text(assembled_source)
        
        # Compile and capture the output directly
        success, compilation_errors = compile_and_capture_output(test_file, repo_path, java_home)
        
        # Clean up - always remove the file after compilation attempt
        if test_file.exists():
            test_file.unlink()
        
        return success, assembled_source, compilation_errors
    except Exception as e:
        print(f"❌ Error during test assembly/compilation: {str(e)}")
        # Clean up on error
        if test_file.exists():
            test_file.unlink()
        return False, assembled_source, f"Error during test assembly/compilation: {str(e)}" 

def compile_and_capture_output(test_file: Path, repo_path: Path, java_home: str = None) -> Tuple[bool, str]:
    """
    Compile a Java test file and capture the output.
    
    Args:
        test_file: Path to the test file
        repo_path: Path to the repository root
        java_home: Optional path to JAVA_HOME
        
    Returns:
        Tuple of (success, compilation_output)
    """
    # Get Java version and path from global config
    java_version = test_config.get_java_version()
    java_path = test_config.get_java_path()
    
    if not java_path:
        logger.error("Java path not set in test_config")
        return False, "Java path not set in test_config"
        
    # Determine build system
    is_maven = (repo_path / 'pom.xml').exists()
    
    if is_maven:
        # Maven command - include skip flags to avoid formatting issues
        cmd = [
            "mvn",
            "compile",
            "test-compile",
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
            
        # Basic Gradle command
        cmd = [
            gradle_cmd,
            "compileTestJava",
            "--no-daemon"
        ]
            
    # Run compilation and capture output
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
        
        # Format the compilation output
        compilation_output = f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        
        # Check if compilation succeeded
        build_success = "BUILD SUCCESSFUL" in result.stdout if not is_maven else "BUILD SUCCESS" in result.stdout
        class_found = verify_compiled_class(test_file, repo_path)
        
        if build_success and class_found:
            print(f"   ✅ Compilation successful")
            return True, compilation_output
        else:
            print("   ❌ Compilation failed")
            return False, compilation_output
            
    except subprocess.CalledProcessError as e:
        error_output = f"Compilation failed with error: {str(e)}"
        print(f"   ❌ {error_output}")
        return False, error_output 