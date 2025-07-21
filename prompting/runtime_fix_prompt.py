from typing import List, Optional
from pydantic import BaseModel, Field

class RuntimeCodeOnly(BaseModel):
    """Model for runtime fix response."""
    code: str = Field(
        ..., 
        description="The corrected test method code, including @Test annotation, signature, body, and closing brace"
    )
    diagnosis: Optional[str] = Field(
        None,
        description="A 1-2 sentence diagnosis of the runtime error that was fixed (optional)"
    )

def build_runtime_fix_prompt(
    test_method: str,
    scaffold: str,
    runtime_error_output: str,
    class_code: str,
    junit_version: int,
    recent_successful_tests: List[str] = None,
    max_examples: int = 3,
    execution_progress: int = 0,
    mut_body: str = None,
    previous_diagnosis: str = None,
    previous_error_line: int = 0,
    build_system: str = None
) -> tuple[str, str]:
    """
    Build prompt for fixing runtime errors in test methods.
    
    Args:
        test_method: The test method that failed with runtime error
        scaffold: The test class scaffold
        runtime_error_output: The runtime error output from test execution
        class_code: The class under test code
        junit_version: The JUnit version being used
        recent_successful_tests: List of recent successful test methods for examples
        max_examples: Maximum number of examples to include
        execution_progress: Line number where execution failed (for progress tracking)
        mut_body: The method under test body (for MUT delimiting)
        previous_diagnosis: Previous diagnosis of the runtime error
        previous_error_line: Line number where the previous error occurred
        build_system: The build system being used (Maven or Gradle)
        
    Returns:
        Tuple of (system_message, prompt)
    """
    if recent_successful_tests is None:
        recent_successful_tests = []
    
    # Add MUT delimiting to class code (similar to test_case_prompt.py)
    if mut_body and class_code:
        # Replace the method in the class code with the marked version
        marked_method = f"""// === BEGIN: METHOD UNDER TEST ===
    {mut_body}
    // === END: METHOD UNDER TEST ==="""
        marked_class_code = class_code.replace(mut_body, marked_method)
    else:
        marked_class_code = class_code
    
    # Create scaffold with test method
    scaffold_with_test = scaffold
    last_brace_pos = scaffold_with_test.rfind('}')
    if last_brace_pos != -1:
        scaffold_with_test = scaffold_with_test[:last_brace_pos] + test_method + '\n' + scaffold_with_test[last_brace_pos:]
    
    # Add line numbers to the test file
    scaffold_with_test_lines = scaffold_with_test.split('\n')
    scaffold_with_test_numbered = ""
    for i, line in enumerate(scaffold_with_test_lines, 1):
        # Add a comment indicating where the runtime error occurred
        # Adjust line number based on build system
        adjusted_line = execution_progress
        if build_system == "maven":
            # Maven reports line N, but actual error is on line N+1 in our numbered file
            adjusted_line = execution_progress + 1
        elif build_system == "gradle":
            # Gradle reports line N, but actual error is on line N-1 in our numbered file
            adjusted_line = execution_progress - 1
        
        if execution_progress > 0 and i == adjusted_line:
            scaffold_with_test_numbered += f"{i:3d}: {line}  // <-- RUNTIME ERROR OCCURRED HERE\n"
        else:
            scaffold_with_test_numbered += f"{i:3d}: {line}\n"
    
    # Build examples section
    indented_examples = ""
    if recent_successful_tests and max_examples > 0:
        examples_to_include = recent_successful_tests[-max_examples:]
        if examples_to_include:
            indented_examples = "\n=== SUCCESSFUL TEST EXAMPLES ===\n"
            indented_examples += "These examples show previous runtime errors that were fixed and may help solve the current runtime error. Note that these methods may still have assertion errors, so use them carefully as reference only.\n"
            for example in examples_to_include:
                indented_examples += f"```java\n{example}\n```\n"
    
    # Build previous diagnosis section (only if we're still on the same line)
    previous_diagnosis_section = ""
    if previous_diagnosis and previous_error_line > 0:
        # Include previous diagnosis if we're on the same error line or within 1 line
        if previous_error_line == execution_progress or abs(previous_error_line - execution_progress) <= 1:
            # Calculate adjusted line number for display
            adjusted_display_line = previous_error_line
            if build_system == "maven":
                adjusted_display_line = previous_error_line + 1
            elif build_system == "gradle":
                adjusted_display_line = previous_error_line - 1
            previous_diagnosis_section = f"\n=== PREVIOUS DIAGNOSIS (Line {adjusted_display_line}) ===\n{previous_diagnosis}\n"
    
    system_message = "You are a Java unit testing expert. Fix the test method so it runs without runtime errors. Return only the full corrected method — no other changes."
    
    prompt = f"""
You are a senior Java unit-testing specialist. A previously compiled JUnit {junit_version} test method is causing runtime errors when executed. Your job is to fix only that test method so that it runs successfully.

=== CLASS UNDER TEST (REFERENCE ONLY) ===
```java
{marked_class_code}
```

=== FULL TEST FILE (with line numbers - the test method that throws runtime errors) ===
```java
{scaffold_with_test_numbered}
```

=== RUNTIME ERROR OUTPUT ===
{runtime_error_output}

{indented_examples}

{previous_diagnosis_section}

=== INSTRUCTIONS ===
1. Carefully read the runtime exception output. It relates specifically to the test method, not to the class under test.
2. Your task is to return a corrected version of that test method (including @Test, signature, body, and closing brace) so that it runs without throwing any runtime exceptions.
   - Do NOT modify any imports, package declarations, class headers, or setup methods like @Before.
   - You must keep the method name exactly the same — do NOT rename it.
   - Focus only on correcting the test method.
   - Do NOT include the comment stating where the runtime error occurred.
3. Provide your answer as a JSON object with exactly two keys:
   - `"code"`: the full corrected test method
   - `"diagnosis"`: a 1–2 sentence explanation of the runtime error root cause and what should be done to fix it
   For example:
   `{{"code": "    @Test\n    public void testXYZ() {{\n        ...\n    }}", "diagnosis": "The mock is returning null for the repository call, so it should be stubbed with a safe default to prevent the NPE."}}`
4. Do NOT wrap your JSON in Markdown fences and do NOT include any explanatory text—only valid JSON matching this schema:
   `{RuntimeCodeOnly.model_json_schema()}`


=== SOLVING RUNTIME ERRORS ===
1. Diagnose the Runtime Error root cause in 1–2 sentences.
2. Try these strategies:
2.1 Mockito Stubbing & Spying  
    - Use `spy()` + `doReturn(...).when(spy)...` for partial overrides.  
    - For pure mocks, use `mock()` + `when(...).thenReturn(...)`.
    - **Preserve Unstubbed Logic:** stub *only* the exact method you need; use `doReturn` so that all other methods on the spy execute their real behavior unmodified.
2.2 Guarantee Safe, Non-Null Returns  
    - Stub any mock method that could return `null` to safe defaults (e.g. `Collections.emptyList()`, `Optional.of(...)`).  
    - Return valid non-null values for primitives and wrappers (e.g. `0`, `""`, or a new object).
2.3 Consistent Argument Matching  
    - Wrap all literals with `eq(...)` if using matchers, or use matchers exclusively (`any()`, `anyString()`, `contains()`).  
    - Use `argThat(...)` when production code transforms inputs.
2.4 Single Source of Truth for Test Data  
    - Declare key values once as variables and reuse them for both stubbing and test inputs.
2.5 Verification & Inspection Hooks  
    - After stubbing, insert `verify(mock).method(expectedArgs);`.  
    - Inject `System.out.println(...)` right before the failure point.  
    - Add in-test assertions on intermediate values to pinpoint where `null` occurs.
2.6 Advanced Stub Diagnostics (Optional)  
    - Use `doAnswer(invocation -> {{ /* inspect invocation.getArguments() */ return safeValue; }}).when(spy).method(any());` to confirm stub invocation.
"""
    
    return system_message, prompt 