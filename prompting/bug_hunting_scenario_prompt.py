"""
Bug hunting scenario generation prompt template.
This module contains the prompt template for generating bug hunting scenarios.
"""

from pydantic import BaseModel, Field
from typing import List, Tuple

class Scenario(BaseModel):
    title: str = Field(..., description="Short identifier for the bug hunting scenario")
    description: str = Field(..., description="1–2 sentence summary of the bug hunting scenario")

class BugHuntingScenarios(BaseModel):
    scenarios: List[Scenario] = Field(
        ..., description="Bug hunting scenarios with title and description"
    )


def build_bug_hunting_scenario_prompt(method_info: dict) -> Tuple[str, str]:
    """
    Builds a prompt for analyzing a method and generating bug hunting scenarios.
    
    Args:
        method_info: Dictionary containing method information including:
            - class_name: Name of the class containing the method
            - method_name: Name of the method
            - method_signature: Full method signature
            - method_code: Implementation of the method
            - class_code: Full class code
            - docstring: Method documentation if available
    
    Returns:
        Tuple[str, str]: A tuple containing (system_message, prompt)
    """
    # Add comment markers around the method under test in the class code
    class_code = method_info['class_code']
    method_code = method_info['method_code'].strip()  # Remove any leading/trailing whitespace
    marked_method = f"""// ===== BEGIN: METHOD UNDER TEST =====
    {method_code}
    // ===== END: METHOD UNDER TEST ====="""
    
    # Replace the method in the class code with the marked version
    class_code = class_code.replace(method_code, marked_method)

    # Extract method type from signature
    method_type = method_info['method_signature'].split()[0]  # Get first word of signature

    system_message = "You are an expert Java software tester specialized in finding bugs and vulnerabilities. Your task is to propose adversarial and edge-case scenarios that are most likely to reveal bugs."

    prompt = f"""=== BUG HUNTING PROMPT ===

You are an expert Java software tester specialized in finding bugs and edge cases.

**Task**: Analyze the method `{method_info['method_name']}` and generate comprehensive bug-hunting test scenarios.

**Method Information**:
- Name: `{method_info['method_name']}`
- Signature: `{method_info['method_signature']}`
- Class: `{method_info['class_name']}`

**Code**:
```java
{method_info['method_code']}
```

**Objective**: Generate test scenarios most likely to reveal bugs, focusing on inputs that violate assumptions, exceed boundaries, or trigger edge cases.

---

## BUG HUNTING CATEGORIES

Systematically cover these categories based on what applies to this specific method:

### 1. INPUT VALIDATION & PRECONDITIONS
- **Null inputs**: Test all parameters that could be null
- **Empty collections**: Empty arrays, lists, strings, trees
- **Out-of-range values**: Parameters exceeding their valid domain
  * Geographic coordinates outside [-90,90] for latitude, [-180,180] for longitude
  * Negative values for size/length parameters
  * Invalid enum-like values
- **Missing validation**: Inputs that should throw exceptions but might not
- **Boundary violations**: Values at or just beyond valid limits

### 2. ARITHMETIC & NUMERIC EDGE CASES
- **Integer overflow/underflow**: Operations involving Integer.MIN_VALUE, Integer.MAX_VALUE
- **Extreme value arithmetic**: 
  * Subtraction: `Integer.MAX_VALUE - Integer.MIN_VALUE`
  * Multiplication: Large values that overflow when multiplied
  * Division: Division by zero, division with extreme values
- **Floating-point issues**: NaN, Infinity, loss of precision
- **Sign handling**: Negative numbers where positives expected, or vice versa
- **Type boundaries**: Testing at min/max values of primitive types

### 3. ALGORITHMIC CORRECTNESS
- **Comparison logic errors**: Edge cases in conditionals (==, >, <, >=, <=)
- **Off-by-one errors**: Loop boundaries, array indices, substring ranges
- **Incorrect branching**: Inputs causing wrong control flow path
- **State machine errors**: Invalid state transitions or unhandled states
- **Termination conditions**: Inputs causing infinite loops or premature exits

### **3A. REFLECTION & DYNAMIC ACCESS (if applicable):**
- **Array index assumptions**: 
  * Does the code assume array/list order matches another collection?
  * Example: `methods[i]` where `i` indexes into a different collection
  * getDeclaredMethods() returns methods in **undefined order** - NOT declaration order
- **Reflection access violations**:
  * setAccessible() calls that might fail
  * invoke() on wrong method or wrong object
  * Type mismatches in reflective calls
- **Type casting assumptions**:
  * instanceof checks that don't cover all subtypes
  * Missing type-specific handling (e.g., booleans vs strings)
  * Coercion logic that fails for certain types

### 4. DATA STRUCTURE EDGE CASES
- **Tree structures**: Null nodes, single-node trees, extremely unbalanced trees, circular references
- **Arrays/Collections**: Length 0, length 1, maximum size, containing extreme values
- **Strings**: Empty, single-character, very long, special characters, unicode
- **Graphs**: Disconnected components, self-loops, cycles

### 5. DOMAIN-SPECIFIC CONSTRAINTS
Consider the method's domain and identify:
- **Physical/real-world limits**: What values are physically impossible or meaningless?
- **Business logic constraints**: What inputs violate domain rules even if syntactically valid?
- **Format requirements**: For parsers/tokenizers, test malformed input structures
- **Ordering dependencies**: For parsers, test elements in wrong order (e.g., END before BEGIN)

### **5A. TYPE SYSTEM & COERCION (if applicable):**
- **Type-specific handling**:
  * Do certain types require special coercion? (e.g., booleans: "true"/"false"/"1"/"0")
  * Are string representations handled consistently across types?
  * Edge cases: empty strings, "null", "undefined"
- **Scalar vs complex types**:
  * Test with each scalar type variant if multiple exist
  * Boundary between scalar and non-scalar types

### 6. STRING PARSING & FORMATTING (if applicable)
- **Malformed input**: Missing delimiters, reversed markers, unclosed quotes
- **Invalid character sequences**: Illegal combinations for the format
- **Trailing/leading issues**: Invalid characters at start or end
- **Escape sequences**: Incorrect escaping, unescaped special characters
- **Scientific notation** (for number parsers): "1.23e+", "5E-", "1e.5", trailing operators

### 7. MATHEMATICAL FUNCTIONS (if applicable)
- **Domain violations**: sqrt of negative, asin/acos outside [-1,1], log of negative
- **Trigonometric edge cases**: Angles causing tan→∞, division by zero in formulas
- **Transcendental functions**: Inputs causing NaN, Infinity propagation

### 8. CONCURRENCY & STATE (if applicable)
- **Race conditions**: Concurrent access to shared state
- **Non-reentrant code**: Methods that can't be called recursively or simultaneously

### 9. RESOURCE & PERFORMANCE
- **Memory exhaustion**: Very large inputs causing OutOfMemoryError
- **Stack overflow**: Deep recursion without proper base cases
- **Timeout scenarios**: Inputs causing excessive computation time

---

## SCENARIO SPECIFICATION REQUIREMENTS

For each bug-hunting scenario you generate:

1. **Be Specific**: Provide exact input values, not just categories
   - Good: "Build BST with root(0), left(-1000), right(1000). Set p=node(-1000), q=node(-500) both in left subtree. Expected LCA is node(-1000), not root."
   - Good: "Test with array = [Integer.MIN_VALUE, Integer.MAX_VALUE], expect overflow detection"
   - Good: "Test with arguments list size 5 but annotation methods array size 3, accessing methods[4] should throw ArrayIndexOutOfBoundsException"
   - Good: "Test with GraphQLBoolean type and string value 'true', expect proper boolean coercion not string"
   - Bad: "Test with large values"

2. **State Expected Behavior**: Clearly indicate what should happen
   - Valid result with expected value
   - Specific exception type (IllegalArgumentException, ArithmeticException, etc.)
   - Error condition or undefined behavior

3. **Explain the Bug Potential**: Why is this input dangerous?
   - What assumption does it violate?
   - What calculation could fail?
   - What validation is missing?

4. **Focus on Detection**: Design tests to REVEAL bugs, not just achieve coverage
   - Prioritize inputs that have historically caused bugs in similar code
   - Think adversarially: "How would I break this method?"

---

## OUTPUT FORMAT

Return a JSON object with a "scenarios" array. Each scenario must have:
- **title**: Concise identifier (CamelCase, e.g., "IntegerOverflowInSubtraction")
- **description**: 2-4 sentences containing:
  * Exact input specification
  * Expected behavior/result
  * Why this could reveal a bug

**Schema**: {BugHuntingScenarios.model_json_schema()}

---

## IMPORTANT REMINDERS

- **Quality over quantity**: 8-15 high-impact scenarios better than 50 generic ones
- **Avoid redundancy**: Don't generate multiple scenarios testing the same edge case
- **Think like an attacker**: What inputs would a malicious user provide?
- **Consider the unexpected**: What did the developer probably NOT think about?
- **Real bugs are subtle**: Focus on corner cases where multiple conditions interact

Generate your bug-hunting scenarios now.
"""

    return system_message, prompt