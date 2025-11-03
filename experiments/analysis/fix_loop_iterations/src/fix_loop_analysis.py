#!/usr/bin/env python3
"""
Fix Loop Iteration Analysis Script
Creates publication-quality plots for master's thesis showing:
- Left Figure: Compile-Fix Loop Performance
- Right Figure: Runtime-Fix Loop Performance

Experiments:
- Experiment 1: 0 iterations
- Experiment 2: 4 iterations  
- Experiment 3: 8 iterations
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

    # Extract compilation data
    # Column S (index 18): Normal scenarios generated
    # Column AO (index 40): Bug hunting scenarios generated
    # Column U (index 20): Compiled normal scenarios
    # Column AQ (index 42): Compiled bug hunting scenarios
    normal_scenarios = pd.to_numeric(df.iloc[1:, 18], errors='coerce').fillna(0)
    bug_hunting_scenarios = pd.to_numeric(df.iloc[1:, 40], errors='coerce').fillna(0)
    compiled_normal = pd.to_numeric(df.iloc[1:, 20], errors='coerce').fillna(0)
    compiled_bug_hunting = pd.to_numeric(df.iloc[1:, 42], errors='coerce').fillna(0)

    # Calculate compilation rate
    total_scenarios = normal_scenarios + bug_hunting_scenarios
    total_compiled = compiled_normal + compiled_bug_hunting

    # Avoid division by zero
    compilation_rate_raw = np.where(total_scenarios > 0,
                                   (total_compiled / total_scenarios) * 100,
                                   0)
    compilation_rate_raw = pd.Series(compilation_rate_raw).dropna()

    # Extract runtime fix data
    # Column AH (index 33): Fixable RE (total RE)
    # Column AK (index 36): Fixed RE
    fixable_re = pd.to_numeric(df.iloc[1:, 33], errors='coerce').fillna(0)
    fixed_re = pd.to_numeric(df.iloc[1:, 36], errors='coerce').fillna(0)

    # Calculate runtime fix rate
    # Avoid division by zero (0/0 = 0)
    runtime_fix_rate_raw = np.where(fixable_re > 0,
                                   (fixed_re / fixable_re) * 100,
                                   0)
    runtime_fix_rate_raw = pd.Series(runtime_fix_rate_raw).dropna()

    # Calculate repository-level averages (10 repos × 5 runs each)
    repo_averages = []
    
    for repo_idx in range(10):  # 10 repositories
        start_idx = repo_idx * 5
        end_idx = start_idx + 5
        
        # Get data for this repository (5 runs)
        repo_line = line_coverage_raw.iloc[start_idx:end_idx]
        repo_branch = branch_coverage_raw.iloc[start_idx:end_idx]
        repo_instruction = instruction_coverage_raw.iloc[start_idx:end_idx]
        repo_compilation = compilation_rate_raw.iloc[start_idx:end_idx]
        repo_runtime = runtime_fix_rate_raw.iloc[start_idx:end_idx]
        
        # Calculate average for this repository
        repo_avg = {
            'line_coverage': repo_line.mean(),
            'branch_coverage': repo_branch.mean(),
            'instruction_coverage': repo_instruction.mean(),
            'compilation_rate': repo_compilation.mean(),
            'runtime_fix_rate': repo_runtime.mean()
        }
        repo_averages.append(repo_avg)
    
    # Convert to pandas Series for compatibility with existing code
    line_coverage = pd.Series([avg['line_coverage'] for avg in repo_averages])
    branch_coverage = pd.Series([avg['branch_coverage'] for avg in repo_averages])
    instruction_coverage = pd.Series([avg['instruction_coverage'] for avg in repo_averages])
    compilation_rate = pd.Series([avg['compilation_rate'] for avg in repo_averages])
    runtime_fix_rate = pd.Series([avg['runtime_fix_rate'] for avg in repo_averages])

    return {
        'line_coverage': line_coverage,
        'branch_coverage': branch_coverage,
        'instruction_coverage': instruction_coverage,
        'compilation_rate': compilation_rate,
        'runtime_fix_rate': runtime_fix_rate
    }

def calculate_statistics(data):
    """Calculate mean and standard deviation for coverage metrics."""
    return {
        'mean': data.mean(),
        'std': data.std(),
        'count': len(data)
    }

def create_compile_fix_plot(experiments_data, output_path):
    """Create the Compile-Fix Loop Performance plot."""
    fig, ax1 = plt.subplots(figsize=(7, 6.5))
    
    iterations = [0, 4, 8]
    
    # Extract data
    line_means = []
    line_stds = []
    branch_means = []
    branch_stds = []
    compilation_means = []
    compilation_stds = []
    
    for exp_num in [1, 2, 3]:
        line_stats = calculate_statistics(experiments_data[exp_num]['line_coverage'])
        branch_stats = calculate_statistics(experiments_data[exp_num]['branch_coverage'])
        compilation_stats = calculate_statistics(experiments_data[exp_num]['compilation_rate'])
        
        line_means.append(line_stats['mean'])
        line_stds.append(line_stats['std'])
        branch_means.append(branch_stats['mean'])
        branch_stds.append(branch_stats['std'])
        compilation_means.append(compilation_stats['mean'])
        compilation_stds.append(compilation_stats['std'])
    
    # Plot coverage metrics on left y-axis (no std dev bands)
    ax1.plot(iterations, line_means, 'o-', linewidth=3, markersize=8, 
             color='#1f77b4', label='Line Cvg', markerfacecolor='#1f77b4', 
             markeredgewidth=2, markeredgecolor='#1f77b4', zorder=15)
    
    ax1.plot(iterations, branch_means, 's-', linewidth=3, markersize=8, 
             color='#2ca02c', label='Branch Cvg', markerfacecolor='#2ca02c', 
             markeredgewidth=2, markeredgecolor='#2ca02c', zorder=15)
    
    # Create secondary y-axis for compilation rate
    ax2 = ax1.twinx()
    ax2.plot(iterations, compilation_means, '^-', linewidth=3, markersize=8, 
             color='#C73E1D', label='Comp Rate', markerfacecolor='#C73E1D', 
             markeredgewidth=2, markeredgecolor='#C73E1D', zorder=15)
    ax2.fill_between(iterations, 
                     np.array(compilation_means) - np.array(compilation_stds),
                     np.array(compilation_means) + np.array(compilation_stds),
                     alpha=0.15, color='#C73E1D', label='Comp Rate ±1 Std Dev', 
                     edgecolor='#C73E1D', linewidth=1, zorder=3)
    
    # Set primary y-axis (coverage)
    ax1.set_xlabel('Number of Fix Iterations', fontweight='bold', fontsize=14)
    ax1.set_ylabel('Coverage (%)', fontweight='bold', color='black', fontsize=14)
    ax1.tick_params(axis='y', labelcolor='black', labelsize=12)
    ax1.tick_params(axis='x', labelsize=12)
    ax1.set_ylim(-5, 105)
    ax1.set_xlim(-0.5, 8.5)
    ax1.set_xticks(iterations)
    
    # Set secondary y-axis (compilation rate)
    ax2.set_ylabel('Compilation Rate (%)', fontweight='bold', color='#C73E1D', fontsize=14)
    ax2.tick_params(axis='y', labelcolor='#C73E1D', labelsize=12)
    ax2.set_ylim(-5, 105)
    
    # Add grid
    ax1.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
    
    # Create legend in dedicated space above the plot
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    
    # Create a 2x2 grid legend layout
    legend_elements = []
    legend_labels = []
    
    # Row 1: Line Coverage, Branch Coverage
    legend_elements.extend([lines1[0], lines1[1]])  # Line, Branch
    legend_labels.extend(['Avg Line Cvg', 'Avg Branch Cvg'])
    
    # Row 2: Compilation Rate, Compilation Rate Std Dev
    legend_elements.extend([lines2[0], lines2[1]])  # Compilation, Compilation error
    legend_labels.extend(['Avg Comp Rate', 'Avg Comp Rate ±1 Std Dev'])
    
    # Create legend in bottom-right corner (moved up and slightly right, bigger)
    legend = fig.legend(legend_elements, legend_labels, 
                      loc='lower right', ncol=2, frameon=True,
                      fancybox=True, shadow=True, edgecolor='black', facecolor='white',
                      bbox_to_anchor=(0.88, 0.15), fontsize=12, columnspacing=0.5)
    
    # Adjust layout - no extra space needed at top since legend is at bottom
    plt.subplots_adjust(top=0.95, bottom=0.15, left=0.12, right=0.88)
    
    # Save plot
    plt.savefig(output_path, dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close()
    
    print(f"Compile-Fix plot saved to: {output_path}")

def create_runtime_fix_plot(experiments_data, output_path):
    """Create the Runtime-Fix Loop Performance plot."""
    fig, ax1 = plt.subplots(figsize=(7, 6.5))
    
    iterations = [0, 4, 8]
    
    # Extract data
    line_means = []
    line_stds = []
    branch_means = []
    branch_stds = []
    runtime_means = []
    runtime_stds = []
    
    for exp_num in [1, 2, 3]:
        line_stats = calculate_statistics(experiments_data[exp_num]['line_coverage'])
        branch_stats = calculate_statistics(experiments_data[exp_num]['branch_coverage'])
        runtime_stats = calculate_statistics(experiments_data[exp_num]['runtime_fix_rate'])
        
        line_means.append(line_stats['mean'])
        line_stds.append(line_stats['std'])
        branch_means.append(branch_stats['mean'])
        branch_stds.append(branch_stats['std'])
        runtime_means.append(runtime_stats['mean'])
        runtime_stds.append(runtime_stats['std'])
    
    # Plot line coverage (no std dev bands)
    ax1.plot(iterations, line_means, 'o-', linewidth=3, markersize=8, 
             color='#1f77b4', label='Line Cvg', markerfacecolor='#1f77b4', 
             markeredgewidth=2, markeredgecolor='#1f77b4', zorder=15)
    
    ax1.plot(iterations, branch_means, 's-', linewidth=3, markersize=8, 
             color='#2ca02c', label='Branch Cvg', markerfacecolor='#2ca02c', 
             markeredgewidth=2, markeredgecolor='#2ca02c', zorder=15)
    
    # Create secondary y-axis for runtime fix rate
    ax2 = ax1.twinx()
    ax2.plot(iterations, runtime_means, '^-', linewidth=3, markersize=8, 
             color='#C73E1D', label='Runtime Fix Rate', markerfacecolor='#C73E1D', 
             markeredgewidth=2, markeredgecolor='#C73E1D', zorder=15)
    ax2.fill_between(iterations, 
                     np.array(runtime_means) - np.array(runtime_stds),
                     np.array(runtime_means) + np.array(runtime_stds),
                     alpha=0.15, color='#C73E1D', label='Runtime Fix Rate ±1 Std Dev', 
                     edgecolor='#C73E1D', linewidth=1, zorder=3)
    
    # Set primary y-axis (coverage)
    ax1.set_xlabel('Number of Fix Iterations', fontweight='bold', fontsize=14)
    ax1.set_ylabel('Coverage (%)', fontweight='bold', color='black', fontsize=14)
    ax1.tick_params(axis='y', labelcolor='black', labelsize=12)
    ax1.tick_params(axis='x', labelsize=12)
    ax1.set_ylim(-5, 105)
    ax1.set_xlim(-0.5, 8.5)
    ax1.set_xticks(iterations)
    
    # Set secondary y-axis (runtime fix rate)
    ax2.set_ylabel('Runtime Fix Rate (%)', fontweight='bold', color='#C73E1D', fontsize=14)
    ax2.tick_params(axis='y', labelcolor='#C73E1D', labelsize=12)
    ax2.set_ylim(-5, 105)
    
    # Add grid
    ax1.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
    
    # Create legend in dedicated space above the plot
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    
    # Create a 2x2 grid legend layout
    legend_elements = []
    legend_labels = []
    
    # Row 1: Line Coverage, Branch Coverage
    legend_elements.extend([lines1[0], lines1[1]])  # Line, Branch
    legend_labels.extend(['Avg Line Cvg', 'Avg Branch Cvg'])
    
    # Row 2: Runtime Fix Rate, Runtime Fix Rate Std Dev
    legend_elements.extend([lines2[0], lines2[1]])  # Runtime, Runtime error
    legend_labels.extend(['Avg Runtime Fix Rate', 'Avg Runtime Fix Rate ±1 Std Dev'])
    
    # Create legend inside the plot area (overlapping with graph)
    legend = ax1.legend(legend_elements, legend_labels, 
                      loc='upper right', ncol=2, frameon=True,
                      fancybox=True, shadow=True, edgecolor='black', facecolor='white',
                      fontsize=12, columnspacing=0.8, bbox_to_anchor=(1.02, 0.98))
    
    # Adjust layout - same as compile plot since legend is inside
    plt.subplots_adjust(top=0.95, bottom=0.15, left=0.12, right=0.88)
    
    # Save plot
    plt.savefig(output_path, dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close()
    
    print(f"Runtime-Fix plot saved to: {output_path}")

def main():
    """Main function to generate both plots."""
    # Set up paths
    results_dir = Path("../../../src/results")
    plots_dir = Path("../plots")
    plots_dir.mkdir(exist_ok=True)
    
    # Load experiment data
    experiments_data = {}
    for exp_num in [1, 2, 3]:
        exp_path = results_dir / f"experiment_{exp_num}.xlsx"
        print(f"Loading {exp_path}...")
        experiments_data[exp_num] = load_experiment_data(exp_path)
        
        # Print summary statistics
        line_stats = calculate_statistics(experiments_data[exp_num]['line_coverage'])
        branch_stats = calculate_statistics(experiments_data[exp_num]['branch_coverage'])
        compilation_stats = calculate_statistics(experiments_data[exp_num]['compilation_rate'])
        runtime_stats = calculate_statistics(experiments_data[exp_num]['runtime_fix_rate'])
        print(f"Experiment {exp_num} (iterations: {[0,4,8][exp_num-1]}):")
        print(f"  Line coverage = {line_stats['mean']:.2f}% ± {line_stats['std']:.2f}% (n={line_stats['count']} repos)")
        print(f"  Branch coverage = {branch_stats['mean']:.2f}% ± {branch_stats['std']:.2f}% (n={branch_stats['count']} repos)")
        print(f"  Compilation rate = {compilation_stats['mean']:.2f}% ± {compilation_stats['std']:.2f}% (n={compilation_stats['count']} repos)")
        print(f"  Runtime fix rate = {runtime_stats['mean']:.2f}% ± {runtime_stats['std']:.2f}% (n={runtime_stats['count']} repos)")
    
    # Create plots
    print("\nCreating plots...")
    create_compile_fix_plot(experiments_data, plots_dir / "compile_fix_performance.pdf")
    create_compile_fix_plot(experiments_data, plots_dir / "compile_fix_performance.png")
    
    create_runtime_fix_plot(experiments_data, plots_dir / "runtime_fix_performance.pdf")
    create_runtime_fix_plot(experiments_data, plots_dir / "runtime_fix_performance.png")
    
    print("\nAll plots generated successfully!")
    print("Files saved in:", plots_dir.absolute())

if __name__ == "__main__":
    main()
