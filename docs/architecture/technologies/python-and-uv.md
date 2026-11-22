# Python and uv

## What it is

**Python** is the language of the reasoner, the command line, the API server and the pipeline. **uv** is a fast tool, written in Rust, that installs Python itself, resolves and installs dependencies, keeps a lockfile, and runs commands in the project's environment. It replaces pip, venv, pip-tools and pyenv in one tool.

## How it works

**Packages and `pyproject.toml`.** A Python package is a directory of modules with a `pyproject.toml` describing it: its name, version, dependencies, the command-line scripts it installs, and the *build backend* that turns it into an installable *wheel* (we use Hatchling). Dependencies are ranges (`fastapi>=0.110`) so that packages can share a resolver's choice.

**Virtual environments.** Each project gets its own isolated set of installed packages, the `.venv/` directory, so projects don't fight over versions. `uv run <command>` runs a command inside it without activating anything.

**The lockfile.** `uv.lock` records the exact version and hash of every package, direct and transitive, for every platform. `uv sync` makes `.venv/` match it exactly, so every machine and CI run gets the same versions. `uv sync --locked` fails instead of updating the lockfile if `pyproject.toml` changed without it: CI uses this to catch a forgotten lock update.

**Workspaces.** A workspace is several packages in one repository that share one lockfile and one environment. The root `pyproject.toml` lists the members. Members depend on each other with `{ workspace = true }` sources, and are installed in *editable* mode: Python imports them straight from their source directories, so edits take effect without reinstalling. Our root is a *virtual* workspace: it holds no package itself, and `uv sync` installs every member.

## How we use it

Three packages, one per responsibility ([ADR 0033](../../adr/0033-build-a-python-data-platform-around-the-graph.md)):

| Package | Import name | Contains | Depends on |
|---|---|---|---|
| `packages/core` | `capabilities` | Graph, reasoner, validator, CLI | PyYAML, jsonschema, DuckDB |
| `packages/api` | `capabilities_api` | The FastAPI server | core, FastAPI, Uvicorn |
| `pipeline` | `capabilities_pipeline` | The build | core, dbt Core, dbt-duckdb |

Why split them: the dependencies differ a lot (dbt is large), each part can be tested and reasoned about alone, and the boundaries match how the platform will grow, with Dagster and other services joining the pipeline. The core never imports the pipeline at the top of a module. It does so only inside `run_build`, so the core still works if installed alone.

We use Python 3.12 and type hints throughout. Tests use pytest; they live beside each package and share fixtures from the root `conftest.py`. Pytest runs in `importlib` mode, so test files in different packages can share names without `__init__.py` files.

## Where it lives

| What | Where |
|---|---|
| Workspace members, pytest settings, dev dependencies | `pyproject.toml` |
| Each package's metadata and dependencies | `packages/core/pyproject.toml`, `packages/api/pyproject.toml`, `pipeline/pyproject.toml` |
| Exact versions | `uv.lock` |
| Shared test fixtures | `conftest.py` |

```bash
uv sync                  # install everything, exactly as locked
uv run pytest            # all tests
uv run capabilities ...  # the CLI (installed by packages/core as a script)
uv add --package capabilities-api httpx   # add a dependency to one member
uv lock --upgrade-package duckdb          # move one dependency to its newest allowed version
```

## Things to know

- Change dependencies with `uv add` or by editing `pyproject.toml` and running `uv lock`, then commit `uv.lock`.
- Check a new dependency's license before adding it ([ADR 0037](../../adr/0037-license-the-project-for-non-commercial-use-only.md)), and add it to [CREDITS.md](../../../CREDITS.md).
- `find_root()` finds the repository by looking for `schema/` and `data/`, first upward from where the command runs, then upward from the installed package. `CAPABILITIES_ROOT` overrides both.

## Further reading

1. [uv documentation](https://docs.astral.sh/uv/): start with "Getting started", then "Projects".
2. [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/): members, workspace sources, virtual roots.
3. [Writing your pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) (Python Packaging User Guide).
4. [Using uv in GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/).
