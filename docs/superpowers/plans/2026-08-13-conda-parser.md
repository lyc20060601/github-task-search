# Conda Environment Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely parse Conda environment YAML into structured environment, Python, framework, CUDA, and dependency facts.

**Architecture:** A dedicated `conda_parser.py` consumes only the existing fetcher's `environment.yml` or `environment.yaml` text. PyYAML `safe_load` converts YAML into standard containers; the parser then accepts only allow-listed scalar/list/mapping shapes and produces deterministic facts, evidence, and sanitized errors without running package-manager commands.

**Tech Stack:** Python 3.12, PyYAML safe loader, pytest

---

### Task 1: Define Conda Parsing Behavior

**Files:**
- Create: `backend/tests/test_conda_parser.py`

- [ ] **Step 1: Add fetcher-shaped input helper**

Use the same `files[path] = {content, size, truncated}` structure as the GitHub
environment fetcher.

- [ ] **Step 2: Add required tests**

Add independent assertions for `environment.yml`, `environment.yaml` fallback,
Python exact and bounded versions, PyTorch, explicit CUDA Toolkit, nested pip
dependencies, missing name, missing Python, and malformed YAML.

- [ ] **Step 3: Add precedence and framework family tests**

Assert `environment.yml` wins when both names exist. Add TensorFlow and JAX
dependency-name mapping checks, source-bearing evidence, and `None` results for
missing files.

- [ ] **Step 4: Run the suite and verify red state**

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe -m pytest tests\test_conda_parser.py -q --basetemp=.conda-parser-red-temp -p no:cacheprovider
```

Expected: collection fails because `compatibility.conda_parser` does not exist.

### Task 2: Add Safe YAML Runtime Dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add a fixed PyYAML version**

Append the currently stable project-compatible PyYAML release as an exact pin.

- [ ] **Step 2: Install backend requirements into the existing virtual environment**

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Expected: PyYAML installs successfully without changing system Python.

### Task 3: Implement the Static Conda Parser

**Files:**
- Create: `backend/compatibility/conda_parser.py`

- [ ] **Step 1: Define result and file selection**

Return all specified scalar fields initialized to `None` plus empty
`dependencies`, `evidence`, and `errors`. Select valid string content from
`environment.yml` before `environment.yaml`.

- [ ] **Step 2: Parse YAML with safe_load only**

Call only `yaml.safe_load(text)`. Catch `yaml.YAMLError` and return
`{"source": source, "reason": "YAML content is invalid"}`. Validate the root
mapping and dependencies list with the fixed sanitized reasons from the design.

- [ ] **Step 3: Parse Conda and pip dependency entries**

Parse string Conda entries into normalized `name`, `version_spec`, and `source`.
Strip a channel prefix for normalization. Parse only static strings from a
`{"pip": [...]}` mapping and mark their source as `<file>:pip`. Never follow
URLs, selectors, or commands.

- [ ] **Step 4: Aggregate Python, framework, CUDA, and evidence**

Apply exact/min/max operators from the `python` dependency. Detect only approved
framework package names. Extract CUDA only from `cudatoolkit`, `cuda`, or
`pytorch-cuda`. Set package manager to `conda` after a valid document and record
source-bearing evidence.

- [ ] **Step 5: Run targeted tests until green**

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe -m pytest tests\test_conda_parser.py -q --basetemp=.conda-parser-target-temp -p no:cacheprovider
```

Expected: all new tests pass with no skip or warning.

### Task 4: Full Regression and Scope Check

**Files:**
- Verify only

- [ ] **Step 1: Run the complete backend test suite**

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.conda-parser-full-temp -p no:cacheprovider
```

Expected: all tests pass with no failure, skip, or warning.

- [ ] **Step 2: Scan the parser for prohibited operations**

Confirm the parser contains no subprocess, command execution, `yaml.load`, LLM,
machine detection, compatibility score, or frontend/API changes. No Git commit
is created because the project currently does not require commits.
