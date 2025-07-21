"""
Coverage configuration module for managing coverage-specific settings.
"""

from typing import List, Optional
from dataclasses import dataclass


@dataclass
class CoverageConfig:
    """Configuration class for coverage analysis settings."""
    
    # Basic settings
    enabled: bool = True
    threshold: float = 80.0  # Minimum coverage percentage
    
    # Report serving settings
    serve_html: bool = True
    report_port: int = 8000
    
    # Export settings
    export_formats: List[str] = None
    
    # Coverage types to include
    include_branch_coverage: bool = True
    include_line_coverage: bool = True
    include_instruction_coverage: bool = True
    
    # Build system specific settings
    gradle_jacoco_version: str = "0.8.11"
    maven_jacoco_version: str = "0.8.11"
    
    def __post_init__(self):
        """Initialize default values for mutable fields."""
        if self.export_formats is None:
            self.export_formats = ['json']
    
    def validate(self) -> List[str]:
        """Validate configuration settings and return list of errors."""
        errors = []
        
        if self.threshold < 0 or self.threshold > 100:
            errors.append("Coverage threshold must be between 0 and 100")
        
        if self.report_port < 1024 or self.report_port > 65535:
            errors.append("Report port must be between 1024 and 65535")
        
        if not self.include_branch_coverage and not self.include_line_coverage and not self.include_instruction_coverage:
            errors.append("At least one coverage type must be enabled")
        
        return errors
    
    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return len(self.validate()) == 0


# Global coverage configuration instance
_coverage_config = CoverageConfig()


def get_coverage_config() -> CoverageConfig:
    """Get the global coverage configuration instance."""
    return _coverage_config


def set_coverage_config(config: CoverageConfig) -> None:
    """Set the global coverage configuration instance."""
    global _coverage_config
    _coverage_config = config


def update_coverage_config(**kwargs) -> None:
    """Update specific coverage configuration settings."""
    global _coverage_config
    for key, value in kwargs.items():
        if hasattr(_coverage_config, key):
            setattr(_coverage_config, key, value)
        else:
            raise ValueError(f"Unknown coverage config setting: {key}")


# Convenience functions for common settings
def enable_coverage() -> None:
    """Enable coverage analysis."""
    update_coverage_config(enabled=True)


def disable_coverage() -> None:
    """Disable coverage analysis."""
    update_coverage_config(enabled=False)


def set_coverage_threshold(threshold: float) -> None:
    """Set the coverage threshold percentage."""
    update_coverage_config(threshold=threshold)


def set_report_port(port: int) -> None:
    """Set the port for serving HTML reports."""
    update_coverage_config(report_port=port)


def enable_html_reports() -> None:
    """Enable HTML report serving."""
    update_coverage_config(serve_html=True)


def disable_html_reports() -> None:
    """Disable HTML report serving."""
    update_coverage_config(serve_html=False) 