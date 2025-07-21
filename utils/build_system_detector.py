from pathlib import Path
from typing import Literal

BuildSystem = Literal["gradle", "maven"]

def detect_build_system(repo_path: Path) -> BuildSystem:
    """
    Detect the build system used by the repository.
    
    Args:
        repo_path: Path to the repository root
        
    Returns:
        "gradle" if build.gradle exists, "maven" if pom.xml exists
        
    Raises:
        ValueError: If neither build system is detected
    """
    gradle_file = repo_path / "build.gradle"
    maven_file = repo_path / "pom.xml"
    
    if gradle_file.exists():
        return "gradle"
    elif maven_file.exists():
        return "maven"
    else:
        raise ValueError(f"No build system detected in {repo_path}. Expected build.gradle or pom.xml") 