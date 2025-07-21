from typing import Dict, List, Set, Tuple
from pydantic import BaseModel, Field
import json
from source_analysis.dependency_extractor import extract_impl
from prompting.clustering_prompt import Scenario

class TestMethodOnly(BaseModel):
    """Model for a single test method response."""
    testMethod: str = Field(
        ..., 
        description="The full JUnit test method code, including annotation and assertions"
    )

def build_test_case_prompt(
    mut_sig: str,
    mut_body: str,
    scaffold: str,
    scenario: Scenario,
    helpers: List[str],
    junit_version: int,
    deps: Dict[str, Set[str]],
    qualifier_map: Dict[str, str],
    flow_control: Set[str],
    example_tests: List[str] = None,
    class_code: str = None,
    repo_root: str = None,
    imports: Dict[str, str] = None,
    src_package: str = None,
    class_name: str = None
) -> Tuple[str, str]:
    """
    Build the prompt for generating a test case.
    
    Args:
        mut_sig: Method Under Test signature
        mut_body: Method Under Test body
        scaffold: Test class scaffold
        scenario: Test scenario to generate
        helpers: List of helper method signatures
        junit_version: JUnit version (4 or 5)
        deps: Dictionary of dependencies by category
        qualifier_map: Map of qualifiers to their definitions
        flow_control: Set of flow control related dependencies to exclude
        example_tests: Optional list of example test methods
        class_code: Full class code containing the MUT
        repo_root: Root directory of the repository
        imports: Dictionary mapping class names to their package paths
        src_package: Source package of the class under test
        class_name: Name of the class under test
        
    Returns:
        Tuple[str, str]: A tuple containing (system_message, prompt)
    """
    # Get the schema and pretty print it
    schema = TestMethodOnly.model_json_schema()
    pretty_schema = json.dumps(schema, indent=2)

    # Build examples block if provided
    examples_block = ""
    if example_tests:
        examples_block = "\n// === EXAMPLE TEST METHODS ===\n"
        for idx, method_body in enumerate(example_tests[-5:], start=1):
            examples_block += f"// Example {idx}:\n{method_body}\n\n"
    
    example_note = ""
    if examples_block:
        # Indent each line of examples_block by 4 spaces
        indented_examples = "\n".join("    " + line for line in examples_block.splitlines())
        example_note = "\nNote: The scaffold above already has some fully‐compilable example test methods (marked with '// Example N') that exercise other scenarios.\n"

    # Build dependencies section
    deps_section = "2. Dependencies\n"
    
    # Map category names to their display names
    category_names = {
        'external_instances': 'External Instance Methods',
        'static_methods': 'Static Methods',
        'static_constants': 'Static Constants',
        'superclass_methods': 'Superclass Methods',
        'self_helpers': 'Self Helpers'
    }
    
    # Add dependencies by category
    section_num = 1
    for category, display_name in category_names.items():
        if category in deps:
            deps_list = deps[category]  # No more filtering of flow control
            if deps_list:  # Only show non-empty categories
                deps_section += f"\n2.{section_num} {display_name}\n"
                section_num += 1
                for sig in sorted(deps_list):
                    impl, found_class = extract_impl(
                        category=category,
                        sig=sig,
                        class_name=class_name,
                        repo_root=repo_root,
                        imports=imports,
                        src_package=src_package,
                        qualifier_map=qualifier_map,
                        deps=deps
                    )
                    
                    # Format the dependency info
                    if category == "external_instances":
                        if sig.startswith("new "):
                            cls_name = sig.split()[1].split('(')[0]
                            deps_section += f"- name: {sig}\n"
                            deps_section += f"  class: {cls_name}\n"
                        else:
                            var, rest = sig.split('.', 1)
                            cls_name = qualifier_map.get(var, var[0].upper() + var[1:])
                            deps_section += f"- name: {sig}\n"
                            deps_section += f"  class: {cls_name}\n"
                    elif category == "static_methods":
                        qual, rest = sig.split('.', 1)
                        deps_section += f"- name: {sig}\n"
                        deps_section += f"  class: {qual}\n"
                    elif category == "static_constants":
                        if '.' in sig:
                            qual, name = sig.split('.', 1)
                            deps_section += f"- name: {name}\n"
                            deps_section += f"  class: {qual}\n"
                        else:
                            deps_section += f"- name: {sig}\n"
                            deps_section += f"  class: {found_class or class_name}\n"
                    elif category == "superclass_methods":
                        # Use the class where the method was actually found
                        deps_section += f"- name: {sig}\n"
                        deps_section += f"  class: {found_class or class_name}\n"
                    elif category == "self_helpers":
                        deps_section += f"- name: {sig}\n"
                        deps_section += f"  class: {found_class or class_name}\n"
                    
                    # Add the implementation
                    deps_section += f"  definition:\n"
                    if impl is None:
                        deps_section += f"    // Could not find implementation for {sig}\n"
                    else:
                        impl_text = impl[0] if isinstance(impl, tuple) else impl
                        if impl_text is None:
                            deps_section += f"    // Could not find implementation for {sig}\n"
                        else:
                            for line in impl_text.splitlines():
                                deps_section += f"    {line}\n"
                    deps_section += "\n"

    # Add MUT delimiting to class code
    marked_method = f"""// === BEGIN: METHOD UNDER TEST ===
    {mut_body}
    // === END: METHOD UNDER TEST ==="""
    
    # Replace the method in the class code with the marked version
    if class_code:
        class_code = class_code.replace(mut_body, marked_method)
    else:
        class_code = marked_method

    # Add the test method insertion comment to the scaffold
    scaffold_edited = scaffold
    last_brace_pos = scaffold_edited.rfind('}')
    if last_brace_pos != -1:
        scaffold_edited = scaffold_edited[:last_brace_pos] + '    // INSERT TEST METHOD HERE\n' + scaffold_edited[last_brace_pos:]

    system_message = "You are a unit testing specialist."

    prompt = f"""=== CONTEXT ===

1. Shortened Class Under Test:

```java
{class_code}
```

{deps_section}
3. Existing Test File Scaffold:

```java
{scaffold_edited}
```
{example_note}
4. Unit Test Scenario (the scenario for which you will generate a test method):

{scenario.title}: {scenario.description}

=== INSTRUCTIONS ===

1. You are a **unit testing specialist**. Your task is to write exactly one JUnit {junit_version} test method targeting the single Method Under Test — {mut_sig} — not any other methods in the superclass.

2. **Focus solely on testing {mut_sig}**. Do not add tests for any other methods or behaviors. Your only test method will be inserted at the "// INSERT TEST METHOD HERE" placeholder in the scaffold. Do **not** add or remove imports, package declarations, or class headers.

3. The test method must be:
   - "public void" with a descriptive name.
   - Annotated with "@Test".
   - Its name must be unique: do not reuse any existing method names in the test file scaffold.
     - Inspect the scaffold section to avoid naming collisions.
     - Derive a meaningful name that reflects the scenario title and description.

4. **Structured‐Output Requirement**:
   - Return exactly one JSON object matching this schema:
    {{ "testMethod": "<your JUnit {junit_version} @Test method here>" }}
   - The value of "testMethod" should contain the entire JUnit {junit_version} test method (including @Test, signature, body, and closing brace)
   - Do **not** output any other text or JSON fields.

5. **Isolation Requirement**:
   - Each test method must be fully self-contained and must not share state (variables, mocks, or objects) with other tests.
   - Do not use `static` fields, class-level variables, or reuse mocks across test methods.
   - The test must not alter any global or external state (e.g., files, environment variables, or static singletons).
   - If unavoidable, reset or clean up within the test method body.

=== CODE GENERATION CONSTRAINTS ===

You must only reference identifiers (e.g., constants, method names, fields, classes) that appear explicitly in the prompt context:

- The "Shortened Class Under Test"
- The "Dependencies" section
- The "Scaffold" code

Do not invent or guess constants, method names, or fields that are not present in these sections.

Only use what is verifiably present in the provided context. If a constant or method does not exist in the input, omit its usage in the test.

Incorrect references will cause compilation to fail and the generated test to be discarded.


=== COMMON PITFALLS & NOTES ===

- If the Method Under Test is private, do NOT attempt to call it directly. Instead, exercise it via its public entry point.
- Attempting to call a private method directly will lead to "has private access" or "incompatible types" compiler errors.
- Only mock or stub dependencies when absolutely necessary, using the provided interfaces.
- Attempting to stub or spy a method that doesn't exist on the class under test will cause "cannot find symbol" errors; instead, use real public constructors or factory methods.
- When a method's return type is more general (e.g., `Object`), cast the result appropriately if assigning it to a more specific type.
- Your goal is compilable code — align all references and mocking logic exactly with what is available in the provided context.
"""

    return system_message, prompt 