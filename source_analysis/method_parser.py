from typing import Tuple
import javalang
import logging

logger = logging.getLogger(__name__)

def parse_method_node(src: str, method_name: str) -> Tuple[javalang.tree.ClassDeclaration, javalang.tree.MethodDeclaration]:
    """Parse and return the class and method nodes for a given method name."""
    try:
        # First try parsing the method directly
        try:
            tree = javalang.parse.parse(src)
            for _, node in tree.filter(javalang.tree.ClassDeclaration):
                # First check methods in the current class
                for method in node.methods:
                    if method.name == method_name:
                        return node, method
                        
                # Then check nested classes
                for member in node.body:
                    if isinstance(member, javalang.tree.ClassDeclaration):
                        # Check if this is a nested class
                        for nested_method in member.methods:
                            if nested_method.name == method_name:
                                return member, nested_method
                                
        except javalang.parser.JavaSyntaxError:
            logger.debug("Direct parsing failed, trying with class wrapper")
            
        # If direct parsing fails, wrap in a class declaration
        wrapped_src = f"public class TempClass {{\n{src}\n}}"
        tree = javalang.parse.parse(wrapped_src)
        for _, node in tree.filter(javalang.tree.ClassDeclaration):
            # First check methods in the current class
            for method in node.methods:
                if method.name == method_name:
                    return node, method
                    
            # Then check nested classes
            for member in node.body:
                if isinstance(member, javalang.tree.ClassDeclaration):
                    for nested_method in member.methods:
                        if nested_method.name == method_name:
                            return member, nested_method
                    
        raise ValueError(f"Method {method_name} not found in source code")
    except Exception as e:
        logger.error(f"Error parsing method node: {str(e)}")
        raise ValueError(f"Failed to parse method {method_name}: {str(e)}") 