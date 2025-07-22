# Compile Fix Loop Flowchart (Concise Version)

This flowchart shows the process for fixing compilation errors in test methods using an iterative LLM-based approach.

```mermaid
%%{init:{
  "theme":"base",
  "flowchart":{"htmlLabels":true},
  "themeVariables":{
    "fontSize":"43px",
    "nodeSpacing":"50",
    "rankSpacing":"40",
    "diagramPadding":"15",
    "edgeLabelBackground":"#ffffff"
  }
}}%%
flowchart TD
    Start([<div style="width:420px;white-space:normal">Begin: Compile-Fix Loop</div>]):::startStyle
    Start --> Init[<div style="width:640px;white-space:normal">Save current as best test method<br/>Count and filter errors</div>]:::actionStyle
    Init --> StartLoop[<div style="width:540px;white-space:normal">Begin fix attempts #40;1 to 7#41;</div>]:::actionStyle
  
    StartLoop --> CallLLM[<div style="width:420px;white-space:normal">Ask LLM for fix</div>]:::actionStyle
    CallLLM --> ValidResponse{<div style="width:320px;white-space:normal">Valid<br/>response?</div>}:::conditionalStyle
    ValidResponse -->|No| MoreAttempts{<div style="width:320px;white-space:normal">More<br/>attempts?</div>}:::conditionalStyle
    ValidResponse -->|Yes| ApplyFix[<div style="width:420px;white-space:normal">Apply fix</div>]:::actionStyle
  
    ApplyFix --> TestCompile[<div style="width:420px;white-space:normal">Test compilation</div>]:::actionStyle
    TestCompile --> CompileSuccess{<div style="width:320px;white-space:normal">Compilation<br/>successful?</div>}:::conditionalStyle
    CompileSuccess -->|Yes| Success[<div style="width:400px;white-space:normal">SUCCESS<br/>Return fixed method</div>]:::successStyle
    CompileSuccess -->|No| CountErrors[<div style="width:420px;white-space:normal">Count new<br/>compilation errors</div>]:::actionStyle
  
    CountErrors --> CompareErrors{<div style="width:400px;white-space:normal">New error count better than best?</div>}:::conditionalStyle
    CompareErrors -->|Yes| UpdateBest[<div style="width:420px;white-space:normal">Update best method<br/>and error count</div>]:::actionStyle
    CompareErrors -->|No| KeepPrevious[<div style="width:320px;white-space:normal">Keep previous best</div>]:::actionStyle
  
    UpdateBest --> MoreAttempts
    KeepPrevious --> MoreAttempts
    MoreAttempts -->|Yes| StartLoop
    MoreAttempts -->|No| Failure[<div style="width:420px;white-space:normal">FAILURE<br/>Return best method</div>]:::failureStyle

    %% Style definitions
    classDef actionStyle      fill:#e8f5e8,stroke:#333,stroke-width:1px
    classDef conditionalStyle fill:#fff3e0,stroke:#333,stroke-width:1px,shape:diamond
    classDef startStyle       fill:#e3f2fd,stroke:#333,stroke-width:1px
    classDef successStyle     fill:#c8e6c9,stroke:#333,stroke-width:1px
    classDef failureStyle     fill:#ffcdd2,stroke:#333,stroke-width:1px


```

## Key Optimizations Made:

1. **Combined Initialization Steps**: Merged "Save original as best", "Count errors", and "Filter errors" into a single initialization step
2. **Simplified LLM Interaction**: Combined "Build prompt" and "Call LLM" into one step
3. **Split Fix Application**: Separated "Apply fix" and "Test compilation" into distinct steps
4. **Added Error Evaluation Granularity**: Split error handling into distinct steps while keeping it compact
5. **Removed Redundant Steps**: Eliminated intermediate steps that don't add significant value to understanding the algorithm

## Preserved Scientific Accuracy:

- **Core Algorithm Logic**: All decision points and control flow remain intact
- **Error Tracking**: The improvement evaluation mechanism is preserved with more granularity
- **Iterative Nature**: The loop structure and attempt counting are maintained
- **Success/Failure Conditions**: Both exit conditions are clearly defined

## Configuration Parameters (Unchanged):

| Parameter    | Default Value | Description                                      |
| ------------ | ------------- | ------------------------------------------------ |
| max_attempts | 7             | Maximum number of fix attempts                   |
| max_examples | 3             | Maximum number of examples to include in prompts |
| Build System | Auto-detected | Maven or Gradle based on project structure       |

This version adds granularity to error evaluation while maintaining compactness (12 nodes total).

### Key Features

- **Progress Tracking**: Tracks error count improvement across attempts
- **Best Method Preservation**: Always keeps the best version seen so far
- **Maven/Gradle Support**: Handles different build system outputs
- **LLM Validation**: Checks for valid responses before compilation
- **Error Filtering**: Extracts relevant compilation errors for Maven projects
