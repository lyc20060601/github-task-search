# Conda Environment Parser Design

## Scope

Create `backend/compatibility/conda_parser.py` to statically parse Conda
environment configuration from the plain-text `environment.yml` or
`environment.yaml` entry returned by the repository environment fetcher. The
parser never runs Conda, pip, Python, shell commands, repository code, or local
machine detection.

An independent module is used because `dependency_parser.py` already owns Python
packaging manifests, while Conda YAML has a distinct nested data model and an
additional CUDA result.

## YAML Safety

Add a pinned PyYAML dependency to `backend/requirements.txt` and parse only with
`yaml.safe_load()`. Never use `yaml.load()`, object constructors, or custom YAML
tags. The parser accepts only the expected scalar, list, and mapping structures
from the loaded document. Invalid YAML and unexpected structures return
sanitized errors rather than raising an unhandled exception.

## Input and File Selection

The public function is:

```python
parse_conda_environment(environment_files: dict[str, object]) -> dict[str, object]
```

The input uses the fetcher's `files` mapping. `environment.yml` has priority;
`environment.yaml` is used only when the former has no valid text entry. Other
files are ignored.

## Output

The result contains:

- `environment_name`: the top-level string `name`, or `None`
- `python_min_version`: explicit lower boundary, or `None`
- `python_max_version`: explicit upper boundary, or `None`
- `python_exact_version`: explicit equality/pin, or `None`
- `framework`: `PyTorch`, `TensorFlow`, `JAX`, or `None`
- `framework_version`: version text from the dependency establishing the
  selected framework, or `None`
- `cuda_version`: version text explicitly attached to `cudatoolkit`, `cuda`, or
  `pytorch-cuda`, or `None`
- `package_manager`: `conda` whenever a valid Conda document is parsed
- `dependencies`: ordered structured dependency records
- `evidence`: source-bearing extracted facts
- `errors`: sanitized parse or structure errors

Dependency records have:

```json
{
  "name": "pytorch",
  "version_spec": "=2.1",
  "source": "environment.yml"
}
```

Nested pip records use source `environment.yml:pip` or
`environment.yaml:pip`.

## Dependency Parsing

Read only the top-level `dependencies` list:

- String entries such as `python=3.10`, `pytorch=2.1`, `torchvision`, and
  `cudatoolkit=11.8` become Conda dependency records.
- Optional channel prefixes such as `pytorch::pytorch=2.1` are stripped from the
  normalized package name but preserved in evidence.
- Build suffixes after a second equality separator are retained in the raw
  evidence but are not interpreted.
- A mapping with key `pip` must contain a list. Static string items are parsed as
  Python package requirements and receive the `:pip` source.
- Other mappings, nested values, URLs, selectors, and non-string entries are not
  executed or followed. Unsupported values are skipped safely.

Dependencies are de-duplicated by normalized package name, version text, and
source while preserving document order.

## Version Rules

For the `python` dependency:

- `python=3.10` or `python==3.10` sets `python_exact_version` to `3.10`.
- `python>=3.9` sets `python_min_version` to `3.9`.
- `python<3.12` sets `python_max_version` to `3.12`.
- A comma-separated constraint may set both boundaries.
- No unstated boundary is inferred.

The parser retains operators and the original dependency in evidence. It does
not expand `3.10` into a patch version.

## Framework and CUDA Rules

Framework detection uses normalized dependency names only:

- `pytorch`, `torch`, `torchvision`, `torchaudio` -> `PyTorch`
- `tensorflow`, `tensorflow-cpu`, `tensorflow-gpu` -> `TensorFlow`
- `jax`, `jaxlib` -> `JAX`

The first framework dependency in document order determines `framework` and
`framework_version`. Nested pip packages participate in the same detection.
Repository name, environment name, channel, comments, and arbitrary strings do
not determine the framework.

CUDA extraction recognizes only explicit `cudatoolkit`, `cuda`, and
`pytorch-cuda` dependencies. It returns the attached version text without using
it to infer `gpu_required`, CUDA necessity, GPU model, or GPU memory.

## Evidence and Errors

Evidence entries contain `source`, `field`, and `value`. Evidence is recorded
for environment name, Python constraints, every accepted dependency, framework,
CUDA version, and package manager.

Errors contain only `source` and a fixed reason. Invalid YAML returns
`YAML content is invalid`; a valid YAML root that is not a mapping returns
`Conda environment root must be a mapping`; a non-list `dependencies` value
returns `Conda dependencies must be a list`. Raw file contents and exception
representations are never returned.

Missing environment files return null scalar fields, empty collections, and no
exception.

## Testing

Tests use in-memory fetcher-shaped dictionaries and cover:

- `environment.yml`
- `environment.yaml` fallback
- exact and bounded Python versions
- PyTorch detection
- explicit CUDA Toolkit extraction
- nested pip dependencies
- missing `name`
- missing Python dependency
- invalid YAML safe failure

Additional assertions verify TensorFlow/JAX mapping, evidence sources, file
priority, and that no command execution API appears in the parser. After
targeted tests pass, the complete backend suite must pass.
