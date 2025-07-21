from typing import List, Tuple
from pydantic import BaseModel, Field
import json

class CodeOnly(BaseModel):
    """Model for compile fix response."""
    code: str = Field(
        ..., 
        description="The corrected test method code, including @Test annotation, signature, body, and closing brace"
    )

def build_compile_fix_prompt(
    test_method: str,
    scaffold: str,
    compilation_errors: str,
    class_code: str,
    junit_version: int,
    recent_successful_tests: List[str] = None,
    max_examples: int = 3
) -> Tuple[str, str]:
    """
    Build the prompt for fixing compilation errors in a test method.
    
    Args:
        test_method: The test method that failed to compile
        scaffold: The test class scaffold
        compilation_errors: The compilation error output
        class_code: The class under test code
        junit_version: The JUnit version being used
        recent_successful_tests: List of recent successful test methods
        max_examples: Maximum number of examples to include (default 3)
        
    Returns:
        Tuple of (system_message, prompt)
    """
    # Build examples block from recent successful tests
    examples_block = ""
    if recent_successful_tests and max_examples > 0:
        examples_block = "=== COMPILED TEST METHODS (REFERENCE ONLY) ===\n"
        for idx, method_body in enumerate(recent_successful_tests[-max_examples:], start=1):
            # Label examples as A, B, C, etc.
            label = chr(64 + idx)  # A=65, B=66, C=67, etc.
            examples_block += f"- Example {label}:\n```java\n{method_body}\n```\n\n"
    
    # Indent examples to look like they're inside the class
    if examples_block:
        lines = examples_block.splitlines()
        if lines:
            # Leave the first line as-is, indent the rest
            indented_examples = lines[0] + "\n" + "\n".join("    " + l for l in lines[1:])
            # Add note about not reusing names
            indented_examples += "\n    // Note: The example test method names above are for reference only — do not reuse or copy their names.\n"
        else:
            indented_examples = ""
    else:
        indented_examples = ""
    
    # Insert the test method directly into the scaffold
    scaffold_with_test = scaffold
    last_brace_pos = scaffold_with_test.rfind('}')
    if last_brace_pos != -1:
        # Insert the test method before the closing brace
        scaffold_with_test = scaffold_with_test[:last_brace_pos] + test_method + '\n' + scaffold_with_test[last_brace_pos:]
    
    system_message = "You are a senior Java unit-testing specialist."
    
    prompt = f"""
You are a senior Java unit‐testing specialist. The compilation errors below pertain only to the generated test method inside the provided JUnit {junit_version} test file (the `@Before` setup and imports are already correct). Your job is to return only the corrected test method so that the file compiles without errors.

=== CLASS UNDER TEST (REFERENCE ONLY) ===
```java
{class_code}
```

=== FULL TEST FILE (with the test method that doesn't compile) ===
```java
{scaffold_with_test}
```

=== COMPILER ERRORS ===
{compilation_errors}

{indented_examples}

=== INSTRUCTIONS ===
1. Examine the compiler errors; they arise only from the test method itself.
2. Return a corrected version of that test method (including `@Test`, signature, body, and closing brace) so that the full test file compiles.
   - Do NOT modify any imports, package declarations, or the `@Before` setup (if it exists).
   - Only change the lines inside the failing test method.
   - The test method name must remain exactly the same — do NOT rename it.
3. Provide your answer as a JSON object with exactly one key "code", whose value is the full corrected test method. For example:
{{"code": "    @Test\\n    public void testXYZ() {{\\n        ...\\n    }}"}}
4. Do NOT wrap your JSON in Markdown fences and do NOT include any explanatory text—only valid JSON matching this schema:
{CodeOnly.model_json_schema()}

=== TROUBLESHOOTING TIPS ===
- If you see an error indicating a value of a general type can't be assigned to a more specific type (e.g., "incompatible types: Object cannot be converted to X"), insert an explicit cast so that the code compiles.
- If the compiler errors include "`has private access`" (or any "private"‐access‐related issue), replace any direct call to a private method with a call to its public entry point.
- If you see "cannot find symbol: method foo(…)" (i.e., you tried to stub or call a helper that doesn't exist), stop attempting to mock that non-existent method. Instead, construct or spy the real helper type via its public API and pass it into the SUT.
- Use the example test methods above as reference for correct syntax and patterns.
- If the error message says a class or method "has private access", and you are referencing a **private inner class**, you cannot access it directly by name. 
  (Use this workaround only when strictly necessary — e.g., the private inner class holds critical state with no public access.)

    Instead, use reflection to load and instantiate the class.

    Example:
    ```java
    @Test
    public void testUsingPrivateClass() throws Exception {{
        Class<?> cls = Class.forName("com.example.Outer$PrivateInner");
        Constructor<?> ctor = cls.getDeclaredConstructor();
        ctor.setAccessible(true);
        Object instance = ctor.newInstance();

        Method method = Outer.class.getDeclaredMethod("somePrivateMethod", cls);
        method.setAccessible(true);
        method.invoke(null, instance);
    }}
    ```

- Do not attempt to use `getDeclaredClass(String)` — this method does not exist in the Java Reflection API. Use `Class.forName("...$Inner")` instead to access private inner classes.
- Do not use the private class name directly in variable declarations or method signatures. Use `Object` and `Class<?>` instead.
- If accessing fields inside a private object, use reflection (`getDeclaredField`, `setAccessible(true)`, `get()`).
- Do not use `.thenReturn(SomeClass.class)` unless the mocked method is expected to return a `Class<?>`.  
  If the method is expected to return an *instance* of the class (e.g., `SomeClass`), then calling `.thenReturn(SomeClass.class)` will produce a **generic type mismatch error**.  
  In this case, return an actual instance (e.g., `new SomeClass()`) or use a proper mock/stub.
- If you see errors involving `thenReturn(SomeClass.class)` and the method does not return a `Class<?>`, change the return value to a valid mock or real instance that satisfies the expected return type of the method.  
  You may use `mock(SomeClass.class)` or a minimal constructor if applicable:
  ```java
  when(mock.method()).thenReturn(mock(SomeClass.class));
  ```
- Do not mix different provider types. If a method expects `com.google.inject.Provider`, do not pass `javax.inject.Provider`, as they are **not compatible** and will trigger type mismatch errors.  
  You cannot fix this through casting alone. Instead, avoid making such substitutions within the test method.
"""
    
    return system_message, prompt 