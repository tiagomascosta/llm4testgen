from typing import List, Tuple
from pydantic import BaseModel, Field

class Scenario(BaseModel):
    title: str = Field(..., description="Short identifier, e.g. 'AlarmFlagPopulation'")
    description: str = Field(..., description="1–2 sentence summary of the scenario")

class ScenarioList(BaseModel):
    scenarios: List[Scenario] = Field(..., description="Clustered scenarios")

def build_clustering_prompt(raw_scenarios: List[str], method_name: str, junit_version: int, method_info: dict = None) -> Tuple[str, str]:
    """
    Build the prompt for clustering scenarios into test themes.
    
    Args:
        raw_scenarios: List of raw scenario descriptions
        method_name: Name of the method being tested
        junit_version: JUnit version (4 or 5)
        method_info: Dictionary containing method information including class_code and method_code
        
    Returns:
        Tuple[str, str]: A tuple containing (system_message, prompt)
    """
    scenarios_list = "\n".join(f"- {s}" for s in raw_scenarios)
    
    # Add class under test with MUT delimiting if method_info is provided
    class_section = ""
    if method_info and 'class_code' in method_info and 'method_code' in method_info:
        # Add comment markers around the method under test in the class code
        class_code = method_info['class_code']
        method_code = method_info['method_code'].strip()  # Remove any leading/trailing whitespace
        marked_method = f"""// ===== BEGIN: METHOD UNDER TEST =====
    {method_code}
    // ===== END: METHOD UNDER TEST ====="""
        
        # Replace the method in the class code with the marked version
        class_code = class_code.replace(method_code, marked_method)
        
        # Extract method type from signature
        method_type = method_info.get('method_signature', '').split()[0] if method_info.get('method_signature') else 'method'
        
        class_section = f"""
=== CLASS UNDER TEST ===
```java
{class_code}
```

(Note: Within this class, the MUT is the {method_type} method:

```java
{method_info.get('method_signature', '')}
```

All other code in the class exists only to show how `{method_name}` is invoked and what helpers it relies on. Focus your clustering exclusively on scenarios for {method_name}.)

"""
    
    system_message = f"You are a Senior Java unit‐testing strategist. Group raw scenario sentences into high‐level themes, which will be used to generate exactly one JUnit {junit_version} test method later."
    
    prompt = f"""=== TASK ===
Given a list of raw scenario sentences, group them into high‐level test themes. Each resulting theme will be later used to generate one, and only one, JUnit {junit_version} test method.

{class_section}

=== RAW SCENARIOS ===
{scenarios_list}

=== INSTRUCTIONS ===
1. Identify groups of raw sentences that test essentially the same logic in `{method_name}`.
   - For example, "sentence too short" and "hex substring at indices 6–8 fails to parse" both relate to parsing errors and should be folded together.
   - If two or more raw scenarios truly share the same testing concern (e.g. "null input → expect null" vs. "empty string → expect null"), collapse them under a single theme.

2. For each group you identify, create exactly one object with:
   • "title": a concise CamelCase identifier
   • "description": exactly 2–3 sentences explaining:
       – which raw conditions this single JUnit {junit_version} test method will cover - be explicit!,
       – and what precise outcome it must assert.

3. If two raw scenarios do not share the same precise testing concern, keep them separate.  
   - Do NOT merge scenarios that test unrelated behaviors just because they share keywords (e.g. both mention "Parser" but cover different edge cases).

4. If collapsing two scenarios may lead to the generation of more than one test method later you should avoid clustering them and you should keep them separate.  

=== OUTPUT FORMAT ===
Return exactly one JSON object with the key "scenarios", whose value is an array of objects. Each object must have exactly two fields—"title" (a CamelCase identifier) and "description" (2–3 sentences). The JSON must conform to this schema:
{ScenarioList.model_json_schema()}"""

    return system_message, prompt 