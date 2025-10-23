import os
import shutil
import logging
from pathlib import Path
from git import Repo

# Configure logging to only show errors
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

class RepositoryManager:
    """Manages repository operations."""
    
    def __init__(self, output_dir: Path, input_dir: Path = None):
        """Initialize repository manager.
        
        Args:
            output_dir: Directory to store repositories
            input_dir: Directory to store cloned repositories (default: implementation/input)
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up input directory
        if input_dir is not None:
            self.input_dir = Path(input_dir)
        else:
            # Default input directory inside implementation
            self.input_dir = Path(__file__).parent.parent / 'input'
        self.input_dir.mkdir(parents=True, exist_ok=True)
    
    def clone_repository(self, repo_url: str, commit_hash: str = None) -> Path:
        """Clone a repository and checkout a specific commit.
        
        Args:
            repo_url: URL of the repository to clone
            commit_hash: Optional commit hash to checkout
            
        Returns:
            Path to the cloned repository
        """
        # Extract repository name from URL
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        repo_path = self.input_dir / repo_name
        
        # Remove existing directory if it exists
        if repo_path.exists():
            shutil.rmtree(repo_path)
        
        # Clone repository
        repo = Repo.clone_from(repo_url, repo_path)
        
        # Checkout specific commit if provided
        if commit_hash:
            repo.git.checkout(commit_hash)
        
        return repo_path
    
    def use_local_repository(self, local_path: str) -> Path:
        """Use a local repository.
        
        Args:
            local_path: Path to the local repository
            
        Returns:
            Path to the repository
        """
        repo_path = Path(local_path)
        if not repo_path.exists():
            raise ValueError(f"Local repository not found: {local_path}")
        
        return repo_path 