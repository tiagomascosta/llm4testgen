import logging
from datetime import datetime
from pathlib import Path

def setup_logging(log_dir: Path) -> logging.Logger:
    """Set up logging to file with detailed information.
    
    Args:
        log_dir: Directory to store log files
        
    Returns:
        Logger instance configured for file logging
    """
    # Create log directory if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create log file with current date
    log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),  # File handler for all INFO and above
            logging.StreamHandler()  # Console handler for INFO and above
        ]
    )
    
    # Set console handler to INFO level
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(logging.INFO)
    
    # Set specific loggers to WARNING to reduce noise
    logging.getLogger('git').setLevel(logging.WARNING)
    logging.getLogger('git.cmd').setLevel(logging.WARNING)
    logging.getLogger('git.repo.base').setLevel(logging.WARNING)
    logging.getLogger('final_implementation.source_analysis.source_resolver').setLevel(logging.WARNING)
    logging.getLogger('source_analysis.method_slicer').setLevel(logging.WARNING)
    logging.getLogger('source_analysis.dependency_method_extractor').setLevel(logging.WARNING)
    
    return logging.getLogger() 