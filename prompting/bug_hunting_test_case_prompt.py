"""
Bug hunting test case generation prompt template.
This module contains the prompt template for generating bug hunting test cases.
"""

from typing import Dict, List, Set, Tuple
from pydantic import BaseModel, Field
import json
from source_analysis.dependency_extractor import extract_impl
from prompting.clustering_prompt import Scenario

class BugHuntingTestMethodOnly(BaseModel):
    """Model for a single bug hunting test method response."""
    testMethod: str = Field(
        ..., 
        description="The full JUnit test method code for bug hunting, including annotation and assertions"
    )

def build_bug_hunting_test_case_prompt(
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
    class_name: str = None,
    used_method_names: List[str] = None
) -> Tuple[str, str]:
    """
    Build the prompt for generating a bug hunting test case.
    
    Args:
        mut_sig: Method Under Test signature
        mut_body: Method Under Test body
        scaffold: Test class scaffold
        scenario: Bug hunting test scenario to generate
        helpers: List of helper method signatures
        junit_version: JUnit version (4 or 5)
        deps: Dictionary of dependencies by category
        qualifier_map: Map of qualifiers to their definitions
        flow_control: Set of flow control related dependencies to exclude
        example_tests: Optional list of example test methods (bug-revealing examples)
        class_code: Full class code containing the MUT
        repo_root: Root directory of the repository
        imports: Dictionary mapping class names to their package paths
        src_package: Source package of the class under test
        class_name: Name of the class under test
        used_method_names: List of already used test method names
        
    Returns:
        Tuple[str, str]: A tuple containing (system_message, prompt)
    """
    # Get the schema and pretty print it
    schema = BugHuntingTestMethodOnly.model_json_schema()
    pretty_schema = json.dumps(schema, indent=2)

    # Check if the scaffold contains example test methods
    example_note = ""
    if "// === EXAMPLE TEST METHODS ===" in scaffold:
        example_note = "\nNote: The scaffold above already has some fully‐compilable example bug-revealing test methods (marked with '// Example N') that exercise other bug hunting scenarios.\n"

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
        scaffold_edited = scaffold_edited[:last_brace_pos] + '    // INSERT BUG HUNTING TEST METHOD HERE\n' + scaffold_edited[last_brace_pos:]

    # Build method names section if provided
    method_names_section = ""
    if used_method_names:
        # Format each method name on a separate line with bullet points
        formatted_names = "\n".join([f"- {name}" for name in used_method_names])
        method_names_section = f"""
        
5. Already Used Method Names:

The following test method names have already been used in this test suite. Do NOT use any of these names for your new test method:

{formatted_names}

"""

    system_message = "You are a senior Java developer. Write a JUnit 5 test method that implements the following bug-hunting scenario. Focus on producing code that compiles, runs, and can reveal a bug if present."

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
4. Bug Hunting Test Scenario (the scenario for which you will generate a bug hunting test method):

**Title**: {scenario.title}
**Description**: {scenario.description}

{method_names_section}

---

=== INSTRUCTIONS ===

1. You are a **senior Java developer and security-minded tester**. Your task is to write exactly one JUnit {junit_version} test method that implements the bug-hunting scenario above and targets potential bugs and edge cases in the single Method Under Test — **{mut_sig}** — not any other methods in the superclass.

2. **Focus on bug hunting for {mut_sig}**. Generate a test that could reveal bugs, edge cases, or failure modes. Do not add tests for any other methods or behaviors. Your only test method will be inserted at the "// INSERT TEST METHOD HERE" placeholder in the scaffold. Do **not** add or remove imports, package declarations, or class headers.

3. The test method must be:
   - `public void` with a descriptive name that indicates it's a bug hunting test
   - Annotated with `@Test`
   - Its name must be **unique**:
     * Check the "Already Used Method Names" section above and avoid using any of those names
     * Derive a meaningful name that reflects the bug hunting scenario title and description
     * Consider using prefixes like `testBug`, `testEdgeCase`, or `testFailure` to indicate bug hunting nature

4. **Structured Output Requirement**:
   - Return exactly one JSON object matching this schema:
     `{{ "testMethod": "<your JUnit {junit_version} @Test method here>" }}`
   - The value of "testMethod" should contain the entire JUnit {junit_version} test method (including @Test, signature, body, and closing brace)
   - Do **not** output any other text or JSON fields

5. **Bug Hunting Focus - Critical Requirements**:
   - Design the test to **fail if a bug exists**, not to pass with normal behavior
   - Focus on producing code that compiles, runs, and can reveal a bug if present
   - The test should make **specific, correct assertions** based on expected behavior
   - If the scenario describes "expected result is X", assert exactly that - don't guess

6. **Isolation Requirement**:
   - Each test method must be fully self-contained and must not share state (variables, mocks, or objects) with other tests
   - Do not use `static` fields, class-level variables, or reuse mocks across test methods
   - The test must not alter any global or external state (e.g., files, environment variables, or static singletons)
   - If unavoidable, reset or clean up within the test method body

---

=== CODE GENERATION CONSTRAINTS ===

You must only reference identifiers (e.g., constants, method names, fields, classes) that appear explicitly in the prompt context:

- The "Shortened Class Under Test"
- The "Dependencies" section
- The "Scaffold" code

**Do not invent or guess** constants, method names, or fields that are not present in these sections.

Only use what is verifiably present in the provided context. If a constant or method does not exist in the input, omit its usage in the test.

Incorrect references will cause compilation to fail and the generated test to be discarded.

---

=== DOMAIN-SPECIFIC TEST PATTERNS ===

Based on the scenario description, apply the appropriate pattern:

### **A. Tree-Structured Data Tests**

If the method operates on hierarchical or node-based data structures:

1. **Build the minimal structure** (e.g., root node with children) described in the scenario.
2. **Position nodes or values** according to the scenario's description.
3. **Verify expected behavior** (returned node, value, or thrown exception) without assuming any particular algorithm (e.g., LCA) unless explicitly evident in the code.
4. **For numerical or structural stress cases**, include extreme values (e.g., Integer.MIN_VALUE, Integer.MAX_VALUE) or unbalanced shapes if relevant.

### **B. Array/Collection Processing Tests**

Follow the same logic for constructing collections or arrays: ensure inputs directly reflect the scenario description, including edge or malformed cases.

### **C. Numeric and Arithmetic Edge Tests**

When scenarios mention boundary conditions or arithmetic risks:
1. Use extreme or boundary values.
2. Assert correct behavior (proper result or exception) when overflow, underflow, or division by zero might occur.

### **D. Input Validation and Null Handling**

Include nulls, empties, or out-of-range inputs as described by the scenario to validate robustness and defensive programming.

### **E. State and Resource Integrity Tests**

If applicable, simulate invalid sequences, double calls, or missing initialization consistent with the scenario.

---

=== BUG HUNTING STRATEGIES ===

Use these as guidance to explore potential failure modes:
- Input validation (nulls, empties, out-of-range)
- Arithmetic errors (overflow, underflow, precision)
- Boundary violations (off-by-one, empty ranges)
- State mismanagement (invalid order, double-free)
- Data structure inconsistencies (unbalanced, cyclic, missing nodes)
- Domain logic errors (invalid assumptions, impossible states)
- Resource exhaustion (deep recursion, large input)

=== CRITICAL REMINDERS ===

- Read the scenario description carefully; it defines what to test.
- Build complete structures or inputs when needed, not partial stubs.
- Assert exact expected outcomes, not generic correctness.
- Use extreme and edge values when appropriate.
- Think adversarially: *What input could break this method?*

Your goal is to create a test that **reveals the bug described in the scenario** if it exists in the code.

Generate the test method now.
"""

    return system_message, prompt
