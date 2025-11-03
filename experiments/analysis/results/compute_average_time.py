#!/usr/bin/env python3
"""
Calculate average time per row and LLM response time from experiment_11.xlsx.

Computes:
- Average time per row (column AS, in seconds)
- Average LLM response time (column AT, in seconds)
- Percentage of time spent by LLM
- Presents results in minutes and seconds (rounded)
"""

import pandas as pd
from pathlib import Path

# Path to experiment_11.xlsx
excel_path = Path(__file__).parent.parent.parent / "src" / "results" / "experiment_11.xlsx"

# Read the Excel file
# Row 1 and 2 are titles, data starts from row 3 (0-based index 2) to row 157 (0-based index 156)
# Use header=1 to get column names from row 2 (Excel row 2)
df = pd.read_excel(excel_path, header=1)
# Take rows from index 0 to 154 (Excel rows 3 to 157)
df = df.iloc[:155]

# Column AS is at index 44 (0-based) - Total time
# Column AT is at index 45 (0-based) - LLM response time
# A=0, B=1, ..., Z=25, AA=26, AB=27, ..., AS=44, AT=45
column_as_index = 44
column_at_index = 45

# Extract column AS (total time in seconds)
time_seconds = df.iloc[:, column_as_index]
time_seconds = pd.to_numeric(time_seconds, errors='coerce').fillna(0)

# Extract column AT (LLM response time in seconds)
llm_time_seconds = df.iloc[:, column_at_index]
llm_time_seconds = pd.to_numeric(llm_time_seconds, errors='coerce').fillna(0)

# Calculate total time and average
total_seconds = float(time_seconds.sum())
total_rows = len(time_seconds)
average_seconds = total_seconds / total_rows if total_rows > 0 else 0

# Calculate total LLM time and average
total_llm_seconds = float(llm_time_seconds.sum())
average_llm_seconds = total_llm_seconds / total_rows if total_rows > 0 else 0

# Calculate percentage of time spent by LLM
llm_percentage = (average_llm_seconds / average_seconds * 100) if average_seconds > 0 else 0

# Convert to minutes and seconds (rounded)
average_minutes_full = int(average_seconds // 60)
average_seconds_remaining = int(round(average_seconds % 60))

average_llm_minutes_full = int(average_llm_seconds // 60)
average_llm_seconds_remaining = int(round(average_llm_seconds % 60))

# Print results
print("=" * 60)
print("AVERAGE TIME PER ROW")
print("=" * 60)
print(f"\nTotal time: {total_seconds:.2f} seconds ({total_seconds/60:.2f} minutes)")
print(f"Number of rows: {total_rows}")
print(f"Average time per row: {average_seconds:.2f} seconds")
print(f"Average time per row: {average_minutes_full} minutes {average_seconds_remaining} seconds")
print("\n" + "-" * 60)
print("LLM RESPONSE TIME")
print("-" * 60)
print(f"\nTotal LLM time: {total_llm_seconds:.2f} seconds ({total_llm_seconds/60:.2f} minutes)")
print(f"Average LLM time per row: {average_llm_seconds:.2f} seconds")
print(f"Average LLM time per row: {average_llm_minutes_full} minutes {average_llm_seconds_remaining} seconds")
print(f"\nPercentage of time spent by LLM: {llm_percentage:.2f}%")
print("=" * 60)

