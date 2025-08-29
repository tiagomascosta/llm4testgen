import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import time


class TestGenerationLogger:
    """
    Logger for building structured JSON reports during test generation.
    
    This class incrementally builds a JSON structure that captures all relevant
    information about the test generation process for research analysis.
    """
    
    def __init__(self, repo_name: Optional[str] = None, target_class: Optional[str] = None, target_method: Optional[str] = None):
        """
        Initialize the logger with basic repository information.
        
        Args:
            repo_name: Name of the repository (can be None if not available)
            target_class: Name of the target class (can be None if not available)
            target_method: Name of the target method (can be None if not available)
        """
        self.start_time = time.time()
        
        # Initialize the JSON structure
        self.data = {
            "repository": repo_name,
            "repository_url": None,
            "commit_hash": None,
            "target_class": target_class,
            "target_method": target_method,
            "build_system": None,
            "junit_version": None,
            "java_repo_version": None,
            "java_version_used": None,
            "dependency_analysis": None,
            
            "llm_models": {
                "code_tasks": None,
                "non_code_tasks": None
            },
            
            "cli_options": {
                "max_fix_attempts": None,
                "max_compile_fix_examples": None,
                "max_scaffold_examples": None
            },
            
            "test_scenarios": {
                "raw_scenarios": None,
                "raw_descriptions": [],
                "total_clustered": None,
                "themes": []
            },
            
            "test_generation": {
                "total_scenarios": None,
                "scenarios": {}
            },
            
            "test_execution": {
                "individual": {
                    "total_tests": None,
                    "passed": None,
                    "assertion_errors": None,
                    "runtime_errors": None,
                    "timeout_errors": None,
                    "failures": {},
                    "tests": {}
                },
                "group": {
                    "total_tests": None,
                    "passed": None,
                    "assertion_errors": None,
                    "runtime_errors": None,
                    "timeout_errors": None,
                    "failures": {}
                },
                "summary": {
                    "total_tests": None,
                    "passed": None,
                    "assertion_errors": None,
                    "runtime_errors": None,
                    "timeout_errors": None,
                    "failures": {}
                }
            },
            
            "coverage": {
                "method": target_method,
                "instructions_covered": None,
                "instructions_total": None,
                "branches_covered": None,
                "branches_total": None,
                "lines_covered": None,
                "lines_total": None
            },
            
            "final_test_suite": {
                "tests_in_final_test_suite": None,
                "final_test_names": [],
                "assertions": None
            },
            
            "bug_assessment": {
                "potential_bug_revealing_tests": None,
                "bug_revealed": None,
                "bug_revealing_test_names": [],
                "error_types": {
                    "assertion_error": 0,
                    "runtime_error": 0,
                    "timeout": 0
                }
            },
            
            "regression_detection": {
                "regression_detected": None,
                "total_tests": None,
                "passed": None,
                "failed": None,
                "failures": []
            },
            
            "llm_requests": None,
            "elapsed_time": None,
            "llm_response_time": None
        }
    
    def update_repository_info(self, repo_url: str, commit_hash: str, build_system: str):
        """Update repository information."""
        self.data["repository_url"] = repo_url
        self.data["commit_hash"] = commit_hash
        self.data["build_system"] = build_system
    
    def update_environment_info(self, java_repo_version: str, java_version_used: str, junit_version: int):
        """Update environment information."""
        self.data["java_repo_version"] = java_repo_version
        self.data["java_version_used"] = java_version_used
        self.data["junit_version"] = junit_version
    
    def update_dependency_analysis(self, dependency_count: int):
        """Update dependency analysis information."""
        self.data["dependency_analysis"] = dependency_count
    
    def update_llm_models(self, code_tasks_model: str, non_code_tasks_model: str):
        """Update LLM model information."""
        self.data["llm_models"]["code_tasks"] = code_tasks_model
        self.data["llm_models"]["non_code_tasks"] = non_code_tasks_model
    
    def update_cli_options(self, max_fix_attempts: int, max_compile_fix_examples: int, max_scaffold_examples: int):
        """Update CLI options."""
        self.data["cli_options"]["max_fix_attempts"] = max_fix_attempts
        self.data["cli_options"]["max_compile_fix_examples"] = max_compile_fix_examples
        self.data["cli_options"]["max_scaffold_examples"] = max_scaffold_examples
    
    def add_raw_scenarios(self, scenarios: List[str]):
        """Add raw test scenarios."""
        self.data["test_scenarios"]["raw_scenarios"] = len(scenarios)
        self.data["test_scenarios"]["raw_descriptions"] = scenarios
    
    def update_themes(self, themes: List[Dict[str, str]]):
        """Update clustered themes."""
        self.data["test_scenarios"]["total_clustered"] = len(themes)
        self.data["test_scenarios"]["themes"] = themes
    
    def add_test_generation_scenario(self, scenario_name: str, compiled: bool, 
                                   compiled_on_first_attempt: bool, fix_attempts: int,
                                   initial_compile_errors: int = 0):
        """Add test generation result for a specific scenario."""
        self.data["test_generation"]["scenarios"][scenario_name] = {
            "compiled": compiled,
            "compiled_on_first_attempt": compiled_on_first_attempt,
            "fix_attempts": fix_attempts,
            "initial_compile_errors": initial_compile_errors
        }
        
        # Update total count
        self.data["test_generation"]["total_scenarios"] = len(self.data["test_generation"]["scenarios"])
    
    def update_test_execution_individual(self, total_tests: int, passed: int, 
                                       assertion_errors: int, runtime_errors: int, 
                                       timeout_errors: int = 0, failures: Dict[str, str] = None):
        """Update individual test execution results."""
        # Preserve the tests section if it exists
        existing_tests = self.data["test_execution"]["individual"].get("tests", {})
        
        self.data["test_execution"]["individual"] = {
            "total_tests": total_tests,
            "passed": passed,
            "assertion_errors": assertion_errors,
            "runtime_errors": runtime_errors,
            "timeout_errors": timeout_errors,
            "failures": failures or {},
            "tests": existing_tests  # Preserve the tests section
        }
    
    def initialize_individual_test_entry(self, test_name: str):
        """Initialize an entry for a test that didn't use runtime fix."""
        self.data["test_execution"]["individual"]["tests"][test_name] = {
            "runtime_fix_attempted": False,
            "runtime_fix_successful": None,
            "attempts_made": None,
            "final_outcome": None
        }
    
    def add_individual_test_runtime_fix_result(self, test_name: str, 
                                             runtime_fix_attempted: bool,
                                             runtime_fix_successful: bool = None,
                                             attempts_made: int = None,
                                             final_outcome: str = None):
        """Add runtime fix result for a specific test."""
        self.data["test_execution"]["individual"]["tests"][test_name] = {
            "runtime_fix_attempted": runtime_fix_attempted,
            "runtime_fix_successful": runtime_fix_successful,
            "attempts_made": attempts_made,
            "final_outcome": final_outcome
        }
    
    def update_test_execution_group(self, total_tests: int, passed: int, 
                                  assertion_errors: int, runtime_errors: int, 
                                  timeout_errors: int = 0, failures: Dict[str, str] = None):
        """Update group test execution results."""
        self.data["test_execution"]["group"] = {
            "total_tests": total_tests,
            "passed": passed,
            "assertion_errors": assertion_errors,
            "runtime_errors": runtime_errors,
            "timeout_errors": timeout_errors,
            "failures": failures or {}
        }
    
    def update_test_execution_summary(self, total_tests: int, passed: int, 
                                    assertion_errors: int, runtime_errors: int, 
                                    timeout_errors: int = 0, failures: Dict[str, str] = None):
        """Update general test execution summary."""
        self.data["test_execution"]["summary"] = {
            "total_tests": total_tests,
            "passed": passed,
            "assertion_errors": assertion_errors,
            "runtime_errors": runtime_errors,
            "timeout_errors": timeout_errors,
            "failures": failures or {}
        }
    
    def update_coverage(self, instructions_covered: int, instructions_total: int,
                       branches_covered: int, branches_total: int,
                       lines_covered: int, lines_total: int):
        """Update coverage information."""
        self.data["coverage"]["instructions_covered"] = instructions_covered
        self.data["coverage"]["instructions_total"] = instructions_total
        self.data["coverage"]["branches_covered"] = branches_covered
        self.data["coverage"]["branches_total"] = branches_total
        self.data["coverage"]["lines_covered"] = lines_covered
        self.data["coverage"]["lines_total"] = lines_total
    
    def update_final_test_suite(self, tests_in_final_test_suite: int, final_test_names: List[str]):
        """Update final test suite information."""
        self.data["final_test_suite"]["tests_in_final_test_suite"] = tests_in_final_test_suite
        self.data["final_test_suite"]["final_test_names"] = final_test_names
    
    def update_bug_assessment(self, potential_bug_revealing_tests: int, bug_revealed: bool, bug_revealing_test_names: List[str] = None, bug_results: Dict[str, str] = None):
        """Update bug assessment information."""
        self.data["bug_assessment"]["potential_bug_revealing_tests"] = potential_bug_revealing_tests
        self.data["bug_assessment"]["bug_revealed"] = bug_revealed
        self.data["bug_assessment"]["bug_revealing_test_names"] = bug_revealing_test_names or []
        
        # Count error types from bug results
        error_types = {
            "assertion_error": 0,
            "runtime_error": 0,
            "timeout": 0
        }
        
        if bug_results:
            for result in bug_results.values():
                if result in error_types:
                    error_types[result] += 1
        
        self.data["bug_assessment"]["error_types"] = error_types
    
    def update_regression_detection(self, regression_detected: bool, total_tests: int, 
                                  passed: int, failed: int, failures: List[str]):
        """Update regression detection information."""
        self.data["regression_detection"]["regression_detected"] = regression_detected
        self.data["regression_detection"]["total_tests"] = total_tests
        self.data["regression_detection"]["passed"] = passed
        self.data["regression_detection"]["failed"] = failed
        self.data["regression_detection"]["failures"] = failures
    
    def increment_llm_requests(self, count: int = 1):
        """Increment LLM request counter."""
        self.data["llm_requests"] += count
    
    def update_llm_metrics(self, request_count: int, total_response_time: float):
        """Update LLM metrics from OllamaClient."""
        self.data["llm_requests"] = request_count
        self.data["llm_response_time"] = total_response_time
    
    def update_assertion_count(self, assertion_count: int):
        """Update assertion count in the final test suite."""
        self.data["final_test_suite"]["assertions"] = assertion_count
    
    def save_report(self, output_dir: Path, filename: str = None):
        """
        Save the JSON report to the output directory.
        
        Args:
            output_dir: Directory where to save the report
            filename: Optional filename for the report
        """
        # Calculate final timing
        self.data["elapsed_time"] = time.time() - self.start_time
        
        # Create filename based on repository name if not provided
        repo_name = self.data["repository"]
        if filename is None:
            filename = f"{repo_name}_report.json"
        file_path = output_dir / filename
        
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save JSON with pretty formatting
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        
        return file_path
    
    def get_current_data(self) -> Dict[str, Any]:
        """Get the current JSON data structure."""
        return self.data.copy()
    
    def update_field(self, field_path: str, value: Any):
        """
        Update a specific field in the JSON structure using dot notation.
        
        Args:
            field_path: Path to the field (e.g., "test_scenarios.raw_scenarios")
            value: Value to set
        """
        keys = field_path.split('.')
        current = self.data
        
        # Navigate to the parent of the target field
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set the final field
        current[keys[-1]] = value 