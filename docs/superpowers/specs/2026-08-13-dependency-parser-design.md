# Python Dependency Parser Design

## Scope

Create `backend/compatibility/dependency_parser.py` to statically parse Python
dependency and interpreter requirements from the plain-text files returned by
`repository_environment_fetcher.py`. The parser does not read README,
Dockerfile, or Conda environment files. It does not execute Python, install
packages, call an LLM, or compare requirements with the local machine.

## Input and Output

The public function is:

```python
parse_python_dependencies(environment_files: dict[str, object]) -> dict[str, object]
```

It accepts the environment fetcher's result, using only entries in its `files`
mapping. Missing files are normal.

The result contains:

- `python_min_version`: lower Python boundary or `None`
- `python_max_version`: upper Python boundary or `None`
- `python_exact_version`: explicit exact Python version or `None`
- `framework`: `PyTorch`, `TensorFlow`, `JAX`, or `None`
- `framework_version`: the selected framework dependency's version specifier or
  `None`
- `package_manager`: `pip`, `pipenv`, or `None`
- `dependencies`: ordered, de-duplicated dependency records
- `evidence`: records describing the source file and extracted fact
- `errors`: sanitized per-file parsing errors

Each dependency record has:

```json
{
  "name": "torch",
  "version_spec": ">=2.1,<2.5",
  "source": "requirements.txt"
}
```

Dependencies are de-duplicated case-insensitively by normalized package name,
version specifier, and source. Environment markers and extras remain part of the
static dependency information when they are present, but no marker is evaluated.

## File Parsers

### requirements.txt

Read lines as text. Ignore blank lines and full-line comments. Parse ordinary
PEP 508-style package requirements, including version specifiers and extras.
Unsupported directives such as `-r`, `--index-url`, editable installs, URLs,
and local paths are not executed or followed; they are recorded as evidence or
ignored safely rather than treated as packages.

### pyproject.toml

Parse with Python 3.12 standard-library `tomllib`. Read:

- `[project].requires-python`
- `[project].dependencies`
- Poetry's `[tool.poetry.dependencies]`, including the special `python` entry

Malformed TOML adds a sanitized `pyproject.toml` error and does not stop other
files.

### setup.cfg

Parse with standard-library `configparser`. Read `python_requires` and multiline
`install_requires` from `[options]`. No plugin or interpolation code is run.

### setup.py

Parse with standard-library `ast` only. Inspect literal keyword arguments passed
to a function named `setup`: `python_requires` and `install_requires`.
`ast.literal_eval` is allowed only for literal strings, lists, and tuples. Names,
function calls, comprehensions, imports, and computed values are never evaluated.
Syntax errors or dynamic expressions produce sanitized errors/evidence and do not
execute code.

### Pipfile

Parse with `tomllib`. Read `[requires].python_version` or
`python_full_version`, plus package names and static string versions from
`[packages]` and `[dev-packages]`. Complex package tables may expose a static
`version` string; other keys are not acted upon.

### runtime.txt and .python-version

Recognize explicit versions such as `python-3.11.8` and `3.10.13`. These set
`python_exact_version`. Values without a complete numeric version are not
invented or expanded.

## Python Version Rules

Version constraints are extracted without using them to install or select an
interpreter:

- `==3.10.13` sets `python_exact_version`.
- `>=3.9` or `>3.9` sets `python_min_version` to the stated boundary text.
- `<3.12` or `<=3.12` sets `python_max_version` to the stated boundary text.
- compatible-release constraints such as `~=3.10` set the minimum to `3.10`;
  the parser does not manufacture an unstated maximum.
- `.python-version`, then `runtime.txt`, provide explicit-version evidence. If
  both exist and disagree, `.python-version` takes precedence and the conflict
  is recorded in evidence.
- Exact versions from these dedicated files take precedence over range metadata;
  range fields may still be retained when independently declared.

The parser stores normalized numeric version strings in the three version
fields and keeps operators and original constraints in evidence.

## Framework Detection

Framework detection uses normalized dependency names only:

- `torch`, `torchvision`, `torchaudio` -> `PyTorch`
- `tensorflow` and its explicitly named distribution variants -> `TensorFlow`
- `jax`, `jaxlib` -> `JAX`

No framework is inferred from repository names, arbitrary text, comments, or
missing dependencies. When more than one framework family is present, the first
family encountered according to file priority is returned and all detected
framework dependencies remain in evidence. File priority is:

1. `requirements.txt`
2. `pyproject.toml`
3. `setup.cfg`
4. `setup.py`
5. `Pipfile`

The framework version is the version specifier on the dependency that first
establishes the selected framework. A companion package such as `torchvision`
may establish PyTorch only when `torch` itself is absent.

## Package Manager Detection

- `Pipfile` alone -> `pipenv`
- any of `requirements.txt`, `pyproject.toml`, `setup.cfg`, or `setup.py` ->
  `pip`
- when pip and Pipfile sources coexist, `pip` takes precedence because it is the
  higher-priority parsed source
- no recognized dependency source -> `None`

This field describes the detected manifest style only; no command is run.

## Evidence and Error Isolation

Evidence is a list of dictionaries containing `source`, `field`, and `value`.
Every extracted Python constraint, dependency, framework decision, and package
manager decision records its source. Error entries contain only `source` and a
fixed, sanitized `reason`; raw source text and exception representations are not
returned.

Malformed content in one file cannot prevent parsing the others. Unexpected
input types are recorded as errors. Missing `files` or missing supported entries
returns null fields, empty dependencies/evidence, and no crash.

## Testing

Unit tests use in-memory fetcher-style dictionaries and cover:

- ordinary `requirements.txt` dependencies
- versioned `requirements.txt` dependencies
- `pyproject.toml` Python requirements
- `pyproject.toml` dependencies
- `setup.cfg`
- `.python-version`
- `runtime.txt`
- PyTorch detection
- TensorFlow detection
- JAX detection
- malformed file content
- missing fields

Additional assertions verify that `setup.py` is parsed through AST without
execution and that sources are retained in dependency/evidence records. After
targeted tests pass, the complete backend test suite is run.
