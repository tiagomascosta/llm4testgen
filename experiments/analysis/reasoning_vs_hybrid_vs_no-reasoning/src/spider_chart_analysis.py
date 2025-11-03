#!/usr/bin/env python3
"""
Spider Chart Analysis Script
Creates publication-quality spider chart comparing 3 experimental setups:
- Experiment 4: Coding models for both tasks
- Experiment 5: Non-code tasks use reasoning model  
- Experiment 6: Both task groups use reasoning

Metrics: Line Coverage, Branch Coverage, Bug Detection Rate, Compilation Rate, Generated Scenarios
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Set seaborn style for consistency with other plots
sns.set_style("whitegrid")
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.size'] = 12

# Set up publication-quality plotting style
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("husl")

# Configure matplotlib for LaTeX compatibility
plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': 12,
    'axes.labelsize': 12,
    'axes.titlesize': 14,
    'xtick.labelsize': 14,
    'ytick.labelsize': 14,
    'legend.fontsize': 10,
    'figure.titlesize': 16,
    'text.usetex': False,
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
    
    # Extract bug detection data
    # Column Z (index 25): Bug detection boolean values
    bug_detection_raw = df.iloc[1:, 25]  # Keep as is for boolean processing

    # Calculate total test cases and compiled tests
    total_test_cases = normal_scenarios + bug_hunting_scenarios
    total_compiled = compiled_normal + compiled_bug_hunting
    
    # Calculate compilation rate
    compilation_rate_raw = np.where(total_test_cases > 0,
                                   (total_compiled / total_test_cases) * 100,
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
        repo_scenarios = pd.Series(total_test_cases[start_idx:end_idx])
        
        # Process bug detection for this repository
        repo_bug_detection = bug_detection_raw.iloc[start_idx:end_idx]
        # Convert to boolean and check if any run detected a bug
        repo_bug_detected = any(pd.to_numeric(repo_bug_detection, errors='coerce').fillna(0) > 0)
        
        # Calculate average for this repository
        repo_avg = {
            'line_coverage': repo_line.mean(),
            'branch_coverage': repo_branch.mean(),
            'instruction_coverage': repo_instruction.mean(),
            'compilation_rate': repo_compilation_rate.mean(),
            'generated_scenarios': repo_scenarios.mean(),
            'bug_detected': repo_bug_detected
        }
        repo_averages.append(repo_avg)
    
    # Convert to pandas Series for compatibility
    line_coverage = pd.Series([avg['line_coverage'] for avg in repo_averages])
    branch_coverage = pd.Series([avg['branch_coverage'] for avg in repo_averages])
    instruction_coverage = pd.Series([avg['instruction_coverage'] for avg in repo_averages])
    compilation_rate = pd.Series([avg['compilation_rate'] for avg in repo_averages])
    generated_scenarios = pd.Series([avg['generated_scenarios'] for avg in repo_averages])
    bug_detected = pd.Series([avg['bug_detected'] for avg in repo_averages])

    return {
        'line_coverage': line_coverage,
        'branch_coverage': branch_coverage,
        'instruction_coverage': instruction_coverage,
        'compilation_rate': compilation_rate,
        'generated_scenarios': generated_scenarios,
        'bug_detected': bug_detected
    }

def calculate_statistics(data):
    """Calculate mean and standard deviation for metrics."""
    return {
        'mean': data.mean(),
        'std': data.std(),
        'count': len(data)
    }

def create_spider_chart(experiments_data, output_path):
    """Create spider chart comparing 3 experimental setups."""
    
    # Define metrics and labels
    metrics = [
        'line_coverage',
        'branch_coverage', 
        'bug_detection_rate',
        'compilation_rate',
        'generated_scenarios'
    ]
    
    metric_labels = [
        'Avg Line Coverage (%)',
        'Avg Branch Coverage (%)',
        'Bug Detection Rate (%)',
        'Avg Compilation Rate (%)',
        'Avg Generated Scenarios'
    ]
    
    # Calculate values for each experiment
    experiment_values = {}
    experiment_names = {
        4: 'Coding Models Only',
        5: 'Non-code Tasks + Reasoning',
        6: 'Both Tasks + Reasoning'
    }
    
    for exp_num in [4, 5, 6]:
        data = experiments_data[exp_num]
        
        # Calculate bug detection rate (percentage of repos where bug was detected)
        bug_detection_rate = (data['bug_detected'].sum() / len(data['bug_detected'])) * 100
        
        values = [
            data['line_coverage'].mean(),
            data['branch_coverage'].mean(),
            bug_detection_rate,
            data['compilation_rate'].mean(),
            data['generated_scenarios'].mean()
        ]
        
        experiment_values[exp_num] = values
    
    # Create figure with wider layout for legend on the right
    fig, ax = plt.subplots(figsize=(14, 6.5))
    ax.set_aspect('equal')
    
    # Number of variables
    num_vars = len(metrics)
    
    # Angles for vertices (pentagon) - rotated so base is at bottom
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    # Rotate by π/2 to make base at bottom (180° from current position)
    angles = [a + np.pi/2 for a in angles]
    angles += angles[:1]  # Close the polygon
    
    # Define colors and markers for each experiment
    colors = ['#1f77b4', '#C73E1D', '#2ca02c']  # Blue, Red, Green
    markers = ['o', 's', '^']  # Circle, Square, Triangle
    
    # Draw pentagonal grid with percentage/number labels
    levels = np.linspace(0.2, 1.0, 5)  # 5 concentric pentagons
    percentages = [20, 40, 60, 80, 100]  # Corresponding percentages
    
    for i, level in enumerate(levels):
        coords = [(level * np.cos(a), level * np.sin(a)) for a in angles]
        xs, ys = zip(*coords)
        ax.plot(xs, ys, color='gray', lw=0.8, alpha=0.6)
        ax.fill(xs, ys, color='gray', alpha=0.05)
        
        # Add percentage/number labels on all grid lines
        # Define which axes are percentages vs numbers
        percentage_axes = [0, 1, 2, 3]  # Line Coverage, Branch Coverage, Bug Detection, Compilation Rate
        number_axis = 4  # Generated Scenarios
        
        # Add labels on percentage axes
        for axis_idx in percentage_axes:
            label_x = level * np.cos(angles[axis_idx])
            label_y = level * np.sin(angles[axis_idx])
            
            # Translate labels to the right (perpendicular to axis) to avoid overlaps
            offset = 0.08  # Distance to move labels perpendicular to axis
            # Move perpendicular to the axis direction (90 degrees clockwise)
            perp_angle = angles[axis_idx] + np.pi/2
            label_x += offset * np.cos(perp_angle)
            label_y += offset * np.sin(perp_angle)
            
            if i < len(percentages):
                # Special cases for scaled axes
                if axis_idx == 0:  # Avg Line Coverage - scale to 60%
                    line_percentages = [12, 24, 36, 48, 60]  # 20%, 40%, 60%, 80%, 100% of 60%
                    ax.text(label_x, label_y, f'{line_percentages[i]}%', 
                           ha='center', va='center', fontsize=10, 
                           color='gray', alpha=0.7)
                elif axis_idx == 1:  # Avg Branch Coverage - scale to 50%
                    branch_percentages = [10, 20, 30, 40, 50]  # 20%, 40%, 60%, 80%, 100% of 50%
                    ax.text(label_x, label_y, f'{branch_percentages[i]}%', 
                           ha='center', va='center', fontsize=10, 
                           color='gray', alpha=0.7)
                else:  # All other percentage axes
                    ax.text(label_x, label_y, f'{percentages[i]}%', 
                           ha='center', va='center', fontsize=10, 
                           color='gray', alpha=0.7)
        
        # Add labels on number axis (Generated Scenarios)
        label_x = level * np.cos(angles[number_axis])
        label_y = level * np.sin(angles[number_axis])
        
        # Translate labels to the right (perpendicular to axis) to avoid overlaps
        offset = 0.08  # Distance to move labels perpendicular to axis
        # Move perpendicular to the axis direction (90 degrees clockwise)
        perp_angle = angles[number_axis] + np.pi/2
        label_x += offset * np.cos(perp_angle)
        label_y += offset * np.sin(perp_angle)
        
        if i < len(percentages):
            # Convert percentage to actual number (using actual max from data)
            max_scenarios = 30  # Increased to accommodate higher values
            actual_number = int((percentages[i] / 100) * max_scenarios)
            ax.text(label_x, label_y, str(actual_number), 
                   ha='center', va='center', fontsize=10, 
                   color='gray', alpha=0.7)
    
    # Draw axes
    for a in angles[:-1]:
        ax.plot([0, np.cos(a)], [0, np.sin(a)], color='gray', lw=0.8)
    
    # Plot each experiment
    for i, (exp_num, values) in enumerate(experiment_values.items()):
        # Normalize values to 0-1 scale (percentages by 100, scenarios by max value)
        normalized_values = []
        for j, v in enumerate(values):
            if j == 0:  # Avg Line Coverage (index 0) - normalize by 60%
                normalized_values.append(v / 60.0)  # Max line coverage = 60%
            elif j == 1:  # Avg Branch Coverage (index 1) - normalize by 50%
                normalized_values.append(v / 50.0)  # Max branch coverage = 50%
            elif j == 4:  # Generated Scenarios (index 4) - normalize by max scenarios
                normalized_values.append(v / 30.0)  # Max scenarios = 30
            else:  # All other metrics are percentages
                normalized_values.append(v / 100.0)
        normalized_values += normalized_values[:1]  # Close the polygon
        
        # Plot data with markers
        data_coords = [(normalized_values[j] * np.cos(angles[j]), 
                       normalized_values[j] * np.sin(angles[j]))
                      for j in range(len(normalized_values))]
        xs, ys = zip(*data_coords)
        ax.plot(xs, ys, color=colors[i], lw=2, marker=markers[i], 
                markersize=8, markerfacecolor=colors[i], markeredgewidth=2, 
                markeredgecolor=colors[i], label=experiment_names[exp_num])
        ax.fill(xs, ys, color=colors[i], alpha=0.15)
    
    # Axis labels with rotation to avoid overlaps
    for i, (label, angle) in enumerate(zip(metric_labels, angles[:-1])):
        x = 1.15 * np.cos(angle)
        y = 1.15 * np.sin(angle)
        
        # Rotate labels slightly to avoid overlaps with data
        rotation = 0
        if i == 0:  # Avg Line Coverage - rotate slightly clockwise
            rotation = 0
        elif i == 1:  # Avg Branch Coverage - rotate slightly counter-clockwise
            rotation = 60
        elif i == 4:  # Avg Generated Scenarios - rotate slightly clockwise
            rotation = -60
        
        ax.text(x, y, label, ha='center', va='center', fontsize=14, 
                fontweight='bold', rotation=rotation)
    
    # Create custom legend with model specifications grouped by experiment
    legend_elements = []
    legend_labels = []
    
    # Experiment 4: Coding Models Only
    legend_elements.append(plt.Line2D([0], [0], color='#1f77b4', marker='o', 
                                     linestyle='-', linewidth=2, markersize=8,
                                     markerfacecolor='#1f77b4', markeredgewidth=2, 
                                     markeredgecolor='#1f77b4'))
    legend_labels.append('Coding Tasks Model: qwen3-coder:30b\nNon-Coding Tasks Model: qwen3-coder:30b')
    
    # Experiment 5: Non-code Tasks + Reasoning  
    legend_elements.append(plt.Line2D([0], [0], color='#C73E1D', marker='s', 
                                     linestyle='-', linewidth=2, markersize=8,
                                     markerfacecolor='#C73E1D', markeredgewidth=2, 
                                     markeredgecolor='#C73E1D'))
    legend_labels.append('Coding Tasks Model: qwen3-coder:30b\nNon-Coding Tasks Model: qwen3:30b (w/ reasoning)')
    
    # Experiment 6: Both Tasks + Reasoning
    legend_elements.append(plt.Line2D([0], [0], color='#2ca02c', marker='^', 
                                     linestyle='-', linewidth=2, markersize=8,
                                     markerfacecolor='#2ca02c', markeredgewidth=2, 
                                     markeredgecolor='#2ca02c'))
    legend_labels.append('Coding Tasks Model: qwen3:30b (w/ reasoning)\nNon-Coding Tasks Model: qwen3:30b (w/ reasoning)')
    
    # Add legend with title
    legend = ax.legend(legend_elements, legend_labels, 
                      loc='center left', bbox_to_anchor=(1.25, 0.5), 
                      fontsize=13, frameon=True, fancybox=True, shadow=True, 
                      edgecolor='black', facecolor='white', title='Model Specifications',
                      handletextpad=0.5, columnspacing=1.0, handlelength=2.0,
                      borderpad=1.5, labelspacing=1.2)
    legend.get_title().set_fontweight('bold')
    legend.get_title().set_fontsize(14)
    
    ax.axis('off')
    
    # Adjust layout
    plt.tight_layout()
    
    # Save plot
    plt.savefig(output_path, dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close()
    
    print(f"Spider chart saved to: {output_path}")

def main():
    """Main function to generate spider chart."""
    # Set up paths
    results_dir = Path("../../../src/results")
    plots_dir = Path("../plots")
    plots_dir.mkdir(exist_ok=True)
    
    # Load experiment data
    experiments_data = {}
    
    experiment_names = {
        4: 'Coding Models Only',
        5: 'Non-code Tasks + Reasoning',
        6: 'Both Tasks + Reasoning'
    }
    
    for exp_num in [4, 5, 6]:
        exp_path = results_dir / f"experiment_{exp_num}.xlsx"
        print(f"Loading {exp_path}...")
        experiments_data[exp_num] = load_experiment_data(exp_path)
        
        # Print summary statistics
        line_stats = calculate_statistics(experiments_data[exp_num]['line_coverage'])
        branch_stats = calculate_statistics(experiments_data[exp_num]['branch_coverage'])
        compilation_stats = calculate_statistics(experiments_data[exp_num]['compilation_rate'])
        scenarios_stats = calculate_statistics(experiments_data[exp_num]['generated_scenarios'])
        bug_detection_rate = (experiments_data[exp_num]['bug_detected'].sum() / len(experiments_data[exp_num]['bug_detected'])) * 100
        
        exp_name = experiment_names[exp_num]
        print(f"Experiment {exp_num} ({exp_name}):")
        print(f"  Line coverage = {line_stats['mean']:.2f}% ± {line_stats['std']:.2f}% (n={line_stats['count']} repos)")
        print(f"  Branch coverage = {branch_stats['mean']:.2f}% ± {branch_stats['std']:.2f}% (n={branch_stats['count']} repos)")
        print(f"  Compilation rate = {compilation_stats['mean']:.2f}% ± {compilation_stats['std']:.2f}% (n={compilation_stats['count']} repos)")
        print(f"  Generated scenarios = {scenarios_stats['mean']:.2f} ± {scenarios_stats['std']:.2f} (n={scenarios_stats['count']} repos)")
        print(f"  Bug detection rate = {bug_detection_rate:.2f}% ({experiments_data[exp_num]['bug_detected'].sum()}/10 repos)")
    
    # Create spider chart
    print("\nCreating spider chart...")
    create_spider_chart(experiments_data, plots_dir / "spider_chart_comparison.pdf")
    create_spider_chart(experiments_data, plots_dir / "spider_chart_comparison.png")
    
    print(f"\nSpider chart generated successfully!")
    print(f"Files saved in: {plots_dir.absolute()}")

if __name__ == "__main__":
    main()
