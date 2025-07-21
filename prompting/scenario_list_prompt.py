"""
This module contains all prompt templates used in the test generation process.
Each prompt is defined as a function that takes the necessary context and returns a formatted prompt.
"""

from pydantic import BaseModel, Field
from typing import List, Tuple

class RawScenarios(BaseModel):
    scenarios: List[str] = Field(
        ..., description="Raw one-sentence scenario descriptions"
    )

def build_scenario_list_prompt(method_info: dict) -> Tuple[str, str]:
    """
    Builds a prompt for analyzing a method and generating a list of test scenarios.
    
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

    system_message = "You are a Senior Java unit‐testing expert. Enumerate every distinct behavior, edge‐case, and error path for a given method."

    prompt = f"""=== TASK ===
Provide a comprehensive list of behaviors, edge cases, and error paths that a unit test should cover for the Method Under Test (MUT) named {method_info['method_name']}, shown in the class below.

=== CLASS UNDER TEST ===
```java
{class_code}
```

(Note: Within this class, the MUT is the {method_type} method:

```java
{method_info['method_signature']}
```

All other code in the class exists only to show how `{method_info['method_name']}` is invoked and what helpers it relies on. Focus your scenarios exclusively on {method_info['method_name']}.)

=== INSTRUCTIONS ===
- Each string is one sentence describing: "under this specific condition, we expect this precise outcome."
- Cover null or invalid inputs, parsing failures, boundary values, side‐effects (if any) and error paths.
- You MUST cover the core success path as well.
- Do NOT include test code, method names, or boilerplate — only human‐readable scenario descriptions.
- Be concise but specific: avoid vague phrases like "error return" without saying what error.

=== OUTPUT FORMAT ===
Return exactly one JSON object with the key "scenarios", whose value is an array of one-sentence strings. The JSON must conform to this schema:
{RawScenarios.model_json_schema()}"""

    return system_message, prompt 