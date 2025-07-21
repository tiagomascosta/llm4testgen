"""
Report server module for serving JaCoCo HTML coverage reports.
"""

import subprocess
import socket
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Tuple
import webbrowser
import os
import signal
import psutil
import shutil


class ReportServer:
    """Manages HTTP server for serving JaCoCo HTML reports."""
    
    def __init__(self, html_root: Path, port: int = 8000):
        self.html_root = html_root
        self.port = port
        self.server_process: Optional[subprocess.Popen] = None
        self.server_thread: Optional[threading.Thread] = None
        self.is_running = False
    
    def start(self) -> bool:
        """Start the HTTP server."""
        if self.is_running:
            return True
        
        if not self.html_root.exists():
            raise FileNotFoundError(f"HTML report directory not found: {self.html_root}")
        
        if not self.html_root.is_dir():
            raise NotADirectoryError(f"HTML report path is not a directory: {self.html_root}")
        
        # Check if port is available
        if not self._is_port_available(self.port):
            raise RuntimeError(f"Port {self.port} is already in use")
        
        try:
            # Start Python HTTP server
            self.server_process = subprocess.Popen(
                ["python3", "-m", "http.server", str(self.port)],
                cwd=self.html_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Wait a moment for server to start
            time.sleep(1)
            
            # Check if server is actually running
            if self.server_process.poll() is None:
                self.is_running = True
                return True
            else:
                return False
                
        except Exception as e:
            raise RuntimeError(f"Failed to start report server: {e}")
    
    def stop(self) -> None:
        """Stop the HTTP server."""
        if self.server_process and self.is_running:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            finally:
                self.is_running = False
                self.server_process = None
    
    def _is_port_available(self, port: int) -> bool:
        """Check if a port is available."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return True
        except OSError:
            return False
    
    def get_base_url(self) -> str:
        """Get the base URL for the report server."""
        return f"http://localhost:{self.port}"
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


def start_report_server(html_root: Path, port: int = 8000) -> Optional[ReportServer]:
    """
    Start HTTP server to serve JaCoCo HTML reports.
    
    Args:
        html_root: Path to the HTML report directory
        port: Port to serve reports on
        
    Returns:
        ReportServer instance if started successfully, None otherwise
    """
    try:
        # First, try to kill any existing process on the port
        if not kill_process_on_port(port):
            # If no process was killed, check if port is still in use
            if not ReportServer(html_root, port)._is_port_available(port):
                print(f"Warning: Port {port} is still in use after cleanup attempt")
                return None
        
        # Wait a moment for the port to be freed
        time.sleep(1)
        
        server = ReportServer(html_root, port)
        if server.start():
            return server
        else:
            return None
    except Exception as e:
        print(f"Warning: Failed to start report server: {e}")
        return None


def stop_report_server(server: Optional[ReportServer]) -> None:
    """
    Stop the report server if running.
    
    Args:
        server: ReportServer instance to stop
    """
    if server:
        server.stop()


def generate_report_urls(
    repo_path: Path,
    package: str,
    class_name: str,
    port: int = 8000,
    inner_class: Optional[str] = None
) -> Dict[str, str]:
    """
    Generate URLs for accessing coverage reports.
    
    Args:
        repo_path: Path to the repository root
        package: Java package name
        class_name: Java class name
        port: Port number for the report server
        inner_class: Optional inner class name
        
    Returns:
        Dictionary with report URLs
    """
    base_url = f"http://localhost:{port}"
    
    # First, try to find the specific class HTML file
    class_html_file = find_class_html_file(repo_path, class_name, inner_class)
    
    if class_html_file:
        # Found the specific class file, generate URL relative to the HTML root
        html_root = find_html_report_directory(repo_path)
        if html_root:
            # Calculate relative path from HTML root to the class file
            try:
                relative_path = class_html_file.relative_to(html_root)
                class_url = f"{base_url}/{relative_path.as_posix()}"
            except ValueError:
                # If we can't calculate relative path, use the fallback approach
                class_url = f"{base_url}/{class_name}.html"
        else:
            class_url = f"{base_url}/{class_name}.html"
    else:
        # Fallback: build the class identifier for JaCoCo
        if inner_class:
            class_identifier = f"{package.replace('.', '/')}/{class_name}${inner_class}"
        else:
            class_identifier = f"{package.replace('.', '/')}/{class_name}"
        class_url = f"{base_url}/{class_identifier}.html"
    
    urls = {
        'main_report': f"{base_url}/index.html",
        'target_class': class_url
    }
    
    return urls


def find_class_html_file(repo_path: Path, class_name: str, inner_class: Optional[str] = None) -> Optional[Path]:
    """
    Find the specific class HTML file by searching from the repo root.
    
    Args:
        repo_path: Path to the repository root
        class_name: Java class name (e.g., "Tokenizer")
        inner_class: Optional inner class name
        
    Returns:
        Path to the class HTML file if found, None otherwise
    """
    # Search for the class HTML file in common JaCoCo report locations
    if inner_class:
        # For inner classes, search for the specific inner class file
        search_patterns = [
            f"**/{class_name}${inner_class}.html",
            f"**/*{class_name}${inner_class}*.html"
        ]
    else:
        # For regular classes, search for the class file
        search_patterns = [
            f"**/{class_name}.html",
            f"**/*{class_name}*.html"
        ]
    
    for pattern in search_patterns:
        for html_file in repo_path.glob(pattern):
            if html_file.is_file():
                return html_file
    
    return None


def find_html_report_directory(repo_path: Path) -> Optional[Path]:
    """
    Find the JaCoCo HTML report directory.
    
    Args:
        repo_path: Path to the repository root
        
    Returns:
        Path to HTML report directory if found, None otherwise
    """
    # Common JaCoCo HTML report locations
    possible_paths = [
        repo_path / "build" / "reports" / "jacoco" / "test" / "html",
        repo_path / "target" / "site" / "jacoco",
        repo_path / "target" / "jacoco" / "html",
        repo_path / "build" / "jacoco" / "html"
    ]
    
    for path in possible_paths:
        if path.exists() and path.is_dir():
            return path
    
    # If no standard location found, search for any HTML report directory
    for html_dir in repo_path.rglob("**/html"):
        if html_dir.is_dir() and any(html_dir.glob("*.html")):
            return html_dir
    
    return None


def copy_html_reports_to_output(html_root: Path, output_dir: Path) -> Optional[Path]:
    """
    Copy JaCoCo HTML reports from repository to output directory.
    
    Args:
        html_root: Path to the HTML report directory in repository
        output_dir: Path to the output directory (should be the repo root)
        
    Returns:
        Path to the copied HTML directory if successful, None otherwise
    """
    if not html_root.exists() or not html_root.is_dir():
        return None
    
    # Create reports/coverage directory in output
    reports_dir = output_dir / "reports"
    coverage_reports_dir = reports_dir / "coverage"
    coverage_reports_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Remove existing content to avoid conflicts
        if coverage_reports_dir.exists():
            shutil.rmtree(coverage_reports_dir)
        # Copy the entire HTML directory
        shutil.copytree(html_root, coverage_reports_dir)
        return coverage_reports_dir
    except Exception as e:
        print(f"Warning: Failed to copy HTML reports: {e}")
        return None


def open_report_in_browser(url: str) -> bool:
    """
    Open a coverage report URL in the default browser.
    
    Args:
        url: URL to open
        
    Returns:
        True if browser was opened successfully, False otherwise
    """
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False


def display_report_urls(urls: Dict[str, str]) -> None:
    """
    Display HTML report access URLs.
    
    Args:
        urls: Dictionary of report URLs
    """
    print("\n🌐 Coverage Reports Available:")
    print("─" * 50)
    for report_type, url in urls.items():
        print(f"   → {report_type.replace('_', ' ').title()}: {url}")


def check_report_server_status(port: int = 8000) -> bool:
    """
    Check if a report server is running on the specified port.
    
    Args:
        port: Port to check
        
    Returns:
        True if server is running, False otherwise
    """
    try:
        import requests
        response = requests.get(f"http://localhost:{port}", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def find_available_port(start_port: int = 8000, max_attempts: int = 10) -> Optional[int]:
    """
    Find an available port starting from start_port.
    
    Args:
        start_port: Starting port number
        max_attempts: Maximum number of ports to try
        
    Returns:
        Available port number if found, None otherwise
    """
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return port
        except OSError:
            continue
    
    return None


def create_report_server_with_fallback(
    html_root: Path,
    preferred_port: int = 8000
) -> Tuple[Optional[ReportServer], int]:
    """
    Create a report server with automatic port fallback.
    
    Args:
        html_root: Path to HTML report directory
        preferred_port: Preferred port number
        
    Returns:
        Tuple of (ReportServer instance, actual port used)
    """
    # Try preferred port first
    if find_available_port(preferred_port, 1):
        server = start_report_server(html_root, preferred_port)
        if server:
            return server, preferred_port
    
    # Find an available port
    available_port = find_available_port(preferred_port + 1, 10)
    if available_port:
        server = start_report_server(html_root, available_port)
        if server:
            return server, available_port
    
    return None, -1


def kill_process_on_port(port: int) -> bool:
    """
    Kill any process using the specified port.
    
    Args:
        port: Port number to check
        
    Returns:
        True if a process was killed, False otherwise
    """
    try:
        # Try using psutil first (more reliable)
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # Get connections separately to avoid attribute issues
                connections = proc.connections()
                if connections:
                    for conn in connections:
                        if hasattr(conn, 'laddr') and conn.laddr.port == port:
                            proc.terminate()
                            proc.wait(timeout=3)
                            return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, psutil.Error):
                continue
        return False
    except ImportError:
        # Fallback: use lsof and kill commands (Linux/macOS)
        try:
            result = subprocess.run(['lsof', '-ti', f':{port}'], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid.strip():
                        subprocess.run(['kill', '-9', pid.strip()], capture_output=True)
                return True
            return False
        except (subprocess.SubprocessError, FileNotFoundError):
            # If lsof is not available, just return False
            return False
    except Exception as e:
        print(f"Warning: Could not kill process on port {port}: {e}")
        return False 