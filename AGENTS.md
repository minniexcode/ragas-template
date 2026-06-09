# Repository Guidelines

## Project Structure & Module Organization
`rag_eval/` contains the core platform code: `config/` loads YAML scenarios, `datasets/` normalizes input records, `metrics/` builds the RAGAS pipeline, `execution/` runs evaluations, and `reporting/` writes run artifacts. Use `main.py` as the primary CLI entrypoint. Keep sample integrations in `apps/` and scenario definitions in `scenarios/`. Store source datasets under `datasets/raw/` or `datasets/normalized/`, architecture notes in `docs/`, generated outputs in `outputs/`, and automated checks in `tests/`.

## Build, Test, and Development Commands
Set up the environment with `uv sync`, then copy `Copy-Item .env.example .env` and fill in the required OpenAI settings.

Run the standard offline sample with:
```powershell
.\.venv\Scripts\python.exe main.py --scenario scenarios/offline/sample-offline.yaml
```

Run tests with:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## Coding Style & Naming Conventions
Target Python 3.12+ and follow PEP 8 with 4-space indentation. Prefer type hints on public functions and keep modules focused on one responsibility. Every Python file should include function comments for each function and concise code comments for non-obvious logic blocks. Use `snake_case` for files, functions, variables, and YAML filenames; use `PascalCase` for classes such as `EvaluationSettings` or `MetricPipeline`. Keep adapters small and return a normalized shape: `answer`, `contexts`, and optional `raw_response`.

## Testing Guidelines
Tests currently use the standard `unittest` framework. Add new coverage under `tests/` with names matching `test_*.py`, and mirror the production module or workflow being exercised. Favor deterministic tests with mocked external calls; do not rely on live model APIs in CI-style checks. For run-artifact tests, write only to temporary directories under `tests/.tmp/`.

## Commit & Pull Request Guidelines
The current history starts with short, imperative subjects (`initial commit`); continue using concise commit lines such as `Add HTTP adapter validation`. Keep each commit scoped to one logical change. Pull requests should describe the scenario impacted, summarize behavior changes, list test coverage, and include sample output paths or screenshots when reporting artifacts or docs change.

## Configuration & Data Handling
Do not commit real secrets in `.env`. Treat `outputs/` and generated run directories as disposable artifacts unless a result is intentionally curated for review. When adding datasets, prefer sanitized examples and document any required schema fields in the relevant scenario or README.
