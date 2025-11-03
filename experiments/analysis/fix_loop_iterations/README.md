# Fix Loop Iteration Analysis

This analysis creates publication-quality plots for the master's thesis showing the performance of fix loop iterations.

## Experiments Analyzed

- **Experiment 1**: 0 fix iterations (baseline)
- **Experiment 2**: 4 fix iterations  
- **Experiment 3**: 8 fix iterations

## Generated Plots

### Left Figure — Compile-Fix Loop Performance
- **X-axis**: Number of fix iterations (0, 4, 8)
- **Y-axis**: Average line coverage (%)
- **Features**: 
  - Solid line with markers showing line coverage trend
  - Shaded bands representing ±1 standard deviation
  - Publication-ready styling for LaTeX

### Right Figure — Runtime-Fix Loop Performance  
- **X-axis**: Number of fix iterations (0, 4, 8)
- **Y-axis**: Average line coverage (%)
- **Features**:
  - Same visual conventions as compile-fix plot
  - Different color scheme for distinction
  - Consistent styling and formatting

## Results Summary

Based on the experimental data:

- **0 iterations**: 26.75% ± 39.71% line coverage (n=50)
- **4 iterations**: 46.93% ± 47.77% line coverage (n=50)  
- **8 iterations**: 44.09% ± 47.55% line coverage (n=50)

## Files Generated

- `compile_fix_performance.pdf` - Compile-fix plot (PDF format)
- `compile_fix_performance.png` - Compile-fix plot (PNG format)
- `runtime_fix_performance.pdf` - Runtime-fix plot (PDF format)
- `runtime_fix_performance.png` - Runtime-fix plot (PNG format)

## Usage

```bash
# Activate virtual environment
source ../../../.venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Run analysis
cd src
python fix_loop_analysis.py
```

## Plot Specifications

- **Size**: 6×4.5 inches (optimized for A4 page width)
- **Resolution**: 300 DPI (publication quality)
- **Format**: PDF and PNG outputs
- **Styling**: Publication-ready with proper fonts, legends, and grid
- **Colors**: Distinct color schemes for each plot type
- **Error representation**: ±1 standard deviation bands
