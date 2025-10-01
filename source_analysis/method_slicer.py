"""
Method slicer module for extracting Java methods from source files.
"""

import re
import logging
import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any, Set
import javalang
from .slice_extractor import SliceExtractor
from .source_resolver import resolve_source_file
from utils.colors import Colors

logger = logging.getLogger(__name__)

# Initialize the working slicer
slicer = SliceExtractor()

def load_source(path: str) -> Dict[str, Any]:
    """Load source file and extract package and imports."""
    src = open(path).read()
    pkg_m = re.search(r'^\s*package\s+([\w\.]+);', src, re.M)
    pkg = pkg_m.group(1) if pkg_m else ''
    # explicit imports
    imap = {cls: mod for mod, cls in re.findall(r'import\s+([\w\.]+)\.(\w+);', src)}
    # wildcard imports
    wildcards = re.findall(r'import\s+([\w\.]+)\.\*\s*;', src)
    return {"source": src, "package": pkg, "imports": imap, "wildcards": wildcards}

def _trim_to_method(snippet: str, method_name: str, arity: Optional[int] = None) -> str:
    """
    Given a raw snippet that may contain extra methods/types,
    find the line with 'public {method_name}(...arity args...)' and
    slice between that line's opening '{' and its matching '}'.
    """
    # escape name for regex
    if arity is not None:
        sig_re = re.compile(
            rf'^[ \t]*(public|protected|private|\s)+\s*{re.escape(method_name)}\s*\('
            rf'(?:[^)]*,\s*){{{arity - 1}}}[^)]*\)\s*\{{',
            re.MULTILINE
        )
    else:
        sig_re = re.compile(
            rf'^[ \t]*(public|protected|private|\s)+\s*{re.escape(method_name)}\s*\([^)]*\)\s*\{{',
            re.MULTILINE
        )
    m = sig_re.search(snippet)
    if not m:
        return snippet    # fallback, no change
    start = m.start()
    # now find the matching brace
    brace = 0
    for idx, ch in enumerate(snippet[start:], start=start):
        if ch == '{':
            brace += 1
        elif ch == '}':
            brace -= 1
            if brace == 0:
                return snippet[start:idx+1]
    return snippet       # fallback

def _slice_by_braces(snippet: str) -> str:
    """
    Given a snippet starting at the method/ctor signature, trim everything
    after its matching closing brace.
    """
    depth = 0
    out = []
    for line in snippet.splitlines():
        out.append(line)
        depth += line.count('{') - line.count('}')
        if depth == 0:
            break
    return "\n".join(out)

def slice_method(
    repo_root: Path,
    method_spec: str,
    arity: Optional[int] = None,
    include_javadoc: bool = True
) -> Optional[str]:
    """
    Extract a method slice from a Java source file.
    This is the original method used for initial method extraction.
    
    Args:
        repo_root: Root directory of the repository
        method_spec: Method specification in format 'package.Class#method'
        arity: Optional number of parameters to match
        include_javadoc: Whether to include Javadoc comments
        
    Returns:
        The method slice as a string, or None if not found
    """
    try:
        # Parse method specification
        if '#' not in method_spec:
            raise ValueError("Method specification must be in format: package.Class#method")
            
        class_part, method_name = method_spec.split('#', 1)
        parts = class_part.split('.')
        package = '.'.join(parts[:-1])
        class_name = parts[-1]
        
        # Use resolve_source_file for consistent path resolution
        file_path = resolve_source_file(str(repo_root), {}, package, class_name)
        if not file_path:
            logger.error(f"Could not find source file for {class_name}")
            return None
            
        # Load source content
        src = open(file_path).read()
        
        # Parse the source to get method arity if not provided
        if arity is None:
            try:
                tree = javalang.parse.parse(src)
                for type_decl in tree.types:
                    if isinstance(type_decl, javalang.tree.ClassDeclaration) and type_decl.name == class_name:
                        # Check methods
                        for method in type_decl.methods:
                            if method.name == method_name:
                                arity = len(method.parameters)
                                break
                        # Check constructors if method_name matches class name
                        if method_name == class_name:
                            for ctor in type_decl.constructors:
                                arity = len(ctor.parameters)
                                break
            except Exception as e:
                logger.error(f"Error parsing source to determine arity: {e}")
                return None
        
        # Use SliceExtractor to get the specific method
        method_impl, found_class = slicer.extract_method(
            file_path=str(file_path),
            method_name=method_name,
            arity=arity,
            include_javadoc=include_javadoc
        )
        
        if method_impl:
            return method_impl
                
        return None
        
    except Exception as e:
        logger.error(f"Error extracting method slice: {e}")
        return None

def extract_dependency_method(
    repo_root: Path,
    method_spec: str,
    arity: Optional[int] = None,
    include_javadoc: bool = True
) -> Optional[str]:
    """
    Extract a method slice from a Java source file.
    This is a more robust version specifically for dependency extraction.
    
    Args:
        repo_root: Root directory of the repository
        method_spec: Method specification in format 'package.Class#method'
        arity: Optional number of parameters to match
        include_javadoc: Whether to include Javadoc comments
        
    Returns:
        The method slice as a string, or None if not found
    """
    try:
        # Parse method specification
        if '#' not in method_spec:
            raise ValueError("Method specification must be in format: package.Class#method")
            
        class_part, method_name = method_spec.split('#', 1)
        parts = class_part.split('.')
        package = '.'.join(parts[:-1])
        class_name = parts[-1]
        
        # Construct file path
        file_path = repo_root / 'src' / 'main' / 'java' / package.replace('.', '/') / f"{class_name}.java"
        if not file_path.exists():
            logger.error(f"Could not find source file for {class_name}")
            return None
            
        # Load source content
        src = file_path.read_text(encoding="utf-8", errors="ignore")
        
        # AST-based search
        try:
            tree = javalang.parse.parse(src)
            for type_decl in tree.types:
                if isinstance(type_decl, javalang.tree.ClassDeclaration) and type_decl.name == class_name:
                    # find matching method node
                    for m in type_decl.methods:
                        if m.name == method_name and (arity is None or len(m.parameters) == arity):
                            # extract all snippets, then filter by signature+arity
                            snippets = slicer.extract_all(str(file_path), include_javadoc=include_javadoc, hops=0)
                            for snippet in snippets:
                                try:
                                    name, ret, types = parse_method_signature(snippet)
                                except ValueError:
                                    continue
                                if name == method_name and (arity is None or len(types) == arity):
                                    # stop on first exact match and trim to just this method
                                    return _trim_to_method(snippet, method_name, arity)
                    # ── try constructors on this class at the right arity ──
                    for ctor in type_decl.constructors:
                        if ctor.name == class_name and (arity is None or len(ctor.parameters) == arity):
                            snippets = slicer.extract_all(str(file_path), include_javadoc=include_javadoc, hops=0)
                            for snippet in snippets:
                                lines = snippet.splitlines()
                                # find the line that _is_ the constructor signature
                                for idx, line in enumerate(lines):
                                    if re.match(
                                        rf"^\s*(public|protected)\s+{class_name}\s*\([^)]*\)\s*\{{",
                                        line
                                    ):
                                        # trim away any annotations or preceding lines
                                        ctor_block = "\n".join(lines[idx:])
                                        return _slice_by_braces(ctor_block)
        except javalang.parser.JavaSyntaxError:
            pass

        # Regex fallback: match signature line with correct comma count
        pattern = re.compile(
            rf'^[ \t]*(?:public|protected|private|static|final|synchronized|\s)+[^{";"}]*\b{re.escape(method_name)}\s*\(([^)]*)\)\s*\{{',
            re.MULTILINE
        )
        for m in pattern.finditer(src):
            params = m.group(1)
            count = 0 if params.strip()=='' else params.count(',')+1
            if arity is None or count == arity:
                start = m.start()
                # find matching closing brace
                brace = 0
                for idx, ch in enumerate(src[start:], start=start):
                    if ch == '{':
                        brace += 1
                    elif ch == '}':
                        brace -= 1
                        if brace == 0:
                            return src[start:idx+1]
                            
        # recurse into superclass
        pkg_info = load_source(str(file_path))
        parent = None
        try:
            tree = javalang.parse.parse(src)
            cls_node = next((t for t in tree.types if isinstance(t, javalang.tree.ClassDeclaration) and t.name == class_name), None)
            if cls_node and cls_node.extends:
                parent = cls_node.extends.name
        except Exception:
            parent = None
        if parent:
            return extract_dependency_method(
                repo_root=repo_root,
                method_spec=f"{package}.{parent}#{method_name}",
                arity=arity,
                include_javadoc=include_javadoc
            )
            
        return None
        
    except Exception as e:
        logger.error(f"Error extracting method slice: {e}")
        return None

def parse_method_signature(impl: str) -> Tuple[str, str, List[str]]:
    """
    Extracts method name, return type, and parameter types from a Java method
    implementation string. Handles generics, varargs, arrays.
    Returns (method_name, return_type, [param_type, ...]).
    """
    # Match signature: modifiers + return + name + (params)
    m = re.search(r"(?:public|protected|private)?\s+([\w<>, ?\[\]]+)\s+(\w+)\s*\(([^)]*)\)", impl)
    if not m:
        raise ValueError(f"Cannot parse method signature from: {impl}")
    ret, name, params = m.group(1).strip(), m.group(2), m.group(3).strip()
    if not params:
        param_types = []
    else:
        param_types = []
        for part in params.split(','):
            part = part.strip()
            # remove parameter name
            t = part.rsplit(' ', 1)[0]
            # normalize varargs to array
            t = t.replace('...', '[]')
            param_types.append(t.strip())
    return name, ret, param_types

def get_method_definition(
    repo_root: str,
    imports: dict,
    src_package: str,
    qualifier: str,
    method_name: str,
    arity: Optional[int] = None,
    include_javadoc: bool = True
) -> Tuple[Optional[str], Optional[str]]:
    """
    Get the definition of a method from a Java source file.
    Returns (method_impl, class_name) tuple.
    """
    try:
        print(f"\n{Colors.CYAN}[INFO]{Colors.RESET} Getting method definition for: {qualifier}.{method_name}({arity})")
        
        # Find the source file
        file_path = resolve_source_file(repo_root, imports, src_package, qualifier)
        if not file_path:
            print(f"  {Colors.BRIGHT_RED}[ERROR]{Colors.RESET} Could not find source file for {qualifier}")
            return None, None
            
        print(f"  → Found source file: {file_path}")
        
        # Extract the method implementation
        slicer = SliceExtractor()
        method_impl, class_name = slicer.extract_method(
            file_path=file_path,
            method_name=method_name,
            arity=arity,
            include_javadoc=include_javadoc,
            repo_root=repo_root,
            imports=imports,
            src_package=src_package
        )
        
        if method_impl:
            print(f"  {Colors.BRIGHT_GREEN}[SUCCESS]{Colors.RESET} Found method implementation")
            return method_impl, class_name
            
        print(f"  {Colors.BRIGHT_RED}[ERROR]{Colors.RESET} Could not find method implementation")
        return None, None
        
    except Exception as e:
        print(f"  {Colors.BRIGHT_RED}[ERROR]{Colors.RESET} Error getting method definition: {str(e)}")
        return None, None

def parse_method_node(src: str, method_name: str) -> Tuple[javalang.tree.ClassDeclaration, javalang.tree.MethodDeclaration]:
    """Parse and return the class and method nodes for a given method name."""
    try:
        # First try parsing the method directly
        try:
            tree = javalang.parse.parse(src)
            for _, node in tree.filter(javalang.tree.ClassDeclaration):
                for member in node.body:
                    if isinstance(member, javalang.tree.MethodDeclaration) and member.name == method_name:
                        return node, member
        except javalang.parser.JavaSyntaxError:
            logger.debug("Direct parsing failed, trying with class wrapper")
            
        # If direct parsing fails, wrap in a class declaration
        wrapped_src = f"public class TempClass {{\n{src}\n}}"
        tree = javalang.parse.parse(wrapped_src)
        for _, node in tree.filter(javalang.tree.ClassDeclaration):
            for member in node.body:
                if isinstance(member, javalang.tree.MethodDeclaration) and member.name == method_name:
                    return node, member
                    
        raise ValueError(f"Method {method_name} not found in source code")
    except Exception as e:
        logger.error(f"Error parsing method node: {str(e)}")
        raise ValueError(f"Failed to parse method {method_name}: {str(e)}")
