"""
Color utilities for professional terminal output.
"""

class Colors:
    """ANSI color codes for terminal output."""
    
    # Basic colors
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    
    # Bright colors
    BRIGHT_RED = '\033[1;91m'
    BRIGHT_GREEN = '\033[1;92m'
    BRIGHT_YELLOW = '\033[1;93m'
    BRIGHT_BLUE = '\033[1;94m'
    BRIGHT_MAGENTA = '\033[1;95m'
    BRIGHT_CYAN = '\033[1;96m'
    
    # Styles
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'
    
    # Reset
    RESET = '\033[0m'

def colorize(text: str, color: str) -> str:
    """Apply color to text."""
    return f"{color}{text}{Colors.RESET}"

def step(text: str) -> str:
    """Format step text."""
    return colorize(f"[STEP] {text}", Colors.BRIGHT_BLUE)

def success(text: str) -> str:
    """Format success text."""
    return colorize(f"[SUCCESS] {text}", Colors.BRIGHT_GREEN)

def error(text: str) -> str:
    """Format error text."""
    return colorize(f"[ERROR] {text}", Colors.BRIGHT_RED)

def warning(text: str) -> str:
    """Format warning text."""
    return colorize(f"[WARNING] {text}", Colors.BRIGHT_YELLOW)

def info(text: str) -> str:
    """Format info text."""
    return colorize(f"[INFO] {text}", Colors.CYAN)

def summary(text: str) -> str:
    """Format summary text."""
    return colorize(f"[SUMMARY] {text}", Colors.BRIGHT_MAGENTA)
