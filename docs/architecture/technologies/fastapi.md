# FastAPI

## What it is

FastAPI is a Python web framework for building HTTP APIs. You write ordinary functions with type hints; FastAPI turns them into endpoints, validates requests and responses against those types, and generates interactive API documentation automatically. It runs on **Uvicorn**, a server that speaks HTTP, and is built on **Starlette** (the web toolkit underneath) and **Pydantic** (data validation from type hints).

## How it works

**Routes from functions.** A decorator such as `@api.post("/explore")` registers a function for an HTTP method and path. Function parameters come from the path, the query string, or the JSON body, depending on their types.

**Pydantic models.** A request body is a class inheriting from Pydantic's `BaseModel`, with typed fields. FastAPI parses the JSON into it and rejects bad input with a clear 422 error before your code runs.

**OpenAPI.** From the routes and models, FastAPI generates an OpenAPI description of the whole API, and serves interactive documentation from it at `/docs`, where you can try every endpoint in the browser.

**ASGI.** FastAPI apps are ASGI applications, the standard interface between Python async web apps and servers. Uvicorn runs the app and handles the network. Starlette provides routing, static files and the test client.

## How we use it

`packages/api/src/capabilities_api/server.py` creates the app (`create_app`):

- It loads the built graph once at start-up, through `current_graph`, rebuilding first if stale, and computes tech levels.
- JSON endpoints under `/api` answer the three questions and feed the web app: `/api/graph`, `/api/explore`, `/api/explain`, `/api/explain-edge`, `/api/need/{id}`, `/api/check` and more. The [README](../../../README.md) has the full table.
- It hosts the built web app (`web/dist`) at `/`, and with it the architecture diagrams at `/architecture/`.

Why FastAPI: typed request models catch bad input at the edge, the generated docs make the API easy to explore, and it is small and quick to learn ([ADR 0013](../../adr/0013-use-python-for-the-reasoner-cli-and-server.md)).

## Where it lives

| What | Where |
|---|---|
| The app and endpoints | `packages/api/src/capabilities_api/server.py` |
| Tests (Starlette's `TestClient`) | `packages/api/tests/test_server.py` |
| Started by | `uv run capabilities serve` (Uvicorn, port 8000) |

## Things to know

- The graph is loaded at start-up: restart the server after changing data.
- Static files are mounted last, so `/api` and `/docs` keep priority over the web app's files.
- Keep reasoning out of the server: endpoints call the core library and its `views` module, so the CLI and the API give the same answers.

## Further reading

1. [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/): short chapters, from first steps to request bodies and testing.
2. [Pydantic](https://docs.pydantic.dev/latest/): models and validation.
3. [Starlette](https://starlette.dev/) and [Uvicorn](https://uvicorn.dev/): the layers underneath.
