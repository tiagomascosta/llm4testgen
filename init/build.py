import subprocess
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def _ensure_sdkman_installed() -> bool:
    """
    Ensure SDKMAN is installed on the system.
    
    Returns:
        bool: True if SDKMAN is installed or was successfully installed, False otherwise
    """
    # Check if SDKMAN is already installed
    sdkman_dir = Path.home() / '.sdkman'
    if sdkman_dir.exists():
        return True
        
    try:
        print("   → Installing SDKMAN...")
        # Install SDKMAN
        install_cmd = 'curl -s "https://get.sdkman.io" | bash'
        result = subprocess.run(
            install_cmd,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        print("   → SDKMAN installation command output:", result.stdout)
        
        # Source SDKMAN
        print("   → Sourcing SDKMAN...")
        source_cmd = 'source "$HOME/.sdkman/bin/sdkman-init.sh"'
        subprocess.run(
            source_cmd,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        
        print("   → SDKMAN installation completed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"   ❌ SDKMAN installation failed with error: {str(e)}")
        print(f"   ❌ Command output: {e.output}")
        return False
    except Exception as e:
        print(f"   ❌ SDKMAN installation failed with unexpected error: {str(e)}")
        return False

def _install_jdk_with_sdkman(version: str) -> Optional[str]:
    """
    Install a specific JDK version using SDKMAN.
    
    Args:
        version: The JDK version to install (e.g., '11.0.12-open')
        
    Returns:
        Optional[str]: Path to the installed JDK if successful, None otherwise
    """
    # Direct mapping of Java versions to SDKMAN identifiers
    VERSION_TO_IDENTIFIER = {
        '6': '6.0.119-zulu',      # Zulu is the only vendor with Java 6
        '7': '7.0.352-zulu',      # Zulu is the only vendor with Java 7
        '8': '8.0.452-tem',       # Temurin (formerly AdoptOpenJDK) is well-maintained
        '11': '11.0.27-tem',      # Temurin is stable for LTS versions
        '17': '17.0.15-tem',      # Temurin is stable for LTS versions
        '21': '21.0.7-tem',       # Temurin is stable for LTS versions
        '24': '24.0.1-tem',       # Temurin is stable for latest versions
    }
    
    try:
        # Get the major version number
        version_num = version.split('.')[-1]  # Get last part of version (e.g., "7" from "1.7")
        
        # Get the SDKMAN identifier for this version
        identifier = VERSION_TO_IDENTIFIER.get(version_num)
        if not identifier:
            print(f"   ❌ No SDKMAN identifier found for Java version {version_num}")
            print("   Available versions:")
            print("   - Java 6: 6.0.119-zulu")
            print("   - Java 7: 7.0.352-zulu")
            print("   - Java 8: 8.0.452-tem")
            print("   - Java 11: 11.0.27-tem")
            print("   - Java 17: 17.0.15-tem")
            print("   - Java 21: 21.0.7-tem")
            print("   - Java 24: 24.0.1-tem")
            return None
            
        # Install the selected version
        install_cmd = f'bash -c ". $HOME/.sdkman/bin/sdkman-init.sh && sdk install java {identifier} -y"'
        try:
            result = subprocess.run(
                install_cmd,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
        except subprocess.TimeoutExpired:
            print("   ❌ Installation timed out after 5 minutes")
            return None
            
        # Get the installation path
        path_cmd = f'bash -c ". $HOME/.sdkman/bin/sdkman-init.sh && sdk home java {identifier}"'
        try:
            result = subprocess.run(
                path_cmd,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout for path check
            )
        except subprocess.TimeoutExpired:
            print("   ❌ Path check timed out")
            return None
            
        jdk_path = result.stdout.strip()
        
        if jdk_path and Path(jdk_path).exists():
            return jdk_path
            
        print(f"   ❌ Java installation path {jdk_path} does not exist")
        return None
        
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Java installation failed with error: {str(e)}")
        print(f"   ❌ Command output: {e.output}")
        return None
    except Exception as e:
        print(f"   ❌ Java installation failed with unexpected error: {str(e)}")
        return None 