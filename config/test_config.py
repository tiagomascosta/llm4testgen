"""
Test configuration module for managing test-related settings.
"""

class TestConfig:
    """Configuration class for test settings."""
    
    def __init__(self):
        self.java_version = None
        self.java_path = None
        self.junit_version = None
        self.test_framework = None
        self.test_file_path = None
    
    def set_java_version(self, version: str):
        """Set the Java version for testing."""
        self.java_version = version
    
    def get_java_version(self) -> str:
        """Get the current Java version."""
        return self.java_version
    
    def set_java_path(self, path: str):
        """Set the Java installation path."""
        self.java_path = path
    
    def get_java_path(self) -> str:
        """Get the current Java installation path."""
        return self.java_path
    
    def set_junit_version(self, version: str):
        """Set the JUnit version for testing."""
        self.junit_version = version
    
    def get_junit_version(self) -> str:
        """Get the current JUnit version."""
        return self.junit_version
    
    def set_test_framework(self, framework: str):
        """Set the test framework to use."""
        self.test_framework = framework
    
    def get_test_framework(self) -> str:
        """Get the current test framework."""
        return self.test_framework
    
    def set_test_file_path(self, path: str):
        """Set the path to the test file."""
        self.test_file_path = path
    
    def get_test_file_path(self) -> str:
        """Get the current test file path."""
        return self.test_file_path

# Create a singleton instance
_config = TestConfig()

# Export all methods and attributes from the singleton instance
set_java_version = _config.set_java_version
get_java_version = _config.get_java_version
set_java_path = _config.set_java_path
get_java_path = _config.get_java_path
set_junit_version = _config.set_junit_version
get_junit_version = _config.get_junit_version
set_test_framework = _config.set_test_framework
get_test_framework = _config.get_test_framework
set_test_file_path = _config.set_test_file_path
get_test_file_path = _config.get_test_file_path 