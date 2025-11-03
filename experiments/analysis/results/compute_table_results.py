#!/usr/bin/env python3
"""
Compute results for thesis tables from experiment_11.xlsx.

Results computed:
- Average tests per test suite: Mean of column X (number of test cases in test suite)
- Average assertions per test: Mean of (column W / column X) for each row
- Average line coverage: Average of repository averages (each repo has 5 runs, column AB)
- Average branch coverage: Average of repository averages (each repo has 5 runs, column AC)
- Bug detection rate: Percentage of repositories where at least one run revealed a bug (column Z)
- Potential bugs rate: Percentage of potentially bug revealing tests out of all tests (columns S, AO, AX)
- Compilation rate: Average of repository compilation rates (each repo has 5 runs, columns S, AO, AQ)
- First try compilation rate: Percentage of compiled tests that compiled on first try (columns U, AQ, AV)
- Compilation loop fix success rate: Success rate of compilation fix loop (columns S, AO, U, AQ, AV)
- Runtime errors rate: Percentage of runtime errors out of total tests (column AM)
- Assertion errors rate: Percentage of assertion errors out of total tests (column AL)
- Non-flaky passing tests rate: Percentage of non-flaky passing tests out of total tests (column X)
"""

import pandas as pd
from pathlib import Path

# Path to experiment_11.xlsx
excel_path = Path(__file__).parent.parent.parent / "src" / "results" / "experiment_11.xlsx"

# Read the Excel file
# Row 1 and 2 are titles, data starts from row 3 (0-based index 2) to row 157 (0-based index 156)
# Use header=1 to get column names from row 2 (Excel row 2)
df = pd.read_excel(excel_path, header=1)
# Skip row 1 (0-based index 0) which comes after header, and take only rows 3-157
# After header=1, row 3 becomes index 0, row 4 becomes index 1, etc.
# So we want to skip nothing (since header=1 already skips row 1) and take rows 0-154 (which are Excel rows 3-157)
# Actually, if header=1, Excel row 2 is header (pandas index -1), Excel row 3 is pandas index 0
# Excel row 157 is pandas index 154 (157 - 3 = 154)
# So we slice from index 0 to 154 inclusive, which is [:155]
df = df.iloc[:155]  # Take rows from index 0 to 154 (Excel rows 3 to 157)

# Column X is at index 23 (0-based) - Number of test cases in test suite
column_x_index = 23
column_x_name = df.columns[column_x_index]

# Extract column X values
test_suite_tests = df.iloc[:, column_x_index]

# Calculate average tests per test suite
avg_tests_per_suite = test_suite_tests.mean()

# Column W is at index 22 (0-based) - Number of assertions
column_w_index = 22
column_w_name = df.columns[column_w_index]

# Extract column W values (assertions)
assertions = df.iloc[:, column_w_index]
# Extract column X values (tests) - already have test_suite_tests

# Calculate assertions per test for each row (avoiding division by zero)
assertions_per_test = []
for i in range(len(df)):
    if test_suite_tests.iloc[i] > 0:
        ratio = assertions.iloc[i] / test_suite_tests.iloc[i]
        assertions_per_test.append(ratio)
    # Skip rows where test count is 0

# Calculate average assertions per test
avg_assertions_per_test = pd.Series(assertions_per_test).mean() if assertions_per_test else 0

# Column AB is at index 27 (0-based) - Line coverage
# A=0, B=1, ..., Z=25, AA=26, AB=27
column_ab_index = 27

# Extract column AB values (line coverage)
line_coverage = df.iloc[:, column_ab_index]

# Group into 31 repositories, each with 5 runs
# 155 rows = 31 repositories × 5 runs each
num_repos = 31
runs_per_repo = 5

# Calculate average for each repository
repo_averages = []
for i in range(num_repos):
    start_idx = i * runs_per_repo
    end_idx = start_idx + runs_per_repo
    repo_runs = line_coverage.iloc[start_idx:end_idx]
    # Calculate average for this repository (handle NaN values)
    repo_avg = repo_runs.mean()
    if pd.notna(repo_avg):  # Only include if not NaN
        repo_averages.append(repo_avg)

# Calculate average of repository averages
avg_line_coverage = pd.Series(repo_averages).mean() if repo_averages else 0

# Column AC is at index 28 (0-based) - Branch coverage
# A=0, B=1, ..., Z=25, AA=26, AB=27, AC=28
column_ac_index = 28

# Extract column AC values (branch coverage)
branch_coverage = df.iloc[:, column_ac_index]

# Group into 31 repositories, each with 5 runs (same structure as line coverage)
# Calculate average for each repository
branch_repo_averages = []
for i in range(num_repos):
    start_idx = i * runs_per_repo
    end_idx = start_idx + runs_per_repo
    repo_runs = branch_coverage.iloc[start_idx:end_idx]
    # Calculate average for this repository (handle NaN values)
    repo_avg = repo_runs.mean()
    if pd.notna(repo_avg):  # Only include if not NaN
        branch_repo_averages.append(repo_avg)

# Calculate average of repository averages
avg_branch_coverage = pd.Series(branch_repo_averages).mean() if branch_repo_averages else 0

# Column Z is at index 25 (0-based) - Boolean indicating if bug was revealed
# A=0, B=1, ..., Z=25
column_z_index = 25

# Extract column Z values (bug revealed boolean)
bug_revealed = df.iloc[:, column_z_index]

# Check for each repository if at least one run revealed a bug
repos_with_bug = 0
for i in range(num_repos):
    start_idx = i * runs_per_repo
    end_idx = start_idx + runs_per_repo
    repo_runs = bug_revealed.iloc[start_idx:end_idx]
    # Check if any of the 5 runs has True/1 (bug revealed)
    # Convert to boolean properly (handle different boolean representations)
    has_bug = False
    for val in repo_runs:
        # Check for True, 1, "True", "1", etc.
        if pd.notna(val):
            if isinstance(val, bool):
                has_bug = has_bug or val
            elif isinstance(val, (int, float)):
                has_bug = has_bug or (val == 1 or val == 1.0)
            elif isinstance(val, str):
                has_bug = has_bug or (val.lower() in ['true', '1', 'yes'])
    if has_bug:
        repos_with_bug += 1

# Calculate bug detection rate (percentage of repositories that detected bug)
bug_detection_rate = (repos_with_bug / num_repos) * 100

# Potential bugs rate calculation (same as Sankey diagram)
# Column S is at index 18 - Ordinary scenarios generated
# Column AO is at index 40 - Bug hunting scenarios generated
# Column AX is at index 49 - Potential Bugs
column_s_index = 18
column_ao_index = 40
column_ax_index = 49

# Extract columns
ordinary_generated = df.iloc[:, column_s_index]
bug_generated = df.iloc[:, column_ao_index]
potential_bugs = df.iloc[:, column_ax_index]

# Convert to numeric, handling NaN values
ordinary_generated = pd.to_numeric(ordinary_generated, errors="coerce").fillna(0)
bug_generated = pd.to_numeric(bug_generated, errors="coerce").fillna(0)
potential_bugs = pd.to_numeric(potential_bugs, errors="coerce").fillna(0)

# Calculate totals
total_tests = float(ordinary_generated.sum() + bug_generated.sum())
potential_bugs_total = float(potential_bugs.sum())

# Calculate potential bugs rate
if total_tests > 0:
    potential_bugs_rate = (potential_bugs_total / total_tests) * 100.0
else:
    potential_bugs_rate = 0.0

# Compilation rate calculation (average of repository averages)
# Column S is at index 18 - Ordinary scenarios generated
# Column AO is at index 40 - Bug hunting scenarios generated
# Column U is at index 20 - Compiled ordinary scenarios
# Column AQ is at index 42 - Compiled bug hunting scenarios
column_u_index = 20
column_aq_index = 42

# Extract columns (already have ordinary_generated and bug_generated)
compiled_ordinary = df.iloc[:, column_u_index]
compiled_ordinary = pd.to_numeric(compiled_ordinary, errors="coerce").fillna(0)
compiled_bug_hunting = df.iloc[:, column_aq_index]
compiled_bug_hunting = pd.to_numeric(compiled_bug_hunting, errors="coerce").fillna(0)

# Total compiled tests = compiled ordinary + compiled bug hunting
compiled_tests = compiled_ordinary + compiled_bug_hunting

# Calculate compilation rate for each repository
compilation_rates = []
for i in range(num_repos):
    start_idx = i * runs_per_repo
    end_idx = start_idx + runs_per_repo
    
    # For this repository, sum total tests generated and tests compiled across 5 runs
    repo_ordinary = ordinary_generated.iloc[start_idx:end_idx].sum()
    repo_bug_gen = bug_generated.iloc[start_idx:end_idx].sum()
    repo_compiled = compiled_tests.iloc[start_idx:end_idx].sum()
    
    repo_total = repo_ordinary + repo_bug_gen
    
    # Calculate compilation rate for this repository
    if repo_total > 0:
        repo_compilation_rate = (repo_compiled / repo_total) * 100.0
        compilation_rates.append(repo_compilation_rate)

# Calculate average of repository compilation rates
avg_compilation_rate = pd.Series(compilation_rates).mean() if compilation_rates else 0

# First try compilation rate calculation
# Column AV is at index 47 - Number of tests that compiled on first try
# A=0, B=1, ..., Z=25, AA=26, AB=27, AC=28, AD=29, AE=30, AF=31, AG=32, AH=33, AI=34,
# AJ=35, AK=36, AL=37, AM=38, AN=39, AO=40, AP=41, AQ=42, AR=43, AS=44, AT=45, AU=46, AV=47
column_av_index = 47

# Extract column AV (tests that compiled on first try)
first_try_compiled = df.iloc[:, column_av_index]
first_try_compiled = pd.to_numeric(first_try_compiled, errors="coerce").fillna(0)

# Calculate totals across all rows (not per repository)
# Total tests generated = sum of (S + AO) - already calculated as total_tests
total_first_try = float(first_try_compiled.sum())  # Total of AV across all rows

# Print intermediate values for verification
print("\n" + "=" * 60)
print("FIRST TRY COMPILATION RATE - INTERMEDIATE VALUES")
print("=" * 60)
print(f"Total tests generated (S + AO): {total_tests:.0f}")
print(f"Total tests compiled on first try (AV): {total_first_try:.0f}")
print(f"First try compilation rate: ({total_first_try:.0f} / {total_tests:.0f}) * 100")
print("=" * 60 + "\n")

# Calculate first try compilation rate (percentage of total tests generated)
if total_tests > 0:
    first_try_compilation_rate = (total_first_try / total_tests) * 100.0
else:
    first_try_compilation_rate = 0.0

# Compilation loop fix success rate calculation
# Step 1: Number of tests needing compilation fix loop = total tests - tests compiled on first try
tests_needing_fix_loop = total_tests - total_first_try

# Step 2: Number of tests that didn't compile = total tests - total compiled tests
total_compiled_tests = float(compiled_tests.sum())  # Total of (U + AQ) across all rows
tests_didnt_compile = total_tests - total_compiled_tests

# Step 3: Insuccess rate = (tests that didn't compile) / (tests needing compile fix loop)
if tests_needing_fix_loop > 0:
    insuccess_rate = tests_didnt_compile / tests_needing_fix_loop
else:
    insuccess_rate = 0.0

# Step 4: Success rate = 1 - insuccess rate
compilation_loop_fix_success_rate = (1 - insuccess_rate) * 100.0

# Print intermediate values for verification
print("\n" + "=" * 60)
print("COMPILATION LOOP FIX SUCCESS RATE - INTERMEDIATE VALUES")
print("=" * 60)
print(f"Total tests generated: {total_tests:.0f}")
print(f"Tests compiled on first try (AV): {total_first_try:.0f}")
print(f"Tests needing compilation fix loop: {tests_needing_fix_loop:.0f}")
print(f"Total compiled tests (U + AQ): {total_compiled_tests:.0f}")
print(f"Tests that didn't compile: {tests_didnt_compile:.0f}")
print(f"Insuccess rate: {tests_didnt_compile:.0f} / {tests_needing_fix_loop:.0f} = {insuccess_rate:.4f}")
print(f"Success rate: 1 - {insuccess_rate:.4f} = {compilation_loop_fix_success_rate:.2f}%")
print("=" * 60 + "\n")

# Runtime errors rate calculation
# Column AM is at index 38 (0-based) - Runtime errors
# A=0, B=1, ..., Z=25, AA=26, AB=27, AC=28, AD=29, AE=30, AF=31, AG=32, AH=33, AI=34,
# AJ=35, AK=36, AL=37, AM=38
column_am_index = 38

# Extract column AM (runtime errors)
runtime_errors = df.iloc[:, column_am_index]
runtime_errors = pd.to_numeric(runtime_errors, errors="coerce").fillna(0)

# Calculate runtime errors rate
total_runtime_errors = float(runtime_errors.sum())
if total_tests > 0:
    runtime_errors_rate = (total_runtime_errors / total_tests) * 100.0
else:
    runtime_errors_rate = 0.0

# Assertion errors rate calculation
# Column AL is at index 37 (0-based) - Assertion errors
column_al_index = 37

# Extract column AL (assertion errors)
assertion_errors = df.iloc[:, column_al_index]
assertion_errors = pd.to_numeric(assertion_errors, errors="coerce").fillna(0)

# Calculate assertion errors rate
total_assertion_errors = float(assertion_errors.sum())
if total_tests > 0:
    assertion_errors_rate = (total_assertion_errors / total_tests) * 100.0
else:
    assertion_errors_rate = 0.0

# Non-flaky passing tests rate calculation
# Column X is at index 23 - Non-flaky passing tests (test suite tests)
# Already have test_suite_tests from earlier

# Calculate non-flaky passing tests rate
total_non_flaky = float(test_suite_tests.sum())
if total_tests > 0:
    non_flaky_rate = (total_non_flaky / total_tests) * 100.0
else:
    non_flaky_rate = 0.0

# Print results
print("=" * 60)
print("THESIS TABLE RESULTS")
print("=" * 60)
print(f"\nAverage tests per test suite: {avg_tests_per_suite:.2f}")
print(f"Average assertions per test: {avg_assertions_per_test:.2f}")
print(f"Average line coverage: {avg_line_coverage:.2f}%")
print(f"Average branch coverage: {avg_branch_coverage:.2f}%")
print(f"Bug detection rate: {bug_detection_rate:.2f}%")
print(f"Potential bugs rate: {potential_bugs_rate:.2f}%")
print(f"Compilation rate: {avg_compilation_rate:.2f}%")
print(f"First try compilation rate: {first_try_compilation_rate:.2f}%")
print(f"Compilation loop fix success rate: {compilation_loop_fix_success_rate:.2f}%")
print(f"Runtime errors rate: {runtime_errors_rate:.2f}%")
print(f"Assertion errors rate: {assertion_errors_rate:.2f}%")
print(f"Non-flaky passing tests rate: {non_flaky_rate:.2f}%")
print("=" * 60)

