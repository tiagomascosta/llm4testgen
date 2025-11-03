#!/usr/bin/env python3
"""
Compute baseline metrics for the Sankey diagram from experiment_11.xlsx.

- Total tests generated = Ordinary (column S) + Bug hunting (column AO)
- Compiled tests        = Compiled ordinary (column U) + Compiled bug hunting (column AQ)
- Passed tests          = Compiled - (Assertion Errors (AE) + Runtime Errors (AF) + Timeout (AI)) per row
- Potential Bugs tests  = Column AX
- Test suite tests      = Column X (number of test cases in the final suite)
- Bugs revealed tests   = Column AW
- Compilation rate (%)  = 100 * Compiled / Total (0 if Total == 0)
- Non-compilation (%)   = 100 - Compilation rate
- Individual pass rate  = 100 * Passed / Total (0 if Total == 0)
- Potential Bugs rate   = 100 * PotentialBugs / Total (0 if Total == 0)
- Test suite rate       = 100 * TestSuite / Total (0 if Total == 0)
- Bugs revealed rate    = 100 * BugsRevealed / Total (0 if Total == 0)

Notes:
- Columns are 0-based indexed as follows in pandas iloc (skip the first header row):
  S  -> index 18 (Ordinary scenarios generated)
  U  -> index 20 (Compiled ordinary scenarios)
  X  -> index 23 (Number of test cases in the test suite)
  AO -> index 40 (Bug hunting scenarios generated)
  AQ -> index 42 (Compiled bug hunting scenarios)
  AE -> index 30 (Assertion Errors)
  AF -> index 31 (Runtime Errors)
  AI -> index 34 (Timeouts)
  AW -> index 48 (Bugs revealed)
  AX -> index 49 (Potential Bugs)

Outputs a small report to stdout.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

# experiments/src/results/experiment_11.xlsx relative to this script
DEFAULT_XLSX = (Path(__file__).resolve().parents[3] / "src" / "results" / "experiment_11.xlsx")

# Column indices (0-based for pandas iloc) as per the project's convention
IDX_S  = 18  # Ordinary scenarios generated
IDX_U  = 20  # Compiled ordinary scenarios
IDX_X  = 23  # Test suite size (final number of test cases)
IDX_AO = 40  # Bug hunting scenarios generated
IDX_AQ = 42  # Compiled bug hunting scenarios
IDX_AE = 30  # Assertion errors
IDX_AF = 31  # Runtime errors
IDX_AI = 34  # Timeouts
IDX_AW = 48  # Bugs revealed
IDX_AX = 49  # Potential Bugs


def load_dataframe(xlsx_path: Path) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path)
    return df


def safe_numeric(series: pd.Series) -> pd.Series:
    """Coerce to numeric and treat NaNs as 0."""
    return pd.to_numeric(series, errors="coerce").fillna(0)


def compute_totals(df: pd.DataFrame) -> dict:
    # Skip header row at index 0
    ordinary_generated = safe_numeric(df.iloc[1:, IDX_S])
    bug_generated      = safe_numeric(df.iloc[1:, IDX_AO])

    compiled_ordinary  = safe_numeric(df.iloc[1:, IDX_U])
    compiled_bug       = safe_numeric(df.iloc[1:, IDX_AQ])

    assert_errors      = safe_numeric(df.iloc[1:, IDX_AE])
    runtime_errors     = safe_numeric(df.iloc[1:, IDX_AF])
    timeouts           = safe_numeric(df.iloc[1:, IDX_AI])

    potential_bugs     = safe_numeric(df.iloc[1:, IDX_AX])
    bugs_revealed      = safe_numeric(df.iloc[1:, IDX_AW])
    suite_tests        = safe_numeric(df.iloc[1:, IDX_X])

    compiled_per_row = compiled_ordinary + compiled_bug
    passed_per_row = compiled_per_row - (assert_errors + runtime_errors + timeouts)
    # Clamp negatives to 0 just in case
    passed_per_row = passed_per_row.clip(lower=0)

    total_tests = float(ordinary_generated.sum() + bug_generated.sum())
    compiled_tests = float(compiled_per_row.sum())
    passed_tests = float(passed_per_row.sum())
    potential_bugs_tests = float(potential_bugs.sum())
    bugs_revealed_tests = float(bugs_revealed.sum())
    suite_tests_total = float(suite_tests.sum())

    if total_tests > 0:
        compilation_rate = (compiled_tests / total_tests) * 100.0
        pass_rate_total = (passed_tests / total_tests) * 100.0
        potential_bugs_rate = (potential_bugs_tests / total_tests) * 100.0
        bugs_revealed_rate = (bugs_revealed_tests / total_tests) * 100.0
        suite_rate = (suite_tests_total / total_tests) * 100.0
    else:
        compilation_rate = 0.0
        pass_rate_total = 0.0
        potential_bugs_rate = 0.0
        bugs_revealed_rate = 0.0
        suite_rate = 0.0

    non_compilation_rate = max(0.0, 100.0 - compilation_rate)

    return {
        "total_tests": total_tests,
        "compiled_tests": compiled_tests,
        "passed_tests": passed_tests,
        "potential_bugs_tests": potential_bugs_tests,
        "bugs_revealed_tests": bugs_revealed_tests,
        "suite_tests": suite_tests_total,
        "compilation_rate_percent": compilation_rate,
        "non_compilation_rate_percent": non_compilation_rate,
        "pass_rate_over_total_percent": pass_rate_total,
        "potential_bugs_rate_percent": potential_bugs_rate,
        "bugs_revealed_rate_percent": bugs_revealed_rate,
        "suite_rate_percent": suite_rate,
    }


def main():
    parser = argparse.ArgumentParser(description="Compute Sankey base metrics from experiment_11.xlsx")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX, help="Path to experiment_11.xlsx")
    args = parser.parse_args()

    print(f"Using XLSX: {args.xlsx}")
    if not args.xlsx.exists():
        raise SystemExit(f"File not found: {args.xlsx}")

    df = load_dataframe(args.xlsx)
    results = compute_totals(df)

    print("Sankey Base Metrics (Experiment 11)")
    print(f"- Total tests generated:      {int(results['total_tests'])}")
    print(f"- Compiled tests:             {int(results['compiled_tests'])}")
    print(f"- Passed tests:               {int(results['passed_tests'])}")
    print(f"- Potential Bugs tests:       {int(results['potential_bugs_tests'])}")
    print(f"- Bugs revealed tests:        {int(results['bugs_revealed_tests'])}")
    print(f"- Test suite tests:           {int(results['suite_tests'])}")
    print(f"- Compilation rate:           {results['compilation_rate_percent']:.1f}%")
    print(f"- Non-compilation rate:       {results['non_compilation_rate_percent']:.1f}%")
    print(f"- Individual pass rate:       {results['pass_rate_over_total_percent']:.1f}%")
    print(f"- Potential Bugs rate:        {results['potential_bugs_rate_percent']:.1f}%")
    print(f"- Bugs revealed rate:         {results['bugs_revealed_rate_percent']:.1f}%")
    print(f"- Test suite rate:            {results['suite_rate_percent']:.1f}%")


if __name__ == "__main__":
    main()
