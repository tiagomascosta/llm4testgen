#!/usr/bin/env python3
"""
Generate Commands Script - Creates command list from sample_config.json
Reads the JSON configuration and generates the individual commands that would be run
by run_experiment.py, saving them to a text file for manual execution or review.
"""

import json
from pathlib import Path

def generate_commands_from_config(config_path, output_path):
    """
    Generate individual commands from the JSON configuration file.
    
    Args:
        config_path: Path to the JSON configuration file
        output_path: Path to save the generated commands
    """
    commands = []
    
    # Load the configuration
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    print(f"Loaded {len(config)} repositories from {config_path}")
    
    # Generate command for each repository
    for i, repo_config in enumerate(config, 1):
        repo_url = repo_config['repo_url']
        commit_hash = repo_config['commit_hash']
        fix_commit_hash = repo_config['fix_commit_hash']
        method = repo_config['method']
        
        # Extract repository name from URL for output directory
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        
        # Generate the command (using defaults for output-dir, models, examples, and fix attempts)
        command = f"""python -m generate_test_suite \\
    --repo-url {repo_url} \\
    --commit-hash {commit_hash} \\
    --fix-commit-hash {fix_commit_hash} \\
    --method {method}"""
        
        commands.append(f"Command {i}\n{'-' * 50}\n{command}\n")
    
    # Write all commands to file
    with open(output_path, 'w') as f:
        f.write('\n'.join(commands))
    
    print(f"Generated {len(commands)} commands")
    print(f"Commands saved to: {output_path}")

def main():
    """Generate commands for both sample and subsample configurations."""
    
    # Generate commands for sample_config.json
    sample_config_path = Path(__file__).parent / "sample_config.json"
    sample_output_path = Path(__file__).parent / "sample_commands.txt"
    
    if sample_config_path.exists():
        print("Generating commands for sample_config.json...")
        generate_commands_from_config(sample_config_path, sample_output_path)
    else:
        print(f"Warning: {sample_config_path} not found")
    
    print()
    
    # Generate commands for subsample_config.json
    subsample_config_path = Path(__file__).parent / "subsample_config.json"
    subsample_output_path = Path(__file__).parent / "subsample_commands.txt"
    
    if subsample_config_path.exists():
        print("Generating commands for subsample_config.json...")
        generate_commands_from_config(subsample_config_path, subsample_output_path)
    else:
        print(f"Warning: {subsample_config_path} not found")

if __name__ == "__main__":
    main()
