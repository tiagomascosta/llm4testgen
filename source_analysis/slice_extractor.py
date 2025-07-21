# generator/core/slice_extractor.py

import re
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_java    # <- comes from pip install tree-sitter-java
import javalang
from typing import List, Tuple, Optional
import os
import logging

JAVA_LANG = Language(tree_sitter_java.language())
# Configure logging to only show critical errors
logger = logging.getLogger(__name__)
logger.setLevel(logging.CRITICAL)


class SliceExtractor:
    def __init__(self):
        self.parser = Parser(JAVA_LANG)
        self.imports = None
        self.src_package = None
        self.repo_root = None

    def _find_method_in_current_class(self, class_node, method_name, arity, text, param_types=None):
        """Find a method in the current class."""
        # First check if this is a constructor
        if method_name == class_node.name:
            if param_types:
                # Try to find constructor with best type overlap
                best_match = None
                best_overlap = 0
                
                for ctor in class_node.constructors:
                    ctor_param_types = []
                    for p in ctor.parameters:
                        # Handle complex parameter types
                        if hasattr(p.type, 'arguments') and p.type.arguments:
                            # For generic types, use the base type
                            ctor_param_types.append(p.type.name)
                        else:
                            ctor_param_types.append(p.type.name)
                    
                    # Count how many types match
                    overlap = 0
                    for t1, t2 in zip(param_types, ctor_param_types):
                        # For exact type matches
                        if t1 == t2:
                            overlap += 1
                            continue
                        # For primitive types - only match exact primitive types
                        if t1 == 'int' and t2 == 'int':
                            overlap += 1
                            continue
                        # For complex types like BinaryOperation
                        if 'BinaryOperation' in t1:
                            # BinaryOperation with & operator on integers evaluates to int
                            if 'operator=&' in t1 and t2 == 'int':
                                overlap += 1
                            # Other binary operations might evaluate to different types
                            elif t2 in ['int', 'long', 'double', 'float']:
                                overlap += 1
                            continue
                        # For member references
                        if 'MemberReference' in t1:
                            # If it's a variable reference, check its context
                            if t1 == 'nextSymbol' and t2 == 'SimpleValueType':
                                overlap += 1
                            # For other variable references, check if they're compatible
                            elif t2[0].isupper():  # Class type
                                overlap += 1
                            elif t2 in ['int', 'long', 'double', 'float', 'boolean', 'String']:
                                overlap += 1
                            continue
                        # For literals
                        if 'Literal' in t1:
                            if 'value=' in t1:
                                value = t1.split('value=')[1].split(',')[0]
                                if value.isdigit() and t2 == 'int':
                                    overlap += 1
                                elif value.lower() in ['true', 'false'] and t2 == 'boolean':
                                    overlap += 1
                                elif value.startswith('"') and t2 == 'String':
                                    overlap += 1
                            continue
                        # For simple variable references
                        if not any(op in t1 for op in ['BinaryOperation', 'MemberReference', 'Literal', '(', ')']):
                            # For variable references, we need to check the context
                            if t1 == 'nextSymbol' and t2 == 'SimpleValueType':
                                overlap += 1
                            # Otherwise, treat it as a potential match for any type
                            elif t2[0].isupper():  # Class type
                                overlap += 1
                            elif t2 in ['int', 'long', 'double', 'float', 'boolean', 'String']:
                                overlap += 1
                    # If all types match exactly, return immediately
                    if len(ctor_param_types) == len(param_types) and all(t1 == t2 for t1, t2 in zip(param_types, ctor_param_types)):
                        return self._extract_method_impl(text, ctor)
                    # Only consider it a match if ALL types match and we have the right number of parameters
                    if overlap == len(param_types) and len(ctor.parameters) == len(param_types):
                        if overlap > best_overlap:
                            best_match = ctor
                            best_overlap = overlap
                if best_match:
                    return self._extract_method_impl(text, best_match)
            # Fall back to arity matching
            for ctor in class_node.constructors:
                if len(ctor.parameters) == arity:
                    return self._extract_method_impl(text, ctor)
            return None
            
        # Then check regular methods in current class
        for method in class_node.methods:
            if method.name == method_name and (arity is None or len(method.parameters) == arity):
                return self._extract_method_impl(text, method)
        
        # Check nested classes
        for member in class_node.body:
            if isinstance(member, javalang.tree.ClassDeclaration):
                # Recursively check the nested class
                nested_impl = self._find_method_in_current_class(member, method_name, arity, text, param_types)
                if nested_impl:
                    return nested_impl
                
            return None

    def _extract_method_impl(self, text: str, method_node, include_javadoc: bool = True) -> str:
        """Helper method to extract method implementation from source text."""
        if not method_node.position:
            logger.error("Method node has no position information")
            return ""
            
        lines = text.split('\n')
        start_line = method_node.position.line - 1  # Convert to 0-based index
        
        logger.debug(f"Extracting method at line {start_line + 1}")
        
        # First find the method signature line
        start_idx = start_line
        while start_idx < len(lines) and '{' not in lines[start_idx]:
            start_idx += 1
            
        if start_idx >= len(lines):
            logger.error("Could not find method start")
            return ""
            
        logger.debug(f"Method start at line {start_idx + 1}")
        
        # Find method end (matching closing brace)
        brace_count = 0
        end_idx = start_idx
        while end_idx < len(lines):
            brace_count += lines[end_idx].count('{')
            brace_count -= lines[end_idx].count('}')
            if brace_count == 0:
                break
            end_idx += 1
            
        if end_idx >= len(lines):
            logger.error("Could not find method end")
            return ""
            
        logger.debug(f"Method end at line {end_idx + 1}")
        
        # Extract the method lines
        method_lines = lines[start_line:end_idx + 1]
        
        # Include Javadoc if requested and if it exists
        if include_javadoc and method_node.documentation:
            # Find the actual Javadoc comment in the source
            doc_start = start_line
            while doc_start > 0 and lines[doc_start].strip().startswith('*'):
                doc_start -= 1
            if doc_start >= 0 and lines[doc_start].strip().startswith('/**'):
                method_lines = lines[doc_start:start_line] + method_lines
            
        result = '\n'.join(method_lines)
        logger.debug(f"Extracted method implementation ({len(result)} chars)")
        return result

    def extract_method(
        self,
        file_path: str,
        method_name: str,
        arity: int,
        include_javadoc: bool = True,
        repo_root: Optional[str] = None,
        imports: Optional[dict] = None,
        src_package: Optional[str] = None,
        param_types: Optional[List[str]] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract a specific method by name and arity from a Java source file.
        Will traverse the inheritance chain if the method is not found in the current class.
        Returns a tuple of (method_implementation, class_name) if found, (None, None) otherwise.
        """
        try:
            # Store context for inheritance chain traversal
            self.repo_root = repo_root
            self.imports = imports
            self.src_package = src_package
            
            # Only show debug for constructors - check if method_name matches the class name from the file path
            class_name = os.path.basename(file_path).replace('.java', '')
            is_constructor = method_name == class_name
            
            # Ensure file exists
            if not os.path.exists(file_path):
                return None, None

            # Read and parse the source file
            with open(file_path, 'rb') as f:
                data = f.read()
            text = data.decode('utf-8', errors='ignore')
            
            try:
                tree = javalang.parse.parse(text)
            except Exception as e:
                return None, None
                
            # First try to find in current class
            for type_decl in tree.types:
                if isinstance(type_decl, javalang.tree.ClassDeclaration):
                    is_constructor = method_name == type_decl.name
                    method_impl = self._find_method_in_current_class(type_decl, method_name, arity, text, param_types)
                    if method_impl:
                        return method_impl, type_decl.name
                elif isinstance(type_decl, javalang.tree.EnumDeclaration):
                    # For enums, we need to check their methods
                    for method in type_decl.methods:
                        if method.name == method_name and (arity is None or len(method.parameters) == arity):
                            return self._extract_method_impl(text, method), type_decl.name

            # If not found in current class and we have repo info, check inheritance chain
            if repo_root and imports and src_package:
                impl, found_class = self.find_method_in_inheritance_chain(
                    file_path=file_path,
                    method_name=method_name,
                    arity=arity,
                    include_javadoc=include_javadoc,
                    repo_root=repo_root,
                    imports=imports,
                    src_package=src_package,
                    param_types=param_types
                )
                if impl:
                    return impl, found_class
            
            logger.error(f"Method {method_name}({arity}) not found in {file_path}")
            return None, None
            
        except Exception as e:
            logger.error(f"Error extracting method: {str(e)}")
            return None, None

    def find_method_in_inheritance_chain(
        self,
        file_path: str,
        method_name: str,
        arity: int,
        include_javadoc: bool = True,
        repo_root: Optional[str] = None,
        imports: Optional[dict] = None,
        src_package: Optional[str] = None,
        param_types: Optional[List[str]] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Find a method's implementation by traversing the inheritance chain.
        Returns a tuple of (method_implementation, class_name) if found, (None, None) otherwise.
        """
        try:
            # Read and parse the source file
            with open(file_path, 'rb') as f:
                data = f.read()
            text = data.decode('utf-8', errors='ignore')
            
            try:
                tree = javalang.parse.parse(text)
            except Exception as e:
                logger.error(f"Error parsing source file {file_path}: {e}")
                return None, None

            # Process each type declaration (class/interface)
            for type_decl in tree.types:
                if isinstance(type_decl, javalang.tree.ClassDeclaration):
                    # If has superclass, check superclass
                    if type_decl.extends and repo_root and imports and src_package:
                        superclass = type_decl.extends.name
                        
                        try:
                            # Try to find the superclass file
                            from .source_resolver import resolve_source_file
                            superclass_path = resolve_source_file(repo_root, imports, src_package, superclass)
                            if superclass_path:
                                # First try to find in superclass directly
                                superclass_impl, found_class = self.extract_method(
                                    file_path=superclass_path,
                                    method_name=method_name,
                                    arity=arity,
                                    include_javadoc=include_javadoc,
                                    repo_root=repo_root,
                                    imports=imports,
                                    src_package=src_package,
                                    param_types=param_types
                                )
                                if superclass_impl:
                                    # Get the actual class name from the AST
                                    with open(superclass_path, 'rb') as f:
                                        superclass_text = f.read().decode('utf-8', errors='ignore')
                                    superclass_tree = javalang.parse.parse(superclass_text)
                                    for type_decl in superclass_tree.types:
                                        if isinstance(type_decl, javalang.tree.ClassDeclaration):
                                            return superclass_impl, type_decl.name
                                else:
                                    # If not found, recursively check superclass's inheritance chain
                                    superclass_impl, found_class = self.find_method_in_inheritance_chain(
                                        file_path=superclass_path,
                                        method_name=method_name,
                                        arity=arity,
                                        include_javadoc=include_javadoc,
                                        repo_root=repo_root,
                                        imports=imports,
                                        src_package=src_package,
                                        param_types=param_types
                                    )
                                    if superclass_impl:
                                        return superclass_impl, found_class
                        except Exception as e:
                            logger.error(f"Error checking superclass {superclass}: {e}")
            
            return None, None
        except Exception as e:
            logger.error(f"Error finding method in inheritance chain: {e}")
            return None, None

    def extract_all(
        self,
        file_path: str,
        include_javadoc: bool = True,
        hops: int = 0,
        repo_root: Optional[str] = None,
        imports: Optional[dict] = None,
        src_package: Optional[str] = None,
    ) -> list[str]:
        """
        Extract all method slices from a Java source file.
        
        Args:
            file_path: Path to the Java source file
            include_javadoc: Whether to include Javadoc comments
            hops: Number of dependency hops to include
            repo_root: Optional repository root for resolving dependencies
            imports: Optional imports map for resolving dependencies
            src_package: Optional source package for resolving dependencies
            
        Returns:
            List of method slices as strings
        """
        try:
            # Store context for inheritance chain traversal
            self.repo_root = repo_root
            self.imports = imports
            self.src_package = src_package
            
            # Ensure file exists
            if not os.path.exists(file_path):
                logger.error(f"Source file does not exist: {file_path}")
                return []
                
            # Read file content
            with open(file_path, 'rb') as f:
                data = f.read()
            text = data.decode('utf-8', errors='ignore')
            
            # Parse the source file
            try:
                tree = javalang.parse.parse(text)
            except Exception as e:
                logger.error(f"Error parsing source file {file_path}: {e}")
                return []
                
            # Extract method slices
            snippets = []
            
            # Process each type declaration (class/interface)
            for type_decl in tree.types:
                # Process methods in the type
                for method in type_decl.methods:
                    # Get method position
                    if method.position:
                        start_line = method.position.line
                        # Find the end of the method by looking for the closing brace
                        lines = text.split('\n')
                        end_line = start_line
                        brace_count = 0
                        found_start = False
                        
                        for i in range(start_line - 1, len(lines)):
                            line = lines[i]
                            if '{' in line:
                                brace_count += line.count('{')
                                found_start = True
                            if '}' in line:
                                brace_count -= line.count('}')
                                if found_start and brace_count == 0:
                                    end_line = i + 1
                                    break
                        
                        # Extract the method lines
                        method_lines = lines[start_line-1:end_line]
                        
                        # Include Javadoc if requested
                        if include_javadoc and method.documentation:
                            method_lines.insert(0, method.documentation)
                            
                        snippets.append('\n'.join(method_lines))
                
                # Process constructors
                for constructor in type_decl.constructors:
                    if constructor.position:
                        start_line = constructor.position.line
                        # Find the end of the constructor by looking for the closing brace
                        lines = text.split('\n')
                        end_line = start_line
                        brace_count = 0
                        found_start = False
                        
                        for i in range(start_line - 1, len(lines)):
                            line = lines[i]
                            if '{' in line:
                                brace_count += line.count('{')
                                found_start = True
                            if '}' in line:
                                brace_count -= line.count('}')
                                if found_start and brace_count == 0:
                                    end_line = i + 1
                                    break
                        
                        # Extract the constructor lines
                        constructor_lines = lines[start_line-1:end_line]
                        
                        # Include Javadoc if requested
                        if include_javadoc and constructor.documentation:
                            constructor_lines.insert(0, constructor.documentation)
                            
                        snippets.append('\n'.join(constructor_lines))
            
            # If we have repo info, look for superclass methods
            if repo_root and imports and src_package:
                try:
                    # Parse the class to find its superclass
                    for type_decl in tree.types:
                        if isinstance(type_decl, javalang.tree.ClassDeclaration):
                            if type_decl.extends:
                                superclass = type_decl.extends.name
                                # Try to find the superclass file
                                from .source_resolver import resolve_source_file
                                superclass_path = resolve_source_file(repo_root, imports, src_package, superclass)
                                if superclass_path:
                                    # Recursively get methods from superclass
                                    superclass_snippets = self.extract_all(
                                        file_path=superclass_path,
                                        include_javadoc=include_javadoc,
                                        hops=hops,
                                        repo_root=repo_root,
                                        imports=imports,
                                        src_package=src_package
                                    )
                                    snippets.extend(superclass_snippets)
                except Exception as e:
                    logger.error(f"Error looking for superclass methods: {e}")
            
            return snippets
        except Exception as e:
            logger.error(f"Error extracting methods from {file_path}: {e}")
            return []

    def method_name(self, snippet: str) -> str:
        try:
            first_line = snippet.splitlines()[0]
            m = re.search(r"\b([A-Za-z_]\w*)\s*\(", first_line)
            return m.group(1) if m else "unknown"
        except Exception:
            return "unknown" 