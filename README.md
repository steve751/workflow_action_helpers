# steves-workflow-helpers

Helpers and custom step types for the DataHub workflow actions engine (`datahub-workflow-actions`).
Installing this package adds its step types to the engine's step catalog, so rules can use them in
`steps[].type` like the built-in ones.

| Step type | What it does |
| --- | --- |
| `log_message` | Writes a message to the engine log. Also the template for new step types. |

## Layout

```text
src/steves_workflow_helpers/
  __init__.py          registers every step on import (runs at interpreter start via a .pth file)
  engine.py            load_engine(): the engine's step API, or None when the engine is absent
  workflow.py          other_workflow_skip(): honour an optional workflow_urn param
  graph.py             run_graphql(): GraphQL call with errors that name the operation
  actions/
    __init__.py        REGISTRARS: add each new step's register function here
    log_message.py     example step
scripts/build_zip.py   builds dist/steves-workflow-helpers-<version>.zip
```

## Add a new step type

1. Copy `actions/log_message.py` to `actions/<your_step>.py`. Keep the logic in a plain function and put the
   engine wiring (params class, `@engine.step(...)`) in `register(engine)`.
2. Append `<your_step>.register` to `REGISTRARS` in `actions/__init__.py`.
3. Add tests in `tests/` using the `fake_engine` fixture.
4. Bump `version` in `pyproject.toml`, rebuild the zip, commit it.

## Build the zip

```bash
python3 scripts/build_zip.py
```

This writes `dist/steves-workflow-helpers-<version>.zip`. The zip holds one top-level directory with
`pyproject.toml`, `setup.py`, `README.md` and `src/`, which is what pip needs to build and install it.
`setup.py` adds a `.pth` file to the built wheel; that file imports the package at interpreter start, which
is what registers the steps with the engine.

## Install on the engine

On the engine ingestion source, set **Extra Pip Libraries** to the engine plus this zip:

```json
[
  "https://github.com/brock-acryl/datahub-workflow-actions/archive/main.zip",
  "https://github.com/<owner>/steves-workflow-action-helpers/raw/refs/heads/main/dist/steves-workflow-helpers-0.1.0.zip"
]
```

Save the source and run it once so the executor builds a fresh virtualenv. A step failure message lists
the known step types; `log_message` should be among them.

The pip name `steves-workflow-helpers` and Python package `steves_workflow_helpers` must stay different
from the engine's `datahub-workflow-actions` / `datahub_workflow_actions`; two entries resolving to the same
pip name fail with a conflicting-URLs error.

## Develop

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

Example rule:

```json
{
  "id": "log-on-approval",
  "name": "Log when approved",
  "enabled": true,
  "on": { "operation": "COMPLETED", "result": "ACCEPTED" },
  "steps": [
    {
      "id": "log",
      "type": "log_message",
      "params": { "message": "{{ requester.urn }} was approved", "level": "info" }
    }
  ]
}
```
