"""
Coverage metrics data structures and calculation functions.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import json
import csv
from pathlib import Path
from utils.colors import Colors


@dataclass
class CoverageMetrics:
    """Data structure for coverage metrics."""
    
    # Raw counts
    instructions_covered: int = 0
    instructions_missed: int = 0
    branches_covered: int = 0
    branches_missed: int = 0
    lines_covered: int = 0
    lines_missed: int = 0
    
    # Target information
    target_name: str = ""
    target_type: str = "class"  # "class" or "method"
    
    def __post_init__(self):
        """Validate metrics after initialization."""
        if any(getattr(self, attr) < 0 for attr in [
            'instructions_covered', 'instructions_missed',
            'branches_covered', 'branches_missed',
            'lines_covered', 'lines_missed'
        ]):
            raise ValueError("Coverage counts cannot be negative")
    
    @property
    def instruction_coverage(self) -> float:
        """Calculate instruction coverage percentage."""
        total = self.instructions_covered + self.instructions_missed
        return (self.instructions_covered / total * 100) if total > 0 else 0.0
    
    @property
    def branch_coverage(self) -> float:
        """Calculate branch coverage percentage."""
        total = self.branches_covered + self.branches_missed
        return (self.branches_covered / total * 100) if total > 0 else 0.0
    
    @property
    def line_coverage(self) -> float:
        """Calculate line coverage percentage."""
        total = self.lines_covered + self.lines_missed
        return (self.lines_covered / total * 100) if total > 0 else 0.0
    
    @property
    def total_instructions(self) -> int:
        """Get total number of instructions."""
        return self.instructions_covered + self.instructions_missed
    
    @property
    def total_branches(self) -> int:
        """Get total number of branches."""
        return self.branches_covered + self.branches_missed
    
    @property
    def total_lines(self) -> int:
        """Get total number of lines."""
        return self.lines_covered + self.lines_missed
    
    def get_overall_coverage(self) -> float:
        """Calculate overall coverage (average of all types)."""
        coverages = []
        if self.total_instructions > 0:
            coverages.append(self.instruction_coverage)
        if self.total_branches > 0:
            coverages.append(self.branch_coverage)
        if self.total_lines > 0:
            coverages.append(self.line_coverage)
        
        return sum(coverages) / len(coverages) if coverages else 0.0
    
    def meets_threshold(self, threshold: float) -> bool:
        """Check if coverage meets the specified threshold."""
        return self.get_overall_coverage() >= threshold
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return {
            'target_name': self.target_name,
            'target_type': self.target_type,
            'instructions': {
                'covered': self.instructions_covered,
                'missed': self.instructions_missed,
                'total': self.total_instructions,
                'percentage': self.instruction_coverage
            },
            'branches': {
                'covered': self.branches_covered,
                'missed': self.branches_missed,
                'total': self.total_branches,
                'percentage': self.branch_coverage
            },
            'lines': {
                'covered': self.lines_covered,
                'missed': self.lines_missed,
                'total': self.total_lines,
                'percentage': self.line_coverage
            },
            'overall_coverage': self.get_overall_coverage()
        }
    
    def to_json(self) -> str:
        """Convert metrics to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    def __str__(self) -> str:
        """String representation of coverage metrics."""
        return f"{self.target_name} ({self.target_type}): " \
               f"Instructions {self.instructions_covered}/{self.total_instructions} ({self.instruction_coverage:.1f}%), " \
               f"Branches {self.branches_covered}/{self.total_branches} ({self.branch_coverage:.1f}%), " \
               f"Lines {self.lines_covered}/{self.total_lines} ({self.line_coverage:.1f}%)"


class CoverageReport:
    """Container for multiple coverage metrics."""
    
    def __init__(self):
        self.metrics: Dict[str, CoverageMetrics] = {}
        self.timestamp: Optional[str] = None
        self.build_system: Optional[str] = None
        self.project_name: Optional[str] = None
    
    def add_metrics(self, metrics: CoverageMetrics) -> None:
        """Add coverage metrics to the report."""
        key = f"{metrics.target_name}_{metrics.target_type}"
        self.metrics[key] = metrics
    
    def get_class_metrics(self, class_name: str) -> Optional[CoverageMetrics]:
        """Get metrics for a specific class."""
        key = f"{class_name}_class"
        return self.metrics.get(key)
    
    def get_method_metrics(self, method_name: str) -> Optional[CoverageMetrics]:
        """Get metrics for a specific method."""
        key = f"{method_name}_method"
        return self.metrics.get(key)
    
    def get_overall_coverage(self) -> float:
        """Calculate overall coverage across all metrics."""
        if not self.metrics:
            return 0.0
        
        total_coverage = sum(metrics.get_overall_coverage() for metrics in self.metrics.values())
        return total_coverage / len(self.metrics)
    
    def export_to_json(self, file_path: Path) -> None:
        """Export coverage report to JSON file."""
        report_data = {
            'timestamp': self.timestamp,
            'build_system': self.build_system,
            'project_name': self.project_name,
            'overall_coverage': self.get_overall_coverage(),
            'metrics': {key: metrics.to_dict() for key, metrics in self.metrics.items()}
        }
        
        with open(file_path, 'w') as f:
            json.dump(report_data, f, indent=2)
    
    def export_to_csv(self, file_path: Path) -> None:
        """Export coverage report to CSV file."""
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Write header
            writer.writerow([
                'Target Name', 'Target Type', 'Instructions Covered', 'Instructions Missed',
                'Instructions Total', 'Instructions Percentage', 'Branches Covered',
                'Branches Missed', 'Branches Total', 'Branches Percentage',
                'Lines Covered', 'Lines Missed', 'Lines Total', 'Lines Percentage',
                'Overall Coverage'
            ])
            
            # Write data
            for metrics in self.metrics.values():
                writer.writerow([
                    metrics.target_name,
                    metrics.target_type,
                    metrics.instructions_covered,
                    metrics.instructions_missed,
                    metrics.total_instructions,
                    f"{metrics.instruction_coverage:.1f}",
                    metrics.branches_covered,
                    metrics.branches_missed,
                    metrics.total_branches,
                    f"{metrics.branch_coverage:.1f}",
                    metrics.lines_covered,
                    metrics.lines_missed,
                    metrics.total_lines,
                    f"{metrics.line_coverage:.1f}",
                    f"{metrics.get_overall_coverage():.1f}"
                ])


def format_coverage_display(metrics: CoverageMetrics, indent: str = "   ") -> str:
    """Format coverage metrics for console display."""
    lines = []
    lines.append(f"{indent}{Colors.CYAN}[INFO]{Colors.RESET} {metrics.target_name} ({metrics.target_type}):")
    
    if metrics.total_instructions > 0:
        lines.append(f"{indent}   → Instructions: {metrics.instructions_covered} / {metrics.total_instructions} ({metrics.instruction_coverage:.1f}%)")
    
    if metrics.total_branches > 0:
        lines.append(f"{indent}   → Branches: {metrics.branches_covered} / {metrics.total_branches} ({metrics.branch_coverage:.1f}%)")
    
    if metrics.total_lines > 0:
        lines.append(f"{indent}   → Lines: {metrics.lines_covered} / {metrics.total_lines} ({metrics.line_coverage:.1f}%)")
    
    return "\n".join(lines)


def format_coverage_summary(metrics: CoverageMetrics) -> str:
    """Format a concise coverage summary."""
    overall = metrics.get_overall_coverage()
    return f"{metrics.target_name}: {overall:.1f}% overall coverage"


def calculate_coverage_trend(current: CoverageMetrics, previous: CoverageMetrics) -> Dict[str, float]:
    """Calculate coverage trend between two measurements."""
    return {
        'instructions': current.instruction_coverage - previous.instruction_coverage,
        'branches': current.branch_coverage - previous.branch_coverage,
        'lines': current.line_coverage - previous.line_coverage,
        'overall': current.get_overall_coverage() - previous.get_overall_coverage()
    } 