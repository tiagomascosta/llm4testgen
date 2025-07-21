# Test Suite Generator

A modular tool for generating test suites for Java projects using LLMs.

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

## Reasoning Models

This tool supports reasoning models like `deepseek-r1` that can think through problems step-by-step before generating tests. This is particularly useful for complex code analysis and comprehensive test scenario generation.

### Using Reasoning Models

```bash
python generate_test_suite.py \
  --local-path input/Leetcode \
  --method com.fishercoder.solutions._235#lowestCommonAncestor \
  --code-model deepseek-r1:32b \
  --non-code-model deepseek-r1:32b
```

The tool automatically detects reasoning models and enables their thinking capabilities.

## Remote Ollama Setup (Bigfoot GPU)

This tool requires Ollama to be running for LLM-based test generation. If you're using remote GPU resources (like Bigfoot), follow this guide to set up SSH tunneling.

### Quickstart: SSH Tunnel to Ollama on Bigfoot GPU Node

This guide shows you how to:

1. Submit an interactive GPU job on **Bigfoot** and start Ollama
2. Open a persistent SSH tunnel from your laptop into the GPU node
3. Smoke-test the remote Ollama server from your local machine

You'll use **three terminal windows**:

- **Window 1**: Launch job & start Ollama on the GPU node
- **Window 2**: Hold open the SSH port-forward
- **Window 3**: Run your smoke-test commands

---

#### Prerequisites

- Username: `tiagomascosta-ext`
- Bastion host: `rotule.univ-grenoble-alpes.fr`
- Head node: `bigfoot`
- GPU node (assigned by OAR): e.g. `bigfoot3`
- Ollama binaries in `~/bin` on the GPU node

---

#### 1. Window 1: Submit job & start Ollama

1. **SSH through bastion → head node**
   ```bash
   ssh -tt \
     -J tiagomascosta-ext@rotule.univ-grenoble-alpes.fr \
     tiagomascosta-ext@bigfoot
   ```
2. **Submit interactive GPU job**
   ```bash
   oarsub -I -l /host=1/gpu=1 --project pr-nocode-llm
   ```
3. **On the GPU node** (e.g. `bigfoot3`), bind Ollama to all interfaces and launch:
   ```bash
   export OLLAMA_HOST="http://0.0.0.0:11434"
   ./ollama serve &
   ```

   - Ollama will now listen on `bigfoot3:11434`

Leave **Window 1** open—the `oarsub` session and Ollama server must stay running.

---

#### 2. Window 2: Open SSH tunnel

In a new terminal on your **laptop**, run:

```bash
ssh -N -tt \
  -J tiagomascosta-ext@rotule.univ-grenoble-alpes.fr \
  -L 11434:bigfoot3:11434 \
  tiagomascosta-ext@bigfoot
```

- `-N` : no remote command (tunnel only)
- `-tt`  : force a pseudo-TTY (for bastion login)
- `-J …` : proxy via bastion
- `-L 11434:bigfoot3:11434`
  - forwards **local** port 11434 → **bigfoot** → connects to `bigfoot3:11434`

Keep **Window 2** running to maintain the tunnel.

---

#### 3. Window 3: Smoke-test from your laptop

With the tunnel up, open another terminal and run:

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

If you see `"response":"4."`, your tunnel and Ollama server are working end-to-end!

---

You can now replicate this setup anytime you need remote Ollama access on Bigfoot's GPUs. Enjoy!

## Requirements

- Python 3.7+
- GitPython
- Java JDK (version required by the target project) 