#!/usr/bin/env python3
"""
Random Sankey Diagram (Plotly)
Creates a publication-quality Sankey diagram consistent with existing plot style.

Output: saves PNG and PDF in ../plots
"""

import plotly.graph_objects as go
from pathlib import Path

# Base node names
base_labels = [
    "All",           # 0
    "Compiled",      # 1
    "Accepted",      # 2
    "Potential Bugs",# 3
    "Not Compiled",      # 4
    "Pass",          # 5
    "Bugs Revealed", # 6
    "Flaky",# 7
    "RE & Timeouts",# 8
]
node_colors = [
    "#1f77b4", # All
    "#9467bd", # Compiled (purple)
    "#2ca02c", # Accepted
    "#ff7f0e", # Potential Bugs
    "#C73E1D", # Rejected
    "#6b9aa8", # Pass (muted teal)
    "#f5a623", # Bugs Revealed (muted yellow for research)
    "#C73E1D", # Flaky
    "#C73E1D", # RE & Timeouts (annotation only, not a node)
]
# Spread nodes horizontally; align terminals
node_x = [0.04, 0.28, 0.965, 0.965, 0.965, 0.60, 0.965, 0.965, 0.965]
# Preserve user-defined y positions
node_y = [0.5, 0.4, 0.57, 0.15, 0.9, 0.59, 0.40, 0.82, 0.82]  # RE & Timeouts at same x/y as Flaky node
# Flows (percentages)
source = [0, 5, 0, 1, 1, 1, 1, 5]
target = [1, 7, 4, 5, 3, 4, 6, 2]
value  = [84.5, 0.1, 15.5, 30.2, 50.1, 4.2, 0.2, 30.1]
link_colors = [
    "rgba(31,119,180,0.40)",  # All->Compiled (blue)
    "rgba(107,154,168,0.55)", # Pass->Flaky Rejected (muted teal)
    "rgba(31,119,180,0.40)", # All->Rejected (blue)
    "rgba(148,103,189,0.55)",# Compiled->Pass (purple)
    "rgba(148,103,189,0.55)",# Compiled->Potential Bugs (purple)
    "rgba(148,103,189,0.55)", # Compiled->Rejected (purple)
    "rgba(148,103,189,0.55)", # Compiled->Bugs Revealed (purple)
    "rgba(107,154,168,0.55)", # Pass->Accepted (muted teal)
]

# Compute dynamic totals for node labels
n_nodes = len(base_labels)
incoming = [0] * n_nodes
outgoing = [0] * n_nodes
for s, t, v in zip(source, target, value):
    outgoing[s] += v
    incoming[t] += v

def node_total(i: int) -> float:
    return incoming[i] if incoming[i] > 0 else outgoing[i]

node_labels = [f"{name}: {node_total(i):.1f}%" for i, name in enumerate(base_labels)]
# Correct swapped annotations for Potential Bugs/Not Compiled
node_labels[3], node_labels[4] = node_labels[4], node_labels[3]
# Fix the value for Not Compiled (node 4 value should be 15.5%)
node_labels[3] = f"Not Compiled: 15.5%"  # Explicitly set the value after swap
# Fix the value for Potential Bugs (index 4 after swap should be 50.2%)
node_labels[4] = "Potential Bugs: 50.2%"  # Explicitly set the value after swap
# Set the value for RE & Timeouts (annotation only, not a node)
node_labels[8] = "RE & Timeouts: 3.9%"

fig = go.Figure(go.Sankey(
    arrangement="fixed",
    node=dict(
        label=["" for _ in node_labels],
        color=node_colors,
        pad=20,
        thickness=22,
        x=node_x,
        y=node_y,
        line=dict(color="rgba(0,0,0,0)", width=0),
    ),
    link=dict(
        source=source,
        target=target,
        value=value,
        color=link_colors,
    ),
    valueformat=",.1f",
))

fig.update_layout(
    font=dict(family="DejaVu Sans", size=16, color="black"),
    paper_bgcolor="white",
    plot_bgcolor="white",
    margin=dict(l=120, r=80, t=40, b=10),  # Cropped bottom and right margins more
    width=1200,
    height=560,
)

# Left-of-node annotations with per-node x offsets and compact rounded backgrounds
annotations = []
shapes = []
# Per-node horizontal offsets (paper coords) tuned to minimize overlap on the right
offsets = [
    0.085,  # All (moved even further left)
    0.100,  # Compiled (moved even further left)
    0.095,  # Accepted (moved considerably to the left)
    0.115,  # Not Compiled (index 3 after swap - moved more to the left)
    0.120,  # Potential Bugs (index 4 after swap - moved further left)
    0.075,  # Pass (moved even further left)
    0.105,  # Bugs Revealed (moved further to the left)
    0.085,  # Flaky (moved very slightly more to the right)
    0.115,  # RE & Timeouts (moved more to the left)
]
# Per-node vertical offsets for annotation positioning (to align with bar centers)
# Note: Positive values move UP, negative values move DOWN
y_offsets = [
    0.0,    # All
    0.15,   # Compiled (move much further up - positive moves up)
    -0.13,  # Accepted (moved slightly down)
    -0.08,  # Not Compiled (index 3 after swap - moved slightly up)
    -0.06,  # Potential Bugs (index 4 after swap - moved down)
    -0.18,  # Pass (move slightly further down - negative moves down)
    0.20,   # Bugs Revealed (moved slightly up)
    -0.60,  # Flaky (moved very slightly down)
    -0.66,  # RE & Timeouts (moved very slightly up)
]
# Per-node box widths (wider for "Compiled")
box_widths = [
    0.12,  # All
    0.16,  # Compiled (wider to fit text)
    0.16,  # Accepted (narrower background)
    0.20,  # Not Compiled (index 3 after swap - wider to fit text)
    0.20,  # Potential Bugs (index 4 after swap - wider to fit text)
    0.12,  # Pass
    0.18,  # Bugs Revealed (wider to fit text)
    0.14,  # Flaky (adjusted to fit shorter text)
    0.20,  # RE & Timeouts (wider to fit text)
]
box_h = 0.055
radius = 0.008

# Helper to draw rounded rectangle path centered at (cx, cy)
def rounded_rect_path(cx: float, cy: float, w: float, h: float, r: float) -> str:
    x0 = cx - w / 2.0
    y0 = cy - h / 2.0
    x1 = cx + w / 2.0
    y1 = cy + h / 2.0
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    return (
        f"M {x0+r},{y0} L {x1-r},{y0} Q {x1},{y0} {x1},{y0+r} L {x1},{y1-r} Q {x1},{y1} {x1-r},{y1} "
        f"L {x0+r},{y1} Q {x0},{y1} {x0},{y1-r} L {x0},{y0+r} Q {x0},{y0} {x0+r},{y0} Z"
    )

for i, text in enumerate(node_labels):
    x_left = node_x[i] - offsets[i]  # Removed clamp to allow further left positioning
    y_annot = node_y[i] + y_offsets[i]  # Apply vertical offset for alignment
    path = rounded_rect_path(x_left, y_annot, box_widths[i], box_h, radius)
    shapes.append(dict(type="path", path=path, xref="paper", yref="paper",
                       fillcolor="rgba(245,245,245,0.90)", line=dict(color="rgba(0,0,0,0)", width=0), layer="above"))
    annotations.append(dict(x=x_left, y=y_annot, xref="paper", yref="paper", text=text, showarrow=False,
                            font=dict(family="DejaVu Sans", size=16, color="black"), align="center",
                            xanchor="center", yanchor="middle", bgcolor="rgba(0,0,0,0)"))

fig.update_layout(shapes=shapes, annotations=annotations)

# Save outputs
plots_dir = Path(__file__).parent.parent / "plots"
plots_dir.mkdir(parents=True, exist_ok=True)
fig.write_image(str(plots_dir / "random_sankey.png"), scale=3)
fig.write_image(str(plots_dir / "random_sankey.pdf"))
print(f"Saved: {plots_dir / 'random_sankey.png'}")
print(f"Saved: {plots_dir / 'random_sankey.pdf'}")


