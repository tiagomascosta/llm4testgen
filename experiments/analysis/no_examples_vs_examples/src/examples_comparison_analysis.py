#!/usr/bin/env python3
"""
Examples vs No Examples Comparison Analysis Script
Creates publication-quality plots for master's thesis showing:
- Left Figure: Fix Attempts and First Try Compilation Rate
- Right Figure: Coverage Metrics Comparison

Experiments:
- Experiment 3: No examples in prompts
- Experiment 4: Examples in prompts
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Set up publication-quality plotting style
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("husl")

# Configure matplotlib for LaTeX compatibility
plt.rcParams.update({
    'font.family': 'DejaVu Sans',  # Use available font
    'font.size': 12,
    'axes.labelsize': 12,
    'axes.titlesize': 14,
    'xtick.labelsize': 14,
    'ytick.labelsize': 14,
    'legend.fontsize': 10,
    'figure.titlesize': 16,
    'text.usetex': False,  # Set to True if you have LaTeX installed
    'axes.grid': True,
    'grid.alpha': 0.3,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.1,
})

def load_experiment_data(experiment_path):
    """Load and clean experiment data from Excel file.
    
    Data structure: 50 rows = 10 repositories × 5 runs each
    First 5 rows = repo 1, next 5 rows = repo 2, etc.
    """
    df = pd.read_excel(experiment_path)

    # Extract coverage data (columns AB=27, AC=28, AD=29)
    # Skip header row (index 0)
    line_coverage_raw = pd.to_numeric(df.iloc[1:, 27], errors='coerce').dropna()
    branch_coverage_raw = pd.to_numeric(df.iloc[1:, 28], errors='coerce').dropna()
    instruction_coverage_raw = pd.to_numeric(df.iloc[1:, 29], errors='coerce').dropna()

    # Extract test generation data
    # Column S (index 18): Normal scenarios generated
    # Column AO (index 40): Bug hunting scenarios generated
    normal_scenarios = pd.to_numeric(df.iloc[1:, 18], errors='coerce').fillna(0)
    bug_hunting_scenarios = pd.to_numeric(df.iloc[1:, 40], errors='coerce').fillna(0)
    
    # Extract compilation data
    # Column U (index 20): Compiled normal scenarios
    # Column AQ (index 42): Compiled bug hunting scenarios
    compiled_normal = pd.to_numeric(df.iloc[1:, 20], errors='coerce').fillna(0)
    compiled_bug_hunting = pd.to_numeric(df.iloc[1:, 42], errors='coerce').fillna(0)
    
    # Extract fix attempts data
    # Column T (index 19): Fix attempts for normal scenarios
    # Column AP (index 41): Fix attempts for bug hunting scenarios
    fix_attempts_normal = pd.to_numeric(df.iloc[1:, 19], errors='coerce').fillna(0)
    fix_attempts_bug_hunting = pd.to_numeric(df.iloc[1:, 41], errors='coerce').fillna(0)
    
    # Extract first try compilation data
    # Column AV (index 47): First try compilations (already summed)
    first_try_compilations = pd.to_numeric(df.iloc[1:, 47], errors='coerce').fillna(0)

    # Calculate total test cases
    total_test_cases = normal_scenarios + bug_hunting_scenarios
    
    # Calculate total compiled tests
    total_compiled = compiled_normal + compiled_bug_hunting
    
    # Calculate compilation rate
    compilation_rate_raw = np.where(total_test_cases > 0,
                                   (total_compiled / total_test_cases) * 100,
                                   0)
    
    # Calculate total fix attempts
    total_fix_attempts = fix_attempts_normal + fix_attempts_bug_hunting
    
    # Calculate average fix attempts per method
    # Avoid division by zero
    avg_fix_attempts_per_method = np.where(total_test_cases > 0,
                                          total_fix_attempts / total_test_cases,
                                          0)
    
    # Calculate first try compilation rate
    first_try_compilation_rate = np.where(total_test_cases > 0,
                                        (first_try_compilations / total_test_cases) * 100,
                                        0)

    # Calculate repository-level averages (10 repos × 5 runs each)
    repo_averages = []
    
    for repo_idx in range(10):  # 10 repositories
        start_idx = repo_idx * 5
        end_idx = start_idx + 5
        
        # Get data for this repository (5 runs)
        repo_line = line_coverage_raw.iloc[start_idx:end_idx]
        repo_branch = branch_coverage_raw.iloc[start_idx:end_idx]
        repo_instruction = instruction_coverage_raw.iloc[start_idx:end_idx]
        repo_compilation_rate = pd.Series(compilation_rate_raw[start_idx:end_idx])
        repo_avg_fix_attempts = pd.Series(avg_fix_attempts_per_method[start_idx:end_idx])
        repo_first_try_rate = pd.Series(first_try_compilation_rate[start_idx:end_idx])
        
        # Calculate average for this repository
        repo_avg = {
            'line_coverage': repo_line.mean(),
            'branch_coverage': repo_branch.mean(),
            'instruction_coverage': repo_instruction.mean(),
            'compilation_rate': repo_compilation_rate.mean(),
            'avg_fix_attempts_per_method': repo_avg_fix_attempts.mean(),
            'first_try_compilation_rate': repo_first_try_rate.mean()
        }
        repo_averages.append(repo_avg)
    
    # Convert to pandas Series for compatibility with existing code
    line_coverage = pd.Series([avg['line_coverage'] for avg in repo_averages])
    branch_coverage = pd.Series([avg['branch_coverage'] for avg in repo_averages])
    instruction_coverage = pd.Series([avg['instruction_coverage'] for avg in repo_averages])
    compilation_rate = pd.Series([avg['compilation_rate'] for avg in repo_averages])
    avg_fix_attempts_per_method = pd.Series([avg['avg_fix_attempts_per_method'] for avg in repo_averages])
    first_try_compilation_rate = pd.Series([avg['first_try_compilation_rate'] for avg in repo_averages])

    return {
        'line_coverage': line_coverage,
        'branch_coverage': branch_coverage,
        'instruction_coverage': instruction_coverage,
        'compilation_rate': compilation_rate,
        'avg_fix_attempts_per_method': avg_fix_attempts_per_method,
        'first_try_compilation_rate': first_try_compilation_rate
    }

def calculate_statistics(data):
    """Calculate mean and standard deviation for metrics."""
    return {
        'mean': data.mean(),
        'std': data.std(),
        'count': len(data)
    }

def create_fix_attempts_plot(experiments_data, output_path):
    """Create the Fix Attempts and First Try Compilation Rate plot."""
    fig, ax = plt.subplots(figsize=(7, 6.5))
    
    # Data for grouped bars
    categories = ['No Examples', 'Examples']
    
    # Extract data
    no_examples_fix_attempts = calculate_statistics(experiments_data[3]['avg_fix_attempts_per_method'])
    examples_fix_attempts = calculate_statistics(experiments_data[4]['avg_fix_attempts_per_method'])
    
    no_examples_first_try = calculate_statistics(experiments_data[3]['first_try_compilation_rate'])
    examples_first_try = calculate_statistics(experiments_data[4]['first_try_compilation_rate'])
    
    # Set up bar positions
    x = np.arange(len(categories))
    width = 0.35
    
    # Create grouped bars
    bars1 = ax.bar(x - width/2, 
                   [no_examples_fix_attempts['mean'], examples_fix_attempts['mean']], 
                   width, 
                   label='Avg Compile Fix Attempts per Test',
                   color='#9467bd',  # Purple for fix attempts
                   alpha=0.8,
                   zorder=100)  # Very high z-order to ensure bars are in foreground
    
    # Create secondary y-axis for first try compilation rate
    ax2 = ax.twinx()
    bars2 = ax2.bar(x + width/2, 
                    [no_examples_first_try['mean'], examples_first_try['mean']], 
                    width, 
                    label='Avg First Try Compilation Rate',
                    color='#ff7f0e',  # Orange for first try compilation
                    alpha=0.8,
                    zorder=100)  # Very high z-order to ensure bars are in foreground
    
    # Set labels and formatting
    ax.set_xlabel('Prompt Configuration', fontweight='bold', fontsize=14)
    ax.set_ylabel('Average Fix Attempts per Method', fontweight='bold', color='#9467bd', fontsize=14)
    ax2.set_ylabel('First Try Compilation Rate (%)', fontweight='bold', color='#ff7f0e', fontsize=14)
    
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.tick_params(axis='y', labelcolor='#9467bd', labelsize=12)
    ax2.tick_params(axis='y', labelcolor='#ff7f0e', labelsize=12)
    ax.tick_params(axis='x', labelsize=12)
    
    # Set y-axis limits for better visualization and legend space
    ax.set_ylim(bottom=0, top=4)  # Left axis: 0 to 4 for fix attempts
    ax2.set_ylim(bottom=0, top=100)  # Right axis: 0 to 100% for compilation rate
    
    # Remove grid entirely to avoid overlap issues
    ax.grid(False)
    
    # Create legend
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    
    legend_elements = lines1 + lines2
    legend_labels = labels1 + labels2
    
    legend = ax.legend(legend_elements, legend_labels, 
                      loc='upper right', ncol=1, frameon=True,
                      fancybox=True, shadow=True, edgecolor='black', facecolor='white',
                      fontsize=12)
    
    # Adjust layout
    plt.subplots_adjust(top=0.95, bottom=0.15, left=0.12, right=0.88)
    
    # Save plot
    plt.savefig(output_path, dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close()
    
    print(f"Fix Attempts plot saved to: {output_path}")

def create_coverage_comparison_plot(experiments_data, output_path):
    """Create the Line Coverage and Compilation Rate Comparison plot."""
    fig, ax1 = plt.subplots(figsize=(7, 6.5))
    
    # Data for grouped bars
    categories = ['No Examples', 'Examples']
    
    # Extract data
    no_examples_line = calculate_statistics(experiments_data[3]['line_coverage'])
    examples_line = calculate_statistics(experiments_data[4]['line_coverage'])
    
    no_examples_compilation = calculate_statistics(experiments_data[3]['compilation_rate'])
    examples_compilation = calculate_statistics(experiments_data[4]['compilation_rate'])
    
    # Set up bar positions
    x = np.arange(len(categories))
    width = 0.35
    
    # Create grouped bars
    bars1 = ax1.bar(x - width/2, 
                    [no_examples_line['mean'], examples_line['mean']], 
                    width, 
                    label='Avg Line Coverage (%)',
                    color='#1f77b4', 
                    alpha=0.8,
                    zorder=100)  # Bring bars to foreground
    
    # Create secondary y-axis for compilation rate
    ax2 = ax1.twinx()
    bars2 = ax2.bar(x + width/2, 
                    [no_examples_compilation['mean'], examples_compilation['mean']], 
                    width, 
                    label='Avg Compilation Rate (%)',
                    color='#C73E1D', 
                    alpha=0.8,
                    zorder=100)  # Bring bars to foreground
    
    # Set labels and formatting
    ax1.set_xlabel('Prompt Configuration', fontweight='bold', fontsize=14)
    ax1.set_ylabel('Line Coverage (%)', fontweight='bold', color='#1f77b4', fontsize=14)
    ax2.set_ylabel('Compilation Rate (%)', fontweight='bold', color='#C73E1D', fontsize=14)
    
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories)
    ax1.tick_params(axis='y', labelcolor='#1f77b4', labelsize=12)
    ax2.tick_params(axis='y', labelcolor='#C73E1D', labelsize=12)
    ax1.tick_params(axis='x', labelsize=12)
    
    # Set y-axis limits for proper bar alignment
    ax1.set_ylim(bottom=0, top=100)  # Both axes: 0 to 100% for coverage
    ax2.set_ylim(bottom=0, top=100)
    
    # Remove grid to avoid overlap issues
    ax1.grid(False)
    
    # Create legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    
    legend_elements = lines1 + lines2
    legend_labels = labels1 + labels2
    
    legend = ax1.legend(legend_elements, legend_labels, 
                      loc='upper left', ncol=1, frameon=True,
                      fancybox=True, shadow=True, edgecolor='black', facecolor='white',
                      fontsize=12)
    
    # Adjust layout
    plt.subplots_adjust(top=0.95, bottom=0.15, left=0.12, right=0.88)
    
    # Save plot
    plt.savefig(output_path, dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close()
    
    print(f"Coverage Comparison plot saved to: {output_path}")

def main():
    """Main function to generate both plots."""
    # Set up paths
    results_dir = Path("../../../src/results")
    plots_dir = Path("../plots")
    plots_dir.mkdir(exist_ok=True)
    
    # Load experiment data
    experiments_data = {}
    
    for exp_num in [3, 4]:
        exp_path = results_dir / f"experiment_{exp_num}.xlsx"
        print(f"Loading {exp_path}...")
        experiments_data[exp_num] = load_experiment_data(exp_path)
        
        # Print summary statistics
        line_stats = calculate_statistics(experiments_data[exp_num]['line_coverage'])
        branch_stats = calculate_statistics(experiments_data[exp_num]['branch_coverage'])
        fix_attempts_stats = calculate_statistics(experiments_data[exp_num]['avg_fix_attempts_per_method'])
        first_try_stats = calculate_statistics(experiments_data[exp_num]['first_try_compilation_rate'])
        compilation_stats = calculate_statistics(experiments_data[exp_num]['compilation_rate'])
        
        exp_name = "No Examples" if exp_num == 3 else "Examples"
        print(f"Experiment {exp_num} ({exp_name}):")
        print(f"  Line coverage = {line_stats['mean']:.2f}% ± {line_stats['std']:.2f}% (n={line_stats['count']} repos)")
        print(f"  Branch coverage = {branch_stats['mean']:.2f}% ± {branch_stats['std']:.2f}% (n={branch_stats['count']} repos)")
        print(f"  Avg fix attempts per method = {fix_attempts_stats['mean']:.2f} ± {fix_attempts_stats['std']:.2f} (n={fix_attempts_stats['count']} repos)")
        print(f"  First try compilation rate = {first_try_stats['mean']:.2f}% ± {first_try_stats['std']:.2f}% (n={first_try_stats['count']} repos)")
        print(f"  Compilation rate = {compilation_stats['mean']:.2f}% ± {compilation_stats['std']:.2f}% (n={compilation_stats['count']} repos)")
    
    # Create plots
    print("\nCreating plots...")
    create_fix_attempts_plot(experiments_data, plots_dir / "fix_attempts_comparison.pdf")
    create_fix_attempts_plot(experiments_data, plots_dir / "fix_attempts_comparison.png")
    create_coverage_comparison_plot(experiments_data, plots_dir / "coverage_comparison.pdf")
    create_coverage_comparison_plot(experiments_data, plots_dir / "coverage_comparison.png")
    
    print(f"\nAll plots generated successfully!")
    print(f"Files saved in: {plots_dir.absolute()}")

if __name__ == "__main__":
    main()
