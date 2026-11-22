# GitHub Actions

## What it is

GitHub Actions runs automated jobs on GitHub's machines when something happens in a repository, such as a push or a pull request. We use it for continuous integration (CI): every change is checked the same way before it is merged.

## How it works

A **workflow** is a YAML file in `.github/workflows/`. It says **when** to run (`on: pull_request`, `on: push`) and defines **jobs**. Each job runs on a fresh virtual machine (`runs-on: ubuntu-latest`) as a list of **steps**: either a shell command (`run:`) or a reusable **action** (`uses: actions/checkout@v4`). Jobs run in parallel unless one `needs` another. A pull request shows each job as a *check*, passing or failing.

## How we use it

`.github/workflows/ci.yml` runs on every pull request and on every push to `main`, with two jobs:

| Job | Steps |
|---|---|
| `check` (Python) | Install with `uv sync --locked`; `capabilities validate`; `capabilities build` (dbt, with its data tests); `pytest`. |
| `web` | `npm ci`; lint; type-check; Vitest; `npm run build`, which also validates and builds the architecture diagrams. |

`uv sync --locked` and `npm ci` both fail if a lockfile is out of date, so a dependency change can't slip through without its lockfile.

## Where it lives

| What | Where |
|---|---|
| The workflow | `.github/workflows/ci.yml` |
| Node version for CI | `web/.nvmrc` |

## Things to know

- A check that fails in CI but passes locally usually means a missing file in git, an out-of-date lockfile, or a dependency on something outside the repository.
- The Playwright smoke test (milestone M8) will be a third job.

## Further reading

1. [GitHub Actions documentation](https://docs.github.com/en/actions): start with "Understanding GitHub Actions".
2. [Using uv in GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/).
