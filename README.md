# LLM4TestGen: An Automated Self-Repair LLM-Driven System for Java Unit Test Generation

A modular tool for generating test suites for Java projects using LLMs.

## Quick Start

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd implementation
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv .venv
   ```

3. **Activate the virtual environment**
   ```bash
   # On Linux/macOS
   source .venv/bin/activate
   
   # On Windows
   .venv\Scripts\activate
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Set up Ollama** (required for LLM-based test generation)
   
   Ensure Ollama is installed and running. See the [Remote Ollama Setup](#remote-ollama-setup) section for configuring remote GPU access, or run Ollama locally:
   ```bash
   ollama serve
   ```

You're now ready to use LLM4TestGen! See the [Usage](#usage) section below to get started.

## Features

- Repository management (clone or use local)
- Gradle configuration (JUnit, JaCoCo)
- JDK version detection
- Project build automation
- **Reasoning model support** (deepseek-r1) for enhanced test generation

## Usage

```bash
python generate_test_suite.py --repo-url <REPO_URL> [--commit-hash <HASH>] [--output-dir <DIR>]
```

### Quick Examples

Here are some quick commands to test the tool:

```bash
# Example 1: Generate tests for a semantic versioning library
python -m generate_test_suite \
    --repo-url https://github.com/semver4j/semver4j.git \
    --commit-hash 48ffbfd1f66c78c43599e64ac3068038caba1766 \
    --fix-commit-hash beb7e5d466c708721740f6fe99ca33ca9f4ed9ea \
    --method org.semver4j.internal.range.processor.XRangeProcessor#process

# Example 2: Generate tests for a LeetCode solution
python -m generate_test_suite \
    --repo-url https://github.com/nikoo28/java-solutions.git \
    --commit-hash 7a73ea56d05ff1f0fa085da259d02cb247b29db8 \
    --fix-commit-hash 8d81307ea1651f3dffe2d9d620378c08f04463ee \
    --method leetcode.medium.OnlineStockSpan#calculateSpans

# Example 3: Generate tests for a math algorithm
python -m generate_test_suite \
    --repo-url https://github.com/TheAlgorithms/Java.git \
    --commit-hash 4fab7adfaa3679d8b41360d169b40ee18b9ed735 \
    --fix-commit-hash a3a2d845d563a901946e052eeebba2f6e51e37d8 \
    --method com.thealgorithms.maths.Armstrong#isArmstrong
```

## Reasoning Models

This tool supports reasoning models like `deepseek-r1` that can think through problems step-by-step before generating tests. This is particularly useful for complex code analysis and comprehensive test scenario generation.

### Using Reasoning Models

```bash
python generate_test_suite.py \
  --repo-url https://github.com/fishercoder1534/Leetcode.git \
  --commit-hash 24b7a6aecc4e431640a2b82a562199008a8bb896 \
  --fix-commit-hash 2110c6b023b7c5623b2603dae9979201f2b2c3ac \
  --method com.fishercoder.solutions._235#lowestCommonAncestor \
  --code-model deepseek-r1:32b \
  --non-code-model deepseek-r1:32b
```

The tool automatically detects reasoning models and enables their thinking capabilities.

## Remote Ollama Setup

This tool requires Ollama to be running for LLM-based test generation. If you're using remote GPU resources, follow this guide to set up SSH tunneling.

### Quickstart: SSH Tunnel to Ollama on Remote GPU Node

This guide shows you how to:

1. Connect to your remote GPU node and start Ollama
2. Open a persistent SSH tunnel from your local machine to the GPU node
3. Verify the remote Ollama server is accessible locally

You'll use **three terminal windows**:

- **Window 1**: Connect to GPU node & start Ollama
- **Window 2**: Hold open the SSH port-forward tunnel
- **Window 3**: Test the connection from your local machine

---

#### Prerequisites

- Access to a remote GPU node (via SSH)
- Ollama installed on the remote GPU node
- If using a bastion/jump host, you have SSH access configured
- If using a job scheduler (SLURM, OAR, etc.), you have permission to submit jobs

---

#### 1. Window 1: Connect to GPU node & start Ollama

1. **Connect to your GPU node**

   - If direct access: `ssh <username>@<gpu-node-hostname>`
   - If via bastion: `ssh -J <username>@<bastion-hostname> <username>@<head-node-hostname>`
   - If via job scheduler, submit an interactive job first:
     ```bash
     # Example for SLURM
     srun --gres=gpu:1 --pty bash
     
     # Example for OAR
     oarsub -I -l /host=1/gpu=1
     ```

2. **Start Ollama on the GPU node**

   ```bash
   export OLLAMA_HOST="http://0.0.0.0:11434"
   ollama serve &
   ```

   - Ollama will now listen on `<gpu-node-hostname>:11434`
   - Note the GPU node hostname for the next step

Leave **Window 1** open—the SSH session and Ollama server must stay running.

---

#### 2. Window 2: Open SSH tunnel

In a new terminal on your **local machine**, create the SSH tunnel:

**If using a bastion/jump host:**
```bash
ssh -N -tt \
  -J <username>@<bastion-hostname> \
  -L 11434:<gpu-node-hostname>:11434 \
  <username>@<head-node-hostname>
```

**If direct access:**
```bash
ssh -N -L 11434:<gpu-node-hostname>:11434 <username>@<gpu-node-hostname>
```

**Options explained:**
- `-N` : no remote command (tunnel only)
- `-tt` : force a pseudo-TTY (needed if going through bastion)
- `-J` : proxy via jump host/bastion
- `-L 11434:<gpu-node-hostname>:11434` : forwards local port 11434 → remote host → connects to `<gpu-node-hostname>:11434`

Keep **Window 2** running to maintain the tunnel.

---

#### 3. Window 3: Test connection from local machine

With the tunnel active, open another terminal and test:

```bash
curl -s -X POST http://localhost:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "mistral",
    "prompt": "What is 2+2?",
    "stream": false
  }'
```

You should receive a JSON response like:

```json
{
  "model": "mistral",
  "response": "4.",
  "done": true,
  …
}
```

If you see a successful response, your tunnel and Ollama server are working end-to-end!

---

You can now use Ollama on the remote GPU node as if it were running locally. The tool will connect to `http://localhost:11434` automatically.

## Requirements

- Python 3.7+
- GitPython
- Java JDK (version required by the target project)
