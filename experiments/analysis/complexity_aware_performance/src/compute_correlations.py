#!/usr/bin/env python3
"""
Compute correlations between Maintainability Index (MI) and performance metrics.

Calculates:
- Pearson correlation (r, p-value, 95% CI via Fisher z transform) for MI vs:
  * Line coverage
  * Branch coverage
  * Bug detection rate
- Spearman correlation (rho, p-value) for the same
- Simple linear regression slopes with 95% CI
- FDR correction for multiple testing (optional)
"""

import pandas as pd
import numpy as np
from scipy.stats import pearsonr, spearmanr
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')


def fisher_ci(r, n, alpha=0.05):
    """Calculate 95% confidence interval for Pearson r via Fisher z transform.
    
    Args:
        r: Pearson correlation coefficient
        n: Sample size
        alpha: Significance level (default 0.05 for 95% CI)
    
    Returns:
        (r_lower, r_upper): Confidence interval bounds
    """
    # Handle edge cases
    if abs(r) >= 0.999:
        return (r, r)
    
    # Fisher z transform
    z = 0.5 * np.log((1 + r) / (1 - r))
    se_z = 1 / np.sqrt(n - 3)
    
    # Critical value for alpha/2 (two-tailed)
    z_crit = stats.norm.ppf(1 - alpha / 2)
    
    # CI in z-space
    z_lower = z - z_crit * se_z
    z_upper = z + z_crit * se_z
    
    # Back-transform to r
    r_lower = (np.exp(2 * z_lower) - 1) / (np.exp(2 * z_lower) + 1)
    r_upper = (np.exp(2 * z_upper) - 1) / (np.exp(2 * z_upper) + 1)
    
    return (r_lower, r_upper)


def load_and_aggregate_data(experiment_path):
    """Load experiment data and aggregate to per-repository means.
    
    Args:
        experiment_path: Path to experiment_11.xlsx
    
    Returns:
        DataFrame with one row per repository (31 repos) with averaged metrics
    """
    # Read Excel file - row 1 and 2 are titles, data from row 3 to 157
    df = pd.read_excel(experiment_path, header=1)
    # Skip row 1 (0-based index 0) and take rows 3-157
    # After header=1, Excel row 3 is pandas index 0, Excel row 157 is pandas index 154
    df = df.iloc[:155]  # Take rows from index 0 to 154 (Excel rows 3 to 157)
    
    # Column indices (0-based)
    mi_index = 16  # MI
    line_cov_index = 27  # Line coverage (column AB)
    branch_cov_index = 28  # Branch coverage (column AC)
    bug_detected_index = 25  # Bug detected (column Z)
    
    # Compilation data for compilation rate
    normal_scenarios_index = 18  # Column S
    bug_hunting_scenarios_index = 40  # Column AO
    compiled_normal_index = 20  # Column U
    compiled_bug_hunting_index = 42  # Column AQ
    
    # Extract data
    mi_raw = pd.to_numeric(df.iloc[:, mi_index], errors='coerce')
    line_coverage_raw = pd.to_numeric(df.iloc[:, line_cov_index], errors='coerce')
    branch_coverage_raw = pd.to_numeric(df.iloc[:, branch_cov_index], errors='coerce')
    bug_detected_raw = df.iloc[:, bug_detected_index]
    normal_scenarios = pd.to_numeric(df.iloc[:, normal_scenarios_index], errors='coerce').fillna(0)
    bug_hunting_scenarios = pd.to_numeric(df.iloc[:, bug_hunting_scenarios_index], errors='coerce').fillna(0)
    compiled_normal = pd.to_numeric(df.iloc[:, compiled_normal_index], errors='coerce').fillna(0)
    compiled_bug_hunting = pd.to_numeric(df.iloc[:, compiled_bug_hunting_index], errors='coerce').fillna(0)
    
    # Calculate compilation rate per row
    total_scenarios = normal_scenarios + bug_hunting_scenarios
    total_compiled = compiled_normal + compiled_bug_hunting
    compilation_rate_raw = np.where(total_scenarios > 0,
                                   (total_compiled / total_scenarios) * 100,
                                   0)
    compilation_rate_raw = pd.Series(compilation_rate_raw)
    
    # Convert bug_detected to boolean
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
        repo_bug_detected = bug_detected_bool.iloc[start_idx:end_idx]
        repo_compilation = compilation_rate_raw.iloc[start_idx:end_idx]
        
        # Calculate averages for this repository
        repo_avg_mi = repo_mi.mean()
        repo_avg_line_cov = repo_line_cov.mean()
        repo_avg_branch_cov = repo_branch_cov.mean()
        repo_bug_detection_rate = (repo_bug_detected.sum() / len(repo_bug_detected)) * 100  # Percentage
        repo_avg_compilation = repo_compilation.mean()
        
        repo_data.append({
            'MI': repo_avg_mi,
            'line_cov': repo_avg_line_cov,
            'branch_cov': repo_avg_branch_cov,
            'bug_det': repo_bug_detection_rate,
            'comp_rate': repo_avg_compilation
        })
    
    # Create DataFrame
    agg_df = pd.DataFrame(repo_data)
    
    # Remove rows with missing values
    agg_df = agg_df.dropna()
    
    return agg_df


def compute_correlations_and_regression(agg_df):
    """Compute correlations and regression statistics for MI vs metrics.
    
    Args:
        agg_df: DataFrame with columns MI, line_cov, branch_cov, bug_det, comp_rate
    
    Returns:
        DataFrame with results for each metric
    """
    n = len(agg_df)
    x = agg_df['MI'].values
    
    results = []
    
    # Metrics to analyze
    metrics = {
        'line_cov': 'Line Coverage',
        'branch_cov': 'Branch Coverage',
        'bug_det': 'Bug Detection Rate'
    }
    
    for col_name, metric_name in metrics.items():
        y = agg_df[col_name].values
        
        # Pearson correlation
        r, p_pearson = pearsonr(x, y)
        r_lower, r_upper = fisher_ci(r, n)
        
        # Spearman correlation
        rho, p_spearman = spearmanr(x, y)
        
        # Simple linear regression: y = a + b*MI
        X = sm.add_constant(x)
        model = sm.OLS(y, X).fit()
        b = model.params[1]  # slope
        ci = model.conf_int(alpha=0.05)
        # CI is a DataFrame, access by index and column
        if hasattr(ci, 'iloc'):
            b_lower = ci.iloc[1, 0]  # slope CI lower
            b_upper = ci.iloc[1, 1]  # slope CI upper
        else:
            # If it's a numpy array, use indexing
            b_lower = ci[1, 0]
            b_upper = ci[1, 1]
        r2 = model.rsquared
        
        result = {
            'metric': metric_name,
            'pearson_r': r,
            'pearson_p': p_pearson,
            'pearson_ci95_lower': r_lower,
            'pearson_ci95_upper': r_upper,
            'spearman_rho': rho,
            'spearman_p': p_spearman,
            'slope_per_MI': b,
            'slope_ci95_lower': b_lower,
            'slope_ci95_upper': b_upper,
            'r2': r2
        }
        results.append(result)
    
    results_df = pd.DataFrame(results)
    
    # FDR correction for Pearson p-values
    rej, p_adj, _, _ = multipletests(results_df['pearson_p'], method='fdr_bh', alpha=0.05)
    results_df['pearson_p_adj'] = p_adj
    results_df['pearson_sig_fdr'] = rej
    
    return results_df


def print_results(results_df, n_repos):
    """Print results in a readable list format.
    
    Args:
        results_df: DataFrame with correlation results
        n_repos: Number of repositories
    """
    print("\n" + "=" * 80)
    print("CORRELATION ANALYSIS: Maintainability Index vs Performance Metrics")
    print("=" * 80)
    print(f"\nSample size: {n_repos} repositories")
    print("\nResults:")
    print("-" * 80)
    
    for idx, (_, row) in enumerate(results_df.iterrows(), 1):
        print(f"\n{idx}. {row['metric']}:")
        print(f"   • Pearson r = {row['pearson_r']:.4f} (95% CI [{row['pearson_ci95_lower']:.4f}, {row['pearson_ci95_upper']:.4f}])")
        print(f"   • Pearson p = {row['pearson_p']:.4f} (FDR-adjusted: {row['pearson_p_adj']:.4f}, {'significant' if row['pearson_sig_fdr'] else 'not significant'})")
        print(f"   • Spearman ρ = {row['spearman_rho']:.4f} (p = {row['spearman_p']:.4f})")
        print(f"   • Linear regression slope = {row['slope_per_MI']:.4f} per MI point (95% CI [{row['slope_ci95_lower']:.4f}, {row['slope_ci95_upper']:.4f}])")
        print(f"   • R² = {row['r2']:.4f}")
        print(f"   • Interpretation: +10 MI points ≈ +{row['slope_per_MI']*10:.2f} percentage points")
    
    print("\n" + "=" * 80)


def main():
    """Main function."""
    # Set up paths
    results_dir = Path(__file__).parent.parent.parent.parent / "src" / "results"
    experiment_path = results_dir / "experiment_11.xlsx"
    
    print(f"Loading data from {experiment_path}...")
    agg_df = load_and_aggregate_data(experiment_path)
    
    print(f"Loaded data for {len(agg_df)} repositories")
    print(f"MI range: {agg_df['MI'].min():.2f} - {agg_df['MI'].max():.2f}")
    print(f"Line coverage range: {agg_df['line_cov'].min():.2f}% - {agg_df['line_cov'].max():.2f}%")
    print(f"Branch coverage range: {agg_df['branch_cov'].min():.2f}% - {agg_df['branch_cov'].max():.2f}%")
    print(f"Bug detection rate range: {agg_df['bug_det'].min():.2f}% - {agg_df['bug_det'].max():.2f}%")
    
    print("\nComputing correlations and regression statistics...")
    results_df = compute_correlations_and_regression(agg_df)
    
    print_results(results_df, len(agg_df))


if __name__ == "__main__":
    main()

