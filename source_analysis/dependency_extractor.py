from typing import Dict, Set, Any, Tuple, List, Optional
import javalang
import re
import os
import logging
from pathlib import Path
from .source_resolver import resolve_source_file, normalize_qualifier
from .slice_extractor import SliceExtractor
from .method_parser import parse_method_node
from .method_slicer import (
    slice_method,
    parse_method_signature
)
from .qualifier_builder import build_qualifier_map

# Configure logging to only show critical errors
logger = logging.getLogger(__name__)
logger.setLevel(logging.CRITICAL)

# Add at the top of the file, after imports
JAVA_CORE = set()  # Will be populated dynamically based on imports

# Known java.lang classes that don't need explicit imports
JAVA_LANG_CLASSES = {
    "String", "Integer", "Short", "Long", "Boolean", "Double", "Float", "Character",
    "System", "Math", "List", "Map", "Set", "Optional", "Object", "StringBuilder",
    "StringBuffer", "Number", "Byte", "Void", "Thread", "Runnable", "Exception",
    "RuntimeException", "Error", "Throwable", "Class", "Package", "ClassLoader",
    "Process", "Runtime", "SecurityManager", "StrictMath", "StringIndexOutOfBoundsException",
    "ArrayIndexOutOfBoundsException", "IllegalArgumentException", "NullPointerException",
    "IllegalStateException", "IndexOutOfBoundsException", "UnsupportedOperationException",
    "CloneNotSupportedException", "InterruptedException", "NoSuchMethodException",
    "NoSuchFieldException", "InstantiationException", "IllegalAccessException",
    "ClassNotFoundException", "NoClassDefFoundError", "LinkageError", "VerifyError",
    "IncompatibleClassChangeError", "AbstractMethodError", "IllegalAccessError",
    "InstantiationError", "NoSuchFieldError", "NoSuchMethodError", "OutOfMemoryError",
    "StackOverflowError", "UnknownError", "UnsatisfiedLinkError", "ClassCircularityError",
    "ClassFormatError", "ExceptionInInitializerError", "IllegalThreadStateException",
    "NumberFormatException", "SecurityException", "StringIndexOutOfBoundsException",
    "TypeNotPresentException", "UnsupportedClassVersionError", "VerifyError"
}

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

def load_source(path_or_content: str) -> Dict[str, Any]:
    """
    Load source file and extract package and imports.
    Returns dict with source, package, imports map, and wildcard imports.
    """
    if os.path.isfile(path_or_content):
        src = open(path_or_content).read()
    else:
        src = path_or_content
        
    # Extract package
    pkg_m = re.search(r'^\s*package\s+([\w\.]+);', src, re.M)
    pkg = pkg_m.group(1) if pkg_m else ''
    
    # Extract explicit imports
    imap = {cls: mod for mod, cls in re.findall(r'import\s+([\w\.]+)\.(\w+);', src)}
    
    # Extract wildcard imports
    wildcards = re.findall(r'import\s+([\w\.]+)\.\*\s*;', src)
    
    # Parse the source into an AST
    try:
        tree = javalang.parse.parse(src)
    except Exception as e:
        logger.error(f"Error parsing source: {e}")
        tree = None
    
    return {
        "source": src,
        "package": pkg,
        "imports": imap,
        "wildcards": wildcards,
        "tree": tree
    }

def find_source_file(repo_root: str, class_name: str, imports: dict, src_package: str) -> str:
    """
    Find a source file by searching in imports, current package, and repository.
    Returns the path if found, empty string if not found.
    """
    return resolve_source_file(repo_root, imports, src_package, class_name)

def extract_method_slice(
    repo_root: str,
    imports: dict,
    src_package: str,
    qualifier: str,
    method_name: str,
    arity: Optional[int] = None,
    include_javadoc: bool = True
) -> Tuple[str, str]:
    """
    Grab the exact method slice for qualifier.method_name with the given arity.
    Uses SliceExtractor for robust method extraction.
    Returns (method_impl, class_name) tuple.
    """
    try:
        # Initialize SliceExtractor
        slicer = SliceExtractor()
        
        # Ensure we have a valid class name
        if not qualifier:
            logger.error("No class name provided")
            return "", ""
            
        # Check if this is a Java core class
        if qualifier in JAVA_LANG_CLASSES:
            return "// Java core class, no source available", qualifier

        # Initialize class_name - will be used for both constructors and regular methods
        class_name = qualifier

        # For constructors, we need to find the actual class file
        if method_name.startswith("new "):  # This is a constructor
            # Extract the class name from the method name (e.g. "new Network" -> "Network")
            class_name = method_name.split(" ")[1]
            
            # Try to find the class in imports
            if class_name in imports:
                pkg = imports[class_name]
                path = os.path.join(repo_root, *pkg.split('.'), f'{class_name}.java')
                if not os.path.isfile(path):
                    path = ""
            else:
                # Try source file resolution
                path = resolve_source_file(repo_root, imports, src_package, class_name)
        else:
            # For regular methods, use source file resolution
            # First check if the class is in imports
            if qualifier in imports:
                pkg = imports[qualifier]
                path = os.path.join(repo_root, *pkg.split('.'), f'{qualifier}.java')
                if not os.path.isfile(path):
                    path = ""
            else:
                # Try source file resolution
                path = resolve_source_file(repo_root, imports, src_package, qualifier)
        
        # If not found in standard locations, try to find in the entire repository
        if not path:
            # Try to find the file in the entire repository
            for root, _, files in os.walk(repo_root):
                for file in files:
                    if file == f"{class_name}.java":
                        path = os.path.join(root, file)
                        break
                if path:
                    break
        
        if not path:
            return f"// Could not find source file for {class_name}", class_name
            
        if not os.path.isfile(path):
            return f"// Source file does not exist: {path}", class_name

        # Use SliceExtractor to get the specific method
        method_impl = slicer.extract_method(
            file_path=path,
            method_name=method_name,
            arity=arity,
            include_javadoc=include_javadoc,
            repo_root=repo_root,
            imports=imports,
            src_package=src_package
        )
        
        if method_impl:
            return method_impl, class_name
                
        return f"// Could not find implementation for {class_name}.{method_name}", class_name
        
    except Exception as e:
        logger.error(f"Error extracting method slice: {str(e)}")
        return f"// Error extracting method slice: {str(e)}", class_name

def find_flow_control_deps(method_node) -> Set[str]:
    """
    Find dependencies that are only used in flow control statements.
    These should be excluded from the final dependency set.
    """
    flow_control = set()

    def collect(expr):
        # Fix: Node.filter() requires a pattern argument
        for _, node in expr.filter(javalang.tree.Node):
            node_type = type(node).__name__
            
            if isinstance(node, javalang.tree.MethodInvocation):
                if node.qualifier:
                    sig = f"{node.qualifier}.{node.member}({len(node.arguments)})"
                    flow_control.add(sig)
                else:
                    sig = f"{node.member}({len(node.arguments)})"
                    flow_control.add(sig)
            elif isinstance(node, javalang.tree.MemberReference):
                if node.qualifier:
                    sig = f"{node.qualifier}.{node.member}"
                    flow_control.add(sig)
                else:
                    sig = node.member
                    flow_control.add(sig)
    
    # Check if/else conditions
    for _, node in method_node.filter(javalang.tree.IfStatement):
        collect(node.condition)
        
    # Check while conditions
    for _, node in method_node.filter(javalang.tree.WhileStatement):
        collect(node.condition)
        
    # Check for conditions
    for _, node in method_node.filter(javalang.tree.ForStatement):
        # Handle traditional for loop
        if hasattr(node, 'condition') and node.condition:
            collect(node.condition)
        # Handle enhanced for loop
        elif hasattr(node, 'iterable'):
            collect(node.iterable)
            
    # Check switch expressions
    for _, node in method_node.filter(javalang.tree.SwitchStatement):
        collect(node.expression)
        
    return flow_control

def find_enum_definition(
    enum_name: str,
    repo_root: str,
    imports: dict,
    src_package: str,
    constant_name: str = None
) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """
    Find the definition of an enum constant.
    Returns (enum_class, arity, constant_value) if found.
    """
    try:
        # Try to find the enum class file
        enum_file = resolve_source_file(repo_root, imports, src_package, enum_name)
        if not enum_file:
            return None, None, None
            
        # Load and parse the enum file
        src = open(enum_file).read()
        tree = javalang.parse.parse(src)
        
        # Find the enum declaration
        for _, node in tree.filter(javalang.tree.EnumDeclaration):
            if node.name == enum_name:
                # If looking for a specific constant
                if constant_name:
                    for const in node.body.constants:
                        if const.name == constant_name:
                            # Get the constant's value if it has one
                            value = None
                            if const.arguments:
                                value = const.arguments[0].value
                            return enum_name, len(const.arguments) if const.arguments else 0, value
                    return None, None, None
                # Otherwise return the first constant's info
                if node.body.constants:
                    const = node.body.constants[0]
                    value = None
                    if const.arguments:
                        value = const.arguments[0].value
                    return enum_name, len(const.arguments) if const.arguments else 0, value
                    
        return None, None, None
        
    except Exception as e:
        logger.error(f"Error finding enum definition: {str(e)}")
        return None, None, None

def extract_dependencies(src: str, method_name: str) -> Dict[str, Set[str]]:
    """
    Extract dependencies from a Java method.
    Returns a dictionary mapping dependency categories to sets of signatures.
    Categories:
    - external_instances: Method calls on parameters/local variables and constructor calls
    - static_methods: Calls on uppercase qualifiers (static methods)
    - static_constants: References to ALL-CAPS fields
    - superclass_methods: Unqualified method calls not in own class
    - self_helpers: Unqualified method calls in own class (excluding recursive calls)
    """
    try:
        # Parse the method node
        class_node, method_node = parse_method_node(src, method_name)
        
        # 1) what "this.<foo>" methods live in the class?
        own_methods = {m.name for m in class_node.methods}
        
        # 2) parameters are injected collaborators
        param_names = {p.name for p in method_node.parameters}
        
        # 3) collect _all_ locals in this method body
        local_vars = set()
        for _, decl in method_node.filter(javalang.tree.LocalVariableDeclaration):
            for var in decl.declarators:
                local_vars.add(var.name)
        
        # 4) collect all class fields
        class_fields = set()
        for _, field in class_node.filter(javalang.tree.FieldDeclaration):
            for var in field.declarators:
                class_fields.add(var.name)
        
        # everything that isn't a primitive or local param is "external"
        collaborator_locals = param_names | local_vars
        
        # Initialize dependency categories
        deps = {
            "external_instances": set(),
            "static_methods": set(),
            "static_constants": set(),
            "superclass_methods": set(),
            "self_helpers": set()
        }
        
        # Find flow control dependencies to merge
        flow_control = find_flow_control_deps(method_node)
        
        # Filter and categorize flow control dependencies
        for dep in sorted(flow_control):
            # Skip nonsensical dependencies
            if dep in ['tag', 'r'] or len(dep) <= 1:
                continue
                
            # Try to parse the dependency
            if '.' in dep:
                # Qualified dependency (e.g. "container.blackPlayer" or "container.event.getRound(0)")
                parts = dep.split('.')
                if len(parts) == 2:
                    qual, name = parts
                    if '(' in name:
                        # Method call with arity
                        method_name = name.split('(')[0]
                        arity = name.split('(')[1].split(')')[0]
                        if qual[0].isupper():
                            # Static method call
                            deps["static_methods"].add(f"{qual}.{method_name}({arity})")
                        else:
                            # Instance method call
                            deps["external_instances"].add(f"{qual}.{method_name}({arity})")
                    else:
                        # Field access or constant
                        if qual[0].isupper() and name.isupper():
                            # Static constant
                            deps["static_constants"].add(f"{qual}.{name}")
                        else:
                            # Field access
                            deps["external_instances"].add(f"{qual}.{name}")
            else:
                # Unqualified dependency
                if '(' in dep:
                    # Method call with arity
                    name = dep.split('(')[0]
                    arity = dep.split('(')[1].split(')')[0]
                    if name in own_methods:
                        deps["self_helpers"].add(f"{name}({arity})")
                    else:
                        deps["superclass_methods"].add(f"{name}({arity})")
                else:
                    # Skip unqualified field access as it's ambiguous
                    pass
        
        # --- 1) method calls (including on locals) ---
        for _, inv in method_node.filter(javalang.tree.MethodInvocation):
            qual = inv.qualifier      # e.g. "parser", "BitUtil" or None
            name = inv.member         # e.g. "nextInt", "setSignalStrength"
            arity = len(inv.arguments)
            sig = f"{name}({arity})"
            full = f"{qual}.{sig}" if qual else sig
            
            # Skip if this is a flow control dependency
            if full in flow_control or sig in flow_control:
                continue
                
            # a) calls on params, locals, or class fields → external collaborator
            if qual in collaborator_locals or qual in class_fields:
                deps["external_instances"].add(full)
                continue
                
            # b) calls on uppercase qualifier → static-method helper
            if qual and qual[0].isupper():
                deps["static_methods"].add(full)
                continue
                
            # c) unqualified → self vs inherited
            if not qual:
                if name in own_methods:
                    deps["self_helpers"].add(sig)
                else:
                    deps["superclass_methods"].add(sig)
        
        # Then, check for method calls in return statements
        for _, ret in method_node.filter(javalang.tree.ReturnStatement):
            # Handle method calls in returns
            if isinstance(ret.expression, javalang.tree.MethodInvocation):
                inv = ret.expression
                qual = inv.qualifier
                name = inv.member
                arity = len(inv.arguments)
                sig = f"{name}({arity})"
                full = f"{qual}.{sig}" if qual else sig
                
                if name == method_name:
                    continue
                    
                if qual in collaborator_locals or qual in class_fields:
                    deps["external_instances"].add(full)
                elif qual and qual[0].isupper():
                    deps["static_methods"].add(full)
                elif not qual:
                    if name in own_methods:
                        deps["self_helpers"].add(sig)
                    else:
                        deps["superclass_methods"].add(sig)
            
            # Handle static constants in returns
            elif isinstance(ret.expression, javalang.tree.MemberReference):
                name = ret.expression.member
                qual = ret.expression.qualifier
                if name.replace('_', '').isupper():
                    full = f"{qual}.{name}" if qual else name
                    deps["static_constants"].add(full)
            
            # Handle constructor calls in returns
            elif isinstance(ret.expression, javalang.tree.ClassCreator):
                name = ret.expression.type.name
                param_types = []
                for arg in ret.expression.arguments:
                    if isinstance(arg, javalang.tree.BinaryOperation):
                        param_types.append("int")  # For operations like initialByte & 31
                    elif isinstance(arg, javalang.tree.MethodInvocation):
                        param_types.append(arg.member)  # For method calls like nextSymbol()
                    else:
                        param_types.append(type(arg).__name__)
                sig = f"new {name}({','.join(param_types)})"
                deps["external_instances"].add(sig)
            
            else:
                pass
        
        # --- 2) constructor calls → external instance creations ---
        for _, ctor in method_node.filter(javalang.tree.ClassCreator):
            name = ctor.type.name         # e.g. "Parser", "Position"
            
            # Get parameter types from arguments
            param_types = []
            for arg in ctor.arguments:
                if isinstance(arg, javalang.tree.MethodInvocation):
                    # For method calls, use the return type of the method
                    # For toString(), we know it returns String
                    if arg.member == "toString":
                        param_types.append("String")
                    else:
                        # For other methods, try to find their return type
                        for _, method in class_node.filter(javalang.tree.MethodDeclaration):
                            if method.name == arg.member:
                                param_types.append(method.return_type.name)
                                break
                        else:
                            # If we can't find the return type, use the method name
                            param_types.append(arg.member)
                elif isinstance(arg, javalang.tree.ClassCreator):
                    # For class creators, use the actual type
                    param_types.append(arg.type.name)
                elif isinstance(arg, javalang.tree.Literal):
                    # For literals, use the Java type
                    if isinstance(arg.value, str):
                        param_types.append("String")
                    elif isinstance(arg.value, bool):
                        param_types.append("boolean")
                    elif isinstance(arg.value, int):
                        param_types.append("int")
                    elif isinstance(arg.value, float):
                        param_types.append("double")
                    else:
                        param_types.append("Object")
                elif isinstance(arg, javalang.tree.MemberReference):
                    # For member references, try to resolve the type
                    found_type = None
                    # First, check if it's a local variable
                    for _, decl in method_node.filter(javalang.tree.LocalVariableDeclaration):
                        for var in decl.declarators:
                            if var.name == arg.member:
                                found_type = decl.type.name
                                break
                        if found_type:
                            break
                    # Next, check if it's a class field
                    if not found_type:
                        for _, decl in class_node.filter(javalang.tree.FieldDeclaration):
                            for var in decl.declarators:
                                if var.name == arg.member:
                                    found_type = decl.type.name
                                    break
                            if found_type:
                                break
                    # If still not found, use the member name as a fallback
                    if found_type:
                        param_types.append(found_type)
                    else:
                        param_types.append(arg.member)
                elif isinstance(arg, javalang.tree.BinaryOperation):
                    # For binary operations, determine the result type
                    if arg.operator == '&':
                        param_types.append("int")
                    elif arg.operator in ['+', '-', '*', '/']:
                        param_types.append("int")
                    else:
                        param_types.append("Object")
                else:
                    # For unknown types, use a simplified string representation
                    param_types.append(type(arg).__name__)
            
            # Create signature with parameter types
            sig = f"new {name}({','.join(param_types)})"
            deps["external_instances"].add(sig)
            
        # --- 3) static field refs → constants only if ALL-CAPS name ---
        for _, ref in method_node.filter(javalang.tree.MemberReference):
            name = ref.member             # e.g. "PATTERN4", "KEY_HDOP"
            full = f"{ref.qualifier}.{name}" if ref.qualifier else name
            
            # Check if this is a constant (ALL_CAPS with possible underscores)
            if name.replace('_', '').isupper():
                deps["static_constants"].add(full)
        
        return deps
        
    except Exception as e:
        logger.error(f"Error extracting dependencies: {str(e)}")
        return {
            "external_instances": set(),
            "static_methods": set(),
            "static_constants": set(),
            "superclass_methods": set(),
            "self_helpers": set()
        }

def find_static_constant(
    file_path: str,
    class_name: str,
    constant_name: str
) -> Optional[str]:
    """Find the definition of a static constant or enum constant in a Java source file."""
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        text = data.decode('utf-8', errors='ignore')
        
        try:
            tree = javalang.parse.parse(text)
        except Exception as e:
            logger.error(f"Error parsing source file: {e}")
            return None
        
        # First check for enum constants
        for type_decl in tree.types:
            if isinstance(type_decl, javalang.tree.EnumDeclaration):
                if type_decl.name == class_name:          
               
                    for i, const in enumerate(type_decl.body.constants):
                        if const.name == constant_name:
                            # For enum constants, return their position/value
                            if const.arguments:
                                # If the enum constant has arguments, return them
                                args = [arg.value for arg in const.arguments]
                                return f"{constant_name} = {', '.join(str(arg) for arg in args)}"
                            else:
                                # Otherwise return the position in the enum
                                return f"{constant_name} = {i}"
                    return None
        
        # Then check for static constants in fields
        for type_decl in tree.types:
            if isinstance(type_decl, javalang.tree.ClassDeclaration) and type_decl.name == class_name:
                # Look for the constant in fields
                for field in type_decl.fields:
                    if field.modifiers & {'public', 'static', 'final'} == {'public', 'static', 'final'} or \
                       field.modifiers & {'private', 'static', 'final'} == {'private', 'static', 'final'}:
                        for declarator in field.declarators:
                            if declarator.name == constant_name:
                                # Get the constant's value
                                value = None
                                if declarator.initializer:
                                    if isinstance(declarator.initializer, javalang.tree.Literal):
                                        value = declarator.initializer.value
                                    elif isinstance(declarator.initializer, javalang.tree.MemberReference):
                                        value = f"{declarator.initializer.qualifier}.{declarator.initializer.member}"
                                    elif isinstance(declarator.initializer, javalang.tree.ClassCreator):
                                        # For PatternBuilder, extract the full implementation
                                        if "Pattern" in str(field.type):
                                            # Find the field declaration in the source text
                                            field_start = text.find(field.type.name + " " + constant_name)
                                            if field_start != -1:
                                                # Look for the last semicolon in the pattern builder chain
                                                lines = text[field_start:].split('\n')
                                                pattern_lines = []
                                                for line in lines:
                                                    pattern_lines.append(line)
                                                    if line.strip().endswith(';'):
                                                        break
                                                value = '\n'.join(pattern_lines).strip()
                                            else:
                                                logger.error("Could not find field declaration in source text")
                                    else:
                                        value = str(declarator.initializer)
                                
                                # Get the field's type
                                field_type = field.type.name
                                if field.type.arguments:
                                    field_type += '<' + ', '.join(arg.type.name for arg in field.type.arguments) + '>'
                                
                                # Format the definition
                                modifiers = ' '.join(field.modifiers)
                                if value and "Pattern" in field_type:
                                    # For patterns, return the full implementation
                                    return value
                                else:
                                    definition = f"{modifiers} {field_type} {constant_name}"
                                    if value is not None:
                                        definition += f" = {value}"
                                    definition += ";"
                                    return definition
        
        return None
    except Exception as e:
        logger.error(f"Error finding static constant: {str(e)}")
        return None

def extract_impl(
    category: str,
    sig: str,
    class_name: str,
    repo_root: str,
    src_package: str,
    imports: dict,
    include_javadoc: bool = True,
    qualifier_map: dict = None,
    deps: dict = None
) -> Tuple[Optional[str], Optional[str]]:
    try:
        # Parse method/constructor signature
        if category == 'external_instances' and sig.startswith('new '):
            # For constructors, the signature is now "new ClassName(Type1,Type2,...)"
            match = re.match(r"new\s+(\w+)\(([^)]+)\)", sig)
            if not match:
                logger.error(f"Invalid constructor signature: {sig}")
                return None, None
                
            target_class = match.group(1)  # For constructors, the class is the method name without "new "
            # Split by comma but not within parentheses
            param_types = []
            current = ""
            paren_count = 0
            for char in match.group(2):
                if char == '(':
                    paren_count += 1
                    current += char
                elif char == ')':
                    paren_count -= 1
                    current += char
                elif char == ',' and paren_count == 0:
                    param_types.append(current.strip())
                    current = ""
                else:
                    current += char
            if current:
                param_types.append(current.strip())
                
            method_name = target_class
            arity = len(param_types)
            
            if qualifier_map and target_class in qualifier_map:
                target_class = qualifier_map[target_class]
            
            target_class = normalize_qualifier(target_class)
            
        elif category == 'static_constants':
            parts = sig.split('.')
            if len(parts) == 2:
                if len(parts) == 3:
                    outer_class = parts[0]
                    enum_name = parts[1]
                    constant_name = parts[2]
                    target_class = outer_class
                else:
                    if parts[0].endswith('Type'):
                        possible_outer = parts[0][:-4]
                        if possible_outer in imports:
                            target_class = possible_outer
                            constant_name = parts[1]
                        else:
                            target_class = parts[0]
                            constant_name = parts[1]
                    else:
                        target_class = parts[0]
                        constant_name = parts[1]
            else:
                target_class = class_name
                constant_name = sig
                
            if qualifier_map and target_class in qualifier_map:
                target_class = qualifier_map[target_class]
            
            target_class = normalize_qualifier(target_class)
            
            file_path = resolve_source_file(repo_root, imports, src_package, target_class)
            if not file_path:
                logger.error(f"No source file found for {target_class}")
                return None, None
                
            definition = find_static_constant(file_path, target_class, constant_name)
            if definition:
                return definition, os.path.basename(file_path).replace('.java', '')
            else:
                if len(parts) == 2:
                    original_class = parts[0]
                    file_path = resolve_source_file(repo_root, imports, src_package, original_class)
                    if file_path:
                        definition = find_static_constant(file_path, original_class, constant_name)
                        if definition:
                            return definition, os.path.basename(file_path).replace('.java', '')
                logger.error(f"No constant definition found")
                return None, None
        else:
            if category == 'superclass_methods':
                match = re.match(r"(\w+)\((\d+)\)", sig)
                if not match:
                    return None, None
                method_name = match.group(1)
                arity = int(match.group(2))
                target_class = class_name
            elif category == 'self_helpers':
                match = re.match(r"(\w+)\((\d+)\)", sig)
                if not match:
                    return None, None
                method_name = match.group(1)
                arity = int(match.group(2))
                target_class = class_name
            else:
                match = re.match(r"(\w+)\.(\w+)\((\d+)\)", sig)
                if not match:
                    return None, None
                qualifier = match.group(1)
                method_name = match.group(2)
                arity = int(match.group(3))
                
                if qualifier and qualifier[0].isupper():
                    target_class = qualifier
                else:
                    if qualifier_map and qualifier in qualifier_map:
                        target_class = qualifier_map[qualifier]
                    else:
                        target_class = class_name
        
        # Find source file for the target class
        if target_class in imports:
            pkg = imports[target_class]
            file_path = os.path.join(repo_root, *pkg.split('.'), f'{target_class}.java')
            if not os.path.isfile(file_path):
                file_path = ""
        else:
            # Try source file resolution
            file_path = resolve_source_file(repo_root, imports, src_package, target_class)
        
        if not file_path:
            if category == 'external_instances' and sig.startswith('new '):
                logger.error(f"No source file found for {target_class}")
            return None, None
        
        # Extract method implementation
        slicer = SliceExtractor()
        
        if category == 'static_methods':
            impl = slicer.extract_method(
                file_path=file_path,
                method_name=method_name,
                arity=arity,
                include_javadoc=include_javadoc,
                repo_root=None,
                imports=None,
                src_package=None
            )
            if impl:
                return impl, os.path.basename(file_path).replace('.java', '')
        elif category == 'superclass_methods':
            impl, found_class = slicer.find_method_in_inheritance_chain(
                file_path=file_path,
                method_name=method_name,
                arity=arity,
                include_javadoc=include_javadoc,
                repo_root=repo_root,
                imports=imports,
                src_package=src_package
            )
            if impl:
                return impl, found_class
        else:
            # For external instances and self helpers, first try direct extraction
            impl, found_class = slicer.extract_method(
                file_path=file_path,
                method_name=method_name,
                arity=arity,
                include_javadoc=include_javadoc,
                repo_root=repo_root,
                imports=imports,
                src_package=src_package,
                param_types=param_types if category == 'external_instances' and sig.startswith('new ') else None
            )
            
            if impl:
                return impl, found_class
            elif category == 'external_instances':
                # If not found in initial class, try inheritance chain for external instances
                impl, found_class = slicer.find_method_in_inheritance_chain(
                    file_path=file_path,
                    method_name=method_name,
                    arity=arity,
                    include_javadoc=include_javadoc,
                    repo_root=repo_root,
                    imports=imports,
                    src_package=src_package,
                    param_types=param_types if sig.startswith('new ') else None
                )
                if impl:
                    return impl, found_class
            
        return None, None
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return None, None

def format_ast_node(node):
    """Format an AST node for debugging."""
    if isinstance(node, javalang.tree.MethodInvocation):
        return f"MethodInvocation({node.member})"
    elif isinstance(node, javalang.tree.ClassCreator):
        return f"ClassCreator({node.type.name})"
    elif isinstance(node, javalang.tree.MemberReference):
        return f"MemberReference({node.member})"
    elif isinstance(node, javalang.tree.EnumConstant):
        return f"EnumConstant({node.name})"
    else:
        return str(node)