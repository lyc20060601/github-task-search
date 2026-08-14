# Python Dependency Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Statically extract Python versions, dependencies, package manager, and PyTorch/TensorFlow/JAX framework facts from fetched repository environment files.

**Architecture:** A single compatibility parser consumes the existing fetcher's `files` mapping and dispatches only allow-listed filenames to standard-library parsers. Each parser returns dependency records and version constraints; a deterministic aggregation pass de-duplicates records, applies explicit source precedence, detects frameworks from package names only, and emits evidence plus sanitized errors.

**Tech Stack:** Python 3.12, `tomllib`, `configparser`, `ast`, `re`, pytest

---

### Task 1: Specify Static Parsing Behavior in Tests

**Files:**
- Create: `backend/tests/test_dependency_parser.py`

- [ ] **Step 1: Add fetcher-style test input helper**

Build dictionaries shaped as:

```python
{"files": {name: {"content": content, "size": len(content), "truncated": False}}}
```

- [ ] **Step 2: Add required manifest and version tests**

Add separate tests for ordinary and versioned requirements, PEP 621
`pyproject.toml` Python/dependency fields, `setup.cfg`, `.python-version`, and
`runtime.txt`. Assert structured dependency records with `name`,
`version_spec`, and `source`.

- [ ] **Step 3: Add framework tests**

Use dependency manifests to independently assert PyTorch, TensorFlow, and JAX
detection plus framework version extraction. Do not put framework names in
repository metadata or arbitrary text.

- [ ] **Step 4: Add safety and resilience tests**

Test malformed TOML alongside a valid requirements file, missing `files`, and a
`setup.py` containing a side-effect call plus literal `setup(...)` metadata.
Patch execution-related builtins so any attempt to execute the source fails the
test. Assert source-bearing evidence and sanitized errors.

- [ ] **Step 5: Verify the new suite is red**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe -m pytest tests\test_dependency_parser.py -q --basetemp=.dependency-parser-red-temp -p no:cacheprovider
```

Expected: collection fails because `compatibility.dependency_parser` does not
exist.

### Task 2: Implement Safe File-Specific Parsers

**Files:**
- Create: `backend/compatibility/dependency_parser.py`

- [ ] **Step 1: Implement input extraction and result skeleton**

Accept only dictionary `files` entries whose allow-listed path maps to a
dictionary containing string `content`. Record invalid supported entries as
`{"source": path, "reason": "file content is invalid"}`. Initialize all
scalar fields to `None` and collection fields to empty lists.

- [ ] **Step 2: Implement dependency string parsing**

Use a conservative regular expression to split a static PEP 508-like string
into normalized package `name` and its remaining version/marker text. Reject
directives, URLs, local paths, and empty/comment lines without following them.
Preserve version specifiers such as `==2.4.0` and `>=2.1,<2.5`.

- [ ] **Step 3: Implement requirements, TOML, and CFG parsers**

Parse `requirements.txt` line-by-line, `pyproject.toml` and `Pipfile` with
`tomllib.loads`, and `setup.cfg` with `configparser.ConfigParser(interpolation=None)`.
Extract only the approved static fields. Catch `TOMLDecodeError`,
`configparser.Error`, `TypeError`, and `ValueError` per file and append fixed
sanitized reasons.

- [ ] **Step 4: Implement setup.py AST parsing**

Use `ast.parse` to find calls whose function is `setup` or an attribute ending
in `.setup`. For keyword values `python_requires` and `install_requires`, use
`ast.literal_eval` and accept only a string or a list/tuple of strings. Never
compile or execute the AST. Record a sanitized error when syntax is invalid;
ignore dynamic expressions safely.

- [ ] **Step 5: Implement explicit Python version extraction**

Recognize only numeric versions with two or three components. Parse `==`,
`>=`, `>`, `<`, `<=`, and `~=` constraints into exact/min/max fields while
recording the original constraint in evidence. Apply `.python-version` before
`runtime.txt`, then manifest ranges.

### Task 3: Aggregate Framework and Evidence Results

**Files:**
- Modify: `backend/compatibility/dependency_parser.py`

- [ ] **Step 1: De-duplicate dependencies deterministically**

Preserve file priority and line order. De-duplicate by case-folded normalized
name, version specifier, and source.

- [ ] **Step 2: Detect package manager and framework**

Return `pip` when a pip-style manifest exists, otherwise `pipenv` for Pipfile.
Map only dependency names from the approved families to PyTorch, TensorFlow, or
JAX. Set framework version from the establishing dependency's version specifier.

- [ ] **Step 3: Record evidence**

For each extracted Python requirement, dependency, framework selection, and
package-manager selection, add `source`, `field`, and `value`. Do not return raw
file contents or exception representations.

- [ ] **Step 4: Run targeted tests until green**

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe -m pytest tests\test_dependency_parser.py -q --basetemp=.dependency-parser-target-temp -p no:cacheprovider
```

Expected: every new test passes with no skipped tests or warnings.

### Task 4: Full Backend Regression

**Files:**
- Verify only

- [ ] **Step 1: Run all backend tests**

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.dependency-parser-full-temp -p no:cacheprovider
```

Expected: all backend tests pass with no failures, skips, or warnings.

- [ ] **Step 2: Check scope**

Verify that no frontend, endpoint, runtime validation, compatibility comparison,
or existing core model was modified. No Git commit is created because the
project currently does not require commits.
