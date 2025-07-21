"""
AST analyzer module for complex Java code analysis.
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from tree_sitter import Language, Parser, Node
import tree_sitter_java

logger = logging.getLogger(__name__)

class ASTAnalyzer:
    """Analyzes Java code using tree-sitter for complex AST operations."""
    
    def __init__(self):
        """Initialize the AST analyzer with tree-sitter parser."""
        self.java_lang = Language(tree_sitter_java.language())
        self.parser = Parser(self.java_lang)
        
    def parse_file(self, file_path: Path) -> Optional[Node]:
        """
        Parse a Java file into an AST.
        
        Args:
            file_path: Path to the Java file
            
        Returns:
            Root node of the AST if successful, None otherwise
        """
        try:
            source = file_path.read_text(encoding='utf-8', errors='ignore')
            tree = self.parser.parse(bytes(source, 'utf8'))
            return tree.root_node
        except Exception as e:
            logger.error(f"Error parsing file {file_path}: {str(e)}")
            return None
            
    def find_method_node(self, root: Node, method_name: str) -> Optional[Node]:
        """
        Find a method node in the AST by name.
        
        Args:
            root: Root node of the AST
            method_name: Name of the method to find
            
        Returns:
            Method node if found, None otherwise
        """
        def find_method(node: Node) -> Optional[Node]:
            if node.type == 'method_declaration':
                # Get method name from identifier node
                for child in node.children:
                    if child.type == 'identifier' and child.text.decode('utf8') == method_name:
                        return node
            for child in node.children:
                result = find_method(child)
                if result:
                    return result
            return None
            
        return find_method(root)
        
    def get_method_dependencies(self, method_node: Node) -> Set[str]:
        """
        Get all dependencies (imports, types, etc.) used by a method.
        
        Args:
            method_node: Node representing the method
            
        Returns:
            Set of dependency names
        """
        dependencies = set()
        
        def collect_dependencies(node: Node):
            if node.type == 'identifier':
                dependencies.add(node.text.decode('utf8'))
            for child in node.children:
                collect_dependencies(child)
                
        collect_dependencies(method_node)
        return dependencies
        
    def get_method_complexity(self, method_node: Node) -> int:
        """
        Calculate cyclomatic complexity of a method.
        
        Args:
            method_node: Node representing the method
            
        Returns:
            Cyclomatic complexity score
        """
        complexity = 1  # Base complexity
        
        def count_branches(node: Node):
            nonlocal complexity
            # Count control flow statements
            if node.type in ['if_statement', 'while_statement', 'for_statement', 
                           'do_statement', 'switch_statement', 'catch_clause']:
                complexity += 1
            # Count logical operators
            elif node.type in ['&&', '||']:
                complexity += 1
            for child in node.children:
                count_branches(child)
                
        count_branches(method_node)
        return complexity
        
    def get_method_metrics(self, method_node: Node) -> Dict[str, Any]:
        """
        Calculate various metrics for a method.
        
        Args:
            method_node: Node representing the method
            
        Returns:
            Dictionary containing method metrics
        """
        metrics = {
            'complexity': self.get_method_complexity(method_node),
            'dependencies': self.get_method_dependencies(method_node),
            'lines': method_node.end_point[0] - method_node.start_point[0] + 1
        }
        return metrics
