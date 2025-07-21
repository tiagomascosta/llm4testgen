import argparse
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def validate_repo_args(args: argparse.Namespace) -> Tuple[Optional[str], Optional[str]]:
    """
    Validate repository-related arguments.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Tuple of (repo_url, local_path)
        
    Raises:
        ValueError: If arguments are invalid
    """
    if args.repo_url and args.local_path:
        raise ValueError("Cannot specify both --repo-url and --local-path")
    if args.commit_hash and not args.repo_url:
        raise ValueError("--commit-hash can only be used with --repo-url")
        
    return args.repo_url, args.local_path

def validate_method_signature(method: str) -> str:
    """
    Validate the method signature format.
    
    Args:
        method: Method signature in format package.ClassName#methodName
        
    Returns:
        Validated method signature
        
    Raises:
        ValueError: If the method signature is invalid
    """
    if not method or '#' not in method:
        raise ValueError("Method signature must be in format: package.ClassName#methodName")
    
    class_part, method_part = method.split('#', 1)
    if not class_part or not method_part:
        raise ValueError("Invalid method signature format")
        
    return method

def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description='Generate test suites for Java projects using LLMs',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Repository source group (mutually exclusive)
    repo_group = parser.add_mutually_exclusive_group(required=True)
    repo_group.add_argument(
        '--repo-url',
        type=str,
        help='GitHub repository URL to clone'
    )
    repo_group.add_argument(
        '--local-path',
        type=str,
        help='Path to local repository'
    )
    
    # Required arguments
    parser.add_argument(
        '--method',
        type=str,
        required=True,
        help='Target method to generate tests for (format: package.ClassName#methodName)'
    )
    
    # Optional arguments
    parser.add_argument(
        '--commit-hash',
        type=str,
        help='Specific commit hash to checkout (only used with --repo-url)'
    )
    parser.add_argument(
        '--fix-commit-hash',
        type=str,
        help='Commit hash of the bug fix to test against for bug assessment'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='output',
        help='Directory to store generated test suites'
    )
    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO',
        help='Set the logging level'
    )
    
    # Model selection arguments
    parser.add_argument(
        '--code-model',
        type=str,
        default='qwen2.5-coder:32b',
        help='Model to use for code-related tasks (e.g. test generation). Reasoning models like deepseek-r1 will automatically enable thinking capabilities.'
    )
    parser.add_argument(
        '--non-code-model',
        type=str,
        default='qwen2.5-coder:32b',
        help='Model to use for non-code tasks (e.g. scenario generation). Reasoning models like deepseek-r1 will automatically enable thinking capabilities.'
    )
    
    # Compile-fix loop configuration arguments
    parser.add_argument(
        '--max-fix-attempts',
        type=int,
        default=7,
        help='Maximum number of compile-fix loop iterations'
    )
    parser.add_argument(
        '--max-compile-fix-examples',
        type=int,
        default=3,
        help='Maximum number of examples to include in compile-fix prompts'
    )
    parser.add_argument(
        '--max-scaffold-examples',
        type=int,
        default=100,
        help='Maximum number of examples to include in test generation scaffold'
    )
    
    # Runtime-fix loop configuration arguments
    parser.add_argument(
        '--max-runtime-fix-attempts',
        type=int,
        default=7,
        help='Maximum number of runtime-fix loop iterations'
    )
    parser.add_argument(
        '--max-runtime-fix-examples',
        type=int,
        default=5,
        help='Maximum number of examples to include in runtime-fix prompts'
    )
    
    # Output retention arguments
    parser.add_argument(
        '--retain-test-suites',
        action='store_true',
        default=False,
        help='Retain past test suites in the output folder (default: false - delete existing test suites)'
    )
    
    args = parser.parse_args()
    
    validate_repo_args(args)
    args.method = validate_method_signature(args.method)
    
    # Convert paths to Path objects
    args.output_dir = Path(args.output_dir)
    if args.local_path:
        args.local_path = Path(args.local_path)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    return args

def main():
    """Main entry point for the CLI."""
    try:
        args = parse_args()
        # The actual work is done in generate_test_suite.py
        logger.info("Arguments parsed successfully")
    except Exception as e:
        logger.error(f"Error parsing arguments: {str(e)}")
        raise 