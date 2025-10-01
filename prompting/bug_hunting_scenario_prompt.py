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

    prompt = f"""=== TASK ===
Enumerate all plausible scenarios that could reveal bugs or vulnerabilities for the Method Under Test (MUT) named {method_info['method_name']}, shown in the class below.

=== CLASS UNDER TEST ===
```java
{class_code}
```

(Note: Within this class, the MUT is the {method_type} method:

```java
{method_info['method_signature']}
```

All other code in the class exists only to show how `{method_info['method_name']}` is invoked and what helpers it relies on. Focus your bug hunting scenarios exclusively on {method_info['method_name']}.)

=== INSTRUCTIONS ===
- Each scenario should have a short title and a detailed description.
- Scenarios should cover, at minimum:
  * Edge cases (empty, null, very large, very small, special characters)
  * Stress cases (concurrency, large loops, deep recursion)
  * Invalid or malformed inputs
  * Security-sensitive cases (injection strings, path traversal, unexpected formats)
  * Boundary value violations
  * Resource leaks and memory issues
  * Race conditions and invalid state transitions
- Consider adversarial scenarios that normal testing might miss
- Think about what could go wrong under unusual or malicious conditions
- Do NOT include test code, method names, or boilerplate — only human-readable scenario descriptions.
- Be specific about the potential failure mode or vulnerability type.
- Title should be a short identifier (e.g., "NullInputHandling", "BoundaryValueOverflow")
- Description should be 1-2 sentences explaining the bug hunting scenario

=== OUTPUT FORMAT ===
Return exactly one JSON object with the key "scenarios", whose value is an array of objects with "title" and "description" fields. The JSON must conform to this schema:
{BugHuntingScenarios.model_json_schema()}"""

    return system_message, prompt