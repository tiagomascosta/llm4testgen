#!/usr/bin/env python3
"""
Complexity-Aware Performance Analysis Script
Creates a publication-quality plot showing how code maintainability (MI) 
influences LLM4TestGen performance across evaluated repositories.

The plot shows:
- Grouped bars: Line coverage, Branch coverage, Bug detection rate (left Y-axis)
- Overlay line: Compilation success rate (right Y-axis)
- X-axis: Three complexity groups (High/Medium/Low maintainability)
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
    """Load and process experiment data from Excel file.
    
    Data structure: 155 rows = 31 repositories × 5 runs each
    First 5 rows = repo 1, next 5 rows = repo 2, etc.
    """
    # Read Excel file - row 1 and 2 are titles, data from row 3 to 157
    df = pd.read_excel(experiment_path, header=1)
    # Skip row 1 (0-based index 0) and take rows 3-157
    # After header=1, Excel row 3 is pandas index 0, Excel row 157 is pandas index 154
    df = df.iloc[:155]  # Take rows from index 0 to 154 (Excel rows 3 to 157)
    
    # Column indices (0-based)
    # MI is at index 16
    mi_index = 16
    # Line coverage is at index 27 (column AB)
    line_cov_index = 27
    # Branch coverage is at index 28 (column AC)
    branch_cov_index = 28
    # Bug detected is at index 25 (column Z)
    bug_detected_index = 25
    # Compilation data:
    # Column S (index 18): Normal scenarios generated
    # Column AO (index 40): Bug hunting scenarios generated
    # Column U (index 20): Compiled normal scenarios
    # Column AQ (index 42): Compiled bug hunting scenarios
    normal_scenarios_index = 18
    bug_hunting_scenarios_index = 40
    compiled_normal_index = 20
    compiled_bug_hunting_index = 42
    
    # Extract data
    mi_raw = pd.to_numeric(df.iloc[:, mi_index], errors='coerce')
    line_coverage_raw = pd.to_numeric(df.iloc[:, line_cov_index], errors='coerce')
    branch_coverage_raw = pd.to_numeric(df.iloc[:, branch_cov_index], errors='coerce')
    bug_detected_raw = df.iloc[:, bug_detected_index]
    normal_scenarios = pd.to_numeric(df.iloc[:, normal_scenarios_index], errors='coerce').fillna(0)
    bug_hunting_scenarios = pd.to_numeric(df.iloc[:, bug_hunting_scenarios_index], errors='coerce').fillna(0)
    compiled_normal = pd.to_numeric(df.iloc[:, compiled_normal_index], errors='coerce').fillna(0)
    compiled_bug_hunting = pd.to_numeric(df.iloc[:, compiled_bug_hunting_index], errors='coerce').fillna(0)
    
    # Calculate compilation success rate per row
    total_scenarios = normal_scenarios + bug_hunting_scenarios
    total_compiled = compiled_normal + compiled_bug_hunting
    compilation_rate_raw = np.where(total_scenarios > 0,
                                   (total_compiled / total_scenarios) * 100,
                                   0)
    compilation_rate_raw = pd.Series(compilation_rate_raw)
    
    # Convert bug_detected to boolean
    # Handle various boolean representations
    bug_detected_bool = []
    for val in bug_detected_raw:
        if pd.isna(val):
            bug_detected_bool.append(False)
        elif isinstance(val, bool):
            bug_detected_bool.append(val)
        elif isinstance(val, (int, float)):
            bug_detected_bool.append(bool(val))
        elif isinstance(val, str):
            val_lower = val.lower().strip()
            bug_detected_bool.append(val_lower in ['true', '1', 'yes', 'y'])
        else:
            bug_detected_bool.append(False)
    bug_detected_bool = pd.Series(bug_detected_bool)
    
    # Calculate repository-level averages (31 repos × 5 runs each)
    num_repos = 31
    runs_per_repo = 5
    
    repo_data = []
    for repo_idx in range(num_repos):
        start_idx = repo_idx * runs_per_repo
        end_idx = start_idx + runs_per_repo
        
        # Get data for this repository (5 runs)
        repo_mi = mi_raw.iloc[start_idx:end_idx]
        repo_line_cov = line_coverage_raw.iloc[start_idx:end_idx]
        repo_branch_cov = branch_coverage_raw.iloc[start_idx:end_idx]
        repo_bug_detected_runs = bug_detected_bool.iloc[start_idx:end_idx]
        repo_compilation = compilation_rate_raw.iloc[start_idx:end_idx]
        
        # Calculate averages for this repository
        repo_avg_mi = repo_mi.mean()
        repo_avg_line_cov = repo_line_cov.mean()
        repo_avg_branch_cov = repo_branch_cov.mean()
        # Bug detected: True if bug was detected in at least one of the 5 runs
        repo_bug_detected = repo_bug_detected_runs.any()
        repo_avg_compilation = repo_compilation.mean()
        
        repo_data.append({
            'mi': repo_avg_mi,
            'line_coverage': repo_avg_line_cov,
            'branch_coverage': repo_avg_branch_cov,
            'bug_detected': repo_bug_detected,  # Boolean: True if bug detected in any run
            'compilation_success_rate': repo_avg_compilation
        })
    
    return pd.DataFrame(repo_data)

def group_by_complexity(repo_df):
    """Group repositories into High/Medium/Low complexity based on MI.
    
    Orders repositories from most complex (lowest MI) to least complex (highest MI),
    then divides into three equal-sized segments.
    """
    # Sort by MI ascending (lowest MI = highest complexity first)
    sorted_df = repo_df.sort_values('mi').reset_index(drop=True)
    
    # Divide into three groups
    total_repos = len(sorted_df)
    group_size_1 = 10  # High complexity
    group_size_2 = 11  # Medium complexity
    group_size_3 = 10  # Low complexity
    
    # If number of repos changes, adjust proportionally
    if total_repos != 31:
        # Maintain approximately 1/3 per group
        group_size_1 = int(np.ceil(total_repos / 3))
        remaining = total_repos - group_size_1
        group_size_2 = int(np.ceil(remaining / 2))
        group_size_3 = remaining - group_size_2
    
    high_complexity = sorted_df.iloc[:group_size_1]
    medium_complexity = sorted_df.iloc[group_size_1:group_size_1 + group_size_2]
    low_complexity = sorted_df.iloc[group_size_1 + group_size_2:]
    
    # Calculate group means (average per repo, then average of repos in group)
    # Also calculate MI ranges for labels
    # Bug detection rate: percentage of repos in group where bug was detected (at least once)
    groups = {
        'High': {
            'mi': high_complexity['mi'].mean(),
            'mi_min': high_complexity['mi'].min(),
            'mi_max': high_complexity['mi'].max(),
            'line_coverage': high_complexity['line_coverage'].mean(),
            'branch_coverage': high_complexity['branch_coverage'].mean(),
            'bug_detection_rate': (high_complexity['bug_detected'].sum() / len(high_complexity)) * 100,
            'compilation_success_rate': high_complexity['compilation_success_rate'].mean()
        },
        'Medium': {
            'mi': medium_complexity['mi'].mean(),
            'mi_min': medium_complexity['mi'].min(),
            'mi_max': medium_complexity['mi'].max(),
            'line_coverage': medium_complexity['line_coverage'].mean(),
            'branch_coverage': medium_complexity['branch_coverage'].mean(),
            'bug_detection_rate': (medium_complexity['bug_detected'].sum() / len(medium_complexity)) * 100,
            'compilation_success_rate': medium_complexity['compilation_success_rate'].mean()
        },
        'Low': {
            'mi': low_complexity['mi'].mean(),
            'mi_min': low_complexity['mi'].min(),
            'mi_max': low_complexity['mi'].max(),
            'line_coverage': low_complexity['line_coverage'].mean(),
            'branch_coverage': low_complexity['branch_coverage'].mean(),
            'bug_detection_rate': (low_complexity['bug_detected'].sum() / len(low_complexity)) * 100,
            'compilation_success_rate': low_complexity['compilation_success_rate'].mean()
        }
    }
    
    return groups

def create_complexity_aware_plot(groups, output_path):
    """Create the Complexity-Aware Performance plot."""
    # Wide figure suitable for full-width LaTeX figure (≈ 4:1 aspect ratio)
    # Made taller to prevent cropping
    fig, ax1 = plt.subplots(figsize=(12, 4.5))
    
    # X-axis labels (inverted order: Low, Medium, High from left to right)
    # Include MI ranges with rounded values
    group_keys = ['Low', 'Medium', 'High']
    x_labels = [
        f"Low ({int(round(groups['Low']['mi_min']))}-{int(round(groups['Low']['mi_max']))})",
        f"Medium ({int(round(groups['Medium']['mi_min']))}-{int(round(groups['Medium']['mi_max']))})",
        f"High ({int(round(groups['High']['mi_min']))}-{int(round(groups['High']['mi_max']))})"
    ]
    x_positions = np.arange(len(x_labels))
    
    # Bar width
    bar_width = 0.25
    x_offset = np.array([-bar_width, 0, bar_width])
    
    # Extract data (order: Low, Medium, High)
    # Calculate: average per repo (already done), then average of repos in group
    line_cov_values = [groups[key]['line_coverage'] for key in group_keys]
    branch_cov_values = [groups[key]['branch_coverage'] for key in group_keys]
    bug_detection_values = [groups[key]['bug_detection_rate'] for key in group_keys]
    compilation_values = [groups[key]['compilation_success_rate'] for key in group_keys]
    
    # Colors matching fix_loop_iterations graph for consistency
    line_cov_color = '#1f77b4'  # Blue (same as fix_loop_iterations)
    branch_cov_color = '#2ca02c'  # Green (same as fix_loop_iterations)
    bug_detection_color = '#9467bd'  # Purple (research-appropriate, distinct from others)
    compilation_line_color = '#C73E1D'  # Red (same as compilation rate in fix_loop_iterations)
    
    # Plot bars on left y-axis
    bars1 = ax1.bar(x_positions + x_offset[0], line_cov_values, bar_width,
                    label='Line coverage', color=line_cov_color, alpha=0.8)
    bars2 = ax1.bar(x_positions + x_offset[1], branch_cov_values, bar_width,
                    label='Branch coverage', color=branch_cov_color, alpha=0.8)
    bars3 = ax1.bar(x_positions + x_offset[2], bug_detection_values, bar_width,
                    label='Bug detection', color=bug_detection_color, alpha=0.8)
    
    # Create secondary y-axis for compilation success rate line
    ax2 = ax1.twinx()
    
    # Plot line with circle markers (matching fix_loop_iterations style)
    line = ax2.plot(x_positions, compilation_values, 'o-', linewidth=3, 
                    markersize=8, color=compilation_line_color, 
                    label='Compilation rate', markerfacecolor=compilation_line_color,
                    markeredgewidth=2, markeredgecolor=compilation_line_color, zorder=15)
    
    # Set primary y-axis (coverage and bug detection)
    ax1.set_xlabel('Code Complexity (Maintainability Index)', fontweight='bold', fontsize=14)
    ax1.set_ylabel('Coverage & Bug Detection (%)', fontweight='bold', color='black', fontsize=14)
    ax1.tick_params(axis='y', labelcolor='black', labelsize=12)
    ax1.tick_params(axis='x', labelsize=12)
    ax1.set_ylim(0, 100)
    ax1.set_xlim(-0.5, len(x_labels) - 0.5)
    ax1.set_xticks(x_positions)
    ax1.set_xticklabels(x_labels)
    
    # Set secondary y-axis (compilation rate)
    ax2.set_ylabel('Compilation Rate (%)', fontweight='bold', 
                   color=compilation_line_color, fontsize=14)
    ax2.tick_params(axis='y', labelcolor=compilation_line_color, labelsize=12)
    ax2.set_ylim(0, 100)
    
    # Add grid (matching fix_loop_iterations style)
    ax1.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
    ax1.set_axisbelow(True)
    
    # Create legend (matching fix_loop_iterations style)
    # Get handles and labels from both axes
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    
    # Combine handles and labels
    all_handles = handles1 + handles2
    all_labels = labels1 + labels2
    
    # Create legend at top-right corner (moved slightly left to avoid y-axis overlap)
    legend = fig.legend(all_handles, all_labels,
                       loc='upper right', ncol=2, frameon=True,
                       fancybox=True, shadow=True, edgecolor='black', facecolor='white',
                       bbox_to_anchor=(0.90, 0.98), fontsize=12, columnspacing=0.5)
    
    # Adjust layout (with legend at top)
    plt.subplots_adjust(top=0.88, bottom=0.15, left=0.12, right=0.92)
    
    # Save plot
    plt.savefig(output_path, dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    
    print(f"Complexity-aware performance plot saved to: {output_path}")

def main():
    """Main function to generate the plot."""
    # Set up paths
    # From: experiments/analysis/complexity_aware_performance/src/
    # To: experiments/src/results/
    results_dir = Path(__file__).parent.parent.parent.parent / "src" / "results"
    plots_dir = Path(__file__).parent.parent / "plots"
    plots_dir.mkdir(exist_ok=True)
    
    # Load experiment data
    experiment_path = results_dir / "experiment_11.xlsx"
    print(f"Loading {experiment_path}...")
    repo_df = load_experiment_data(experiment_path)
    
    print(f"Loaded data for {len(repo_df)} repositories")
    
    # Group by complexity
    groups = group_by_complexity(repo_df)
    
    # Print summary statistics
    print("\nGroup Summary Statistics:")
    print("=" * 60)
    print("Note: Values calculated as average per repository (5 runs), then average of repositories in group")
    print("=" * 60)
    for group_name, group_data in groups.items():
        print(f"{group_name} Complexity (MI range: {int(round(group_data['mi_min']))}-{int(round(group_data['mi_max']))}):")
        print(f"  Mean MI: {group_data['mi']:.2f}")
        print(f"  Mean Line Coverage: {group_data['line_coverage']:.2f}%")
        print(f"  Mean Branch Coverage: {group_data['branch_coverage']:.2f}%")
        print(f"  Mean Bug Detection Rate: {group_data['bug_detection_rate']:.2f}%")
        print(f"  Mean Compilation Rate: {group_data['compilation_success_rate']:.2f}%")
        print()
    
    # Create plot
    print("Creating plot...")
    create_complexity_aware_plot(groups, plots_dir / "complexity_aware_performance.pdf")
    create_complexity_aware_plot(groups, plots_dir / "complexity_aware_performance.png")
    
    print("\nPlot generated successfully!")
    print("Files saved in:", plots_dir.absolute())

if __name__ == "__main__":
    main()

