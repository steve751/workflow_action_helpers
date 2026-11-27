# steves-workflow-helpers

Helpers and custom step types for the DataHub workflow actions engine (`datahub-workflow-actions`).
Installing this package adds its step types to the engine's step catalog, so rules can use them in
`steps[].type` like the built-in ones.

| Step type | What it does |
| --- | --- |
| `log_message` | Writes a message to the engine log. Also the template for new step types. |

It also ships standalone `datahub-actions` plugins, which run in a plain Actions pipeline rather than the engine:

| Action type | What it does |
| --- | --- |
| `schema_membership_sync` | When a schema is added to (or removed from) a data product, adds (or removes) every dataset in it. See [Schema membership sync](#schema-membership-sync). |

The same action also runs as an ingestion source, `schema-membership-sync`, so it can run on the executor
next to the engine. See [Run it as an ingestion source](#run-it-as-an-ingestion-source).

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
  plugins/
    schema_membership_sync.py          datahub-actions Action; never imported by the engine steps
    schema_membership_sync_source.py   ingestion source that runs that action as a pipeline
examples/              recipes
scripts/build_zip.py   builds dist/steves-workflow-helpers-<version>.zip
```

## Schema membership sync

`examples/data_product_schema_sync.yaml` is a complete `datahub-actions` recipe. The action listens for
`dataProductProperties` change logs on data products and compares the new asset list with the previous one:

- A container added to the product whose subtype is in `schema_subtypes` has every dataset under it added.
  The search is recursive, so datasets in nested containers count.
- A matching container removed from the product has its datasets removed, except any that another schema still
  in the product covers.
- Other containers (subtype not listed) and non-container assets are ignored.

| Config | Default | Meaning |
| --- | --- | --- |
| `schema_subtypes` | `["Schema"]` | Container subtypes that count as a schema, case-insensitive. Add `"Database"` to expand databases. |
| `batch_size` | `200` | Assets per emitted patch. |
| `dry_run` | `false` | Log what would change and write nothing. |

The action's own writes produce another change log, but that one only adds or removes datasets, so nothing
further happens. Removing a schema also removes datasets in it that someone added to the product by hand.
The pipeline needs a `datahub:` connection (or the executor's) and permission to edit data products.

Use it with `type: schema_membership_sync`, or the full path
`steves_workflow_helpers.plugins.schema_membership_sync:SchemaMembershipSyncAction`. Install this package and
`acryl-datahub-actions` in the environment that runs the pipeline.

### Run it as an ingestion source

`examples/schema_membership_sync_source.yaml` runs the same action from a normal ingestion source, the way the
workflow engine runs. Create an ingestion source with this recipe and put this package's zip in **Extra Pip
Libraries** (the executor already has `acryl-datahub-actions`):

```yaml
source:
  type: schema-membership-sync
  config:
    schema_subtypes: ["Schema"]
    dry_run: true
    pipeline_name: schema-membership-sync
```

The source polls the Events API (the engine's transport) for `MetadataChangeLog_Versioned_v1`, handles
`dataProductProperties` changes, and runs until stopped. It uses the ingestion run's DataHub connection. It takes the
same `schema_subtypes`, `batch_size` and `dry_run` as the action, plus `pipeline_name` (the name the Events API
stores its read position under; keep it stable and unique per running copy) and `cloud_events` (overrides such as
`lookback_days` for the event source). Run it once with `dry_run: true` and read the log for
`[dry run] add N datasets for schema ...`, then set it to `false`.

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
  "https://github.com/steve751/workflow_action_helpers/raw/refs/heads/main/dist/steves-workflow-helpers-0.3.3.zip"
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
