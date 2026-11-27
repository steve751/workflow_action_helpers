"""Ingestion source that runs the ``schema_membership_sync`` action as a long-lived pipeline.

The workflow engine ships as an ingestion source (``datahub-workflow-actions``) that starts a
datahub-actions pipeline in-process. This does the same for ``schema_membership_sync``, so the sync
runs from a normal ingestion source on the executor, with this package in Extra Pip Libraries and
no separate Actions host.

Recipe (see ``examples/schema_membership_sync_source.yaml``)::

    source:
      type: schema-membership-sync
      config:
        schema_subtypes: ["Schema"]
        dry_run: true

The source listens to the Events API (the same transport the engine uses) on the versioned
metadata change log and acts on ``dataProductProperties`` changes. It runs until stopped and emits
no metadata of its own; the datasets it adds are written through the executor's DataHub connection.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Iterable, Optional

from pydantic import Field

from datahub.ingestion.api.source import Source, SourceReport
from datahub_actions.event.event_registry import METADATA_CHANGE_LOG_EVENT_V1_TYPE

from steves_workflow_helpers.plugins.schema_membership_sync import SchemaMembershipSyncConfig

logger = logging.getLogger(__name__)

DEFAULT_PIPELINE_NAME = "schema-membership-sync"
MCL_TOPIC = "MetadataChangeLog_Versioned_v1"
# Expanding a large schema can take a while; the events source aborts the pipeline if an event is
# not acked within this window (default 60 s), so allow the same 15 minutes the engine does.
EVENT_PROCESSING_SECONDS = 15 * 60


class SchemaMembershipSyncSourceConfig(SchemaMembershipSyncConfig):
    pipeline_name: str = Field(
        default=DEFAULT_PIPELINE_NAME,
        description=(
            "datahub-actions pipeline name. The Events API stores its read position under this "
            "name, so keep it stable and unique per running copy."
        ),
    )
    cloud_events: Dict[str, Any] = Field(
        default_factory=dict,
        description="Overrides for the datahub-cloud event source (lookback_days, reset_offsets, ...).",
    )


def ensure_visible_logging() -> None:
    """The datahub CLI drops INFO records from packages it does not own, so give ours a handler once.

    Without this the executor log would not show which datasets the sync added or removed.
    """
    ours = logging.getLogger("steves_workflow_helpers")
    if any(getattr(h, "_steves_workflow_helpers", False) for h in ours.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)-8s {%(name)s} - %(message)s")
    )
    handler._steves_workflow_helpers = True  # type: ignore[attr-defined]
    ours.addHandler(handler)
    ours.setLevel(logging.INFO)
    ours.propagate = False


def datahub_client_config(ctx: Any) -> Optional[Dict[str, Any]]:
    """The DataHub connection for the pipeline: the ingestion run's own graph, else the environment."""
    graph_config = getattr(getattr(ctx, "graph", None), "config", None)
    if graph_config is not None:
        keys = (
            "server",
            "token",
            "timeout_sec",
            "retry_status_codes",
            "retry_max_times",
            "extra_headers",
            "ca_certificate_path",
            "client_certificate_path",
            "disable_ssl_verification",
        )
        found = {key: getattr(graph_config, key, None) for key in keys}
        return {k: v for k, v in found.items() if v not in (None, "", {}, [])}

    server = os.environ.get("DATAHUB_GMS_URL")
    if not server and os.environ.get("DATAHUB_GMS_HOST"):
        protocol = os.environ.get("DATAHUB_GMS_PROTOCOL", "http")
        port = os.environ.get("DATAHUB_GMS_PORT")
        server = f"{protocol}://{os.environ['DATAHUB_GMS_HOST']}" + (f":{port}" if port else "")
    if not server:
        return None
    token = os.environ.get("DATAHUB_GMS_TOKEN")
    return {"server": server, **({"token": token} if token else {})}


def build_pipeline_config(
    config: SchemaMembershipSyncSourceConfig, datahub: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """The datahub-actions pipeline recipe that this source runs."""
    return {
        "name": config.pipeline_name,
        **({"datahub": datahub} if datahub else {}),
        "source": {
            "type": "datahub-cloud",
            "config": {
                "topics": [MCL_TOPIC],
                "event_processing_time_max_duration_seconds": EVENT_PROCESSING_SECONDS,
                **config.cloud_events,
            },
        },
        # The action checks entity type and aspect itself; this only spares it unrelated events.
        "filter": {
            "event_type": METADATA_CHANGE_LOG_EVENT_V1_TYPE,
            "event": {"entityType": "dataProduct", "aspectName": "dataProductProperties"},
        },
        "action": {
            "type": "schema_membership_sync",
            "config": {
                "schema_subtypes": list(config.schema_subtypes),
                "batch_size": config.batch_size,
                "dry_run": config.dry_run,
                "skip_datasets_in_other_products": config.skip_datasets_in_other_products,
            },
        },
    }


class SchemaMembershipSyncSource(Source):
    """Long-running: blocks in ``get_workunits`` while the actions pipeline consumes events."""

    def __init__(self, config: SchemaMembershipSyncSourceConfig, ctx: Any) -> None:
        super().__init__(ctx)
        self.config = config
        self.report = SourceReport()

    @classmethod
    def create(cls, config_dict: dict, ctx: Any) -> "SchemaMembershipSyncSource":
        return cls(SchemaMembershipSyncSourceConfig.model_validate(config_dict or {}), ctx)

    def get_workunits(self) -> Iterable[Any]:
        from datahub_actions.pipeline.pipeline import Pipeline

        ensure_visible_logging()
        datahub = datahub_client_config(getattr(self, "ctx", None))
        if not datahub:
            raise ValueError(
                "schema-membership-sync needs a DataHub connection; none was found on the "
                "ingestion run or in DATAHUB_GMS_URL / DATAHUB_GMS_TOKEN"
            )
        pipeline_config = build_pipeline_config(self.config, datahub)
        logger.info(
            "schema-membership-sync: starting pipeline %s against %s (subtypes=%s, dry_run=%s)",
            self.config.pipeline_name,
            datahub.get("server"),
            self.config.schema_subtypes,
            self.config.dry_run,
        )
        pipeline = Pipeline.create(pipeline_config)
        pipeline.run()  # blocks until stopped
        return iter(())

    def get_report(self) -> SourceReport:
        return self.report

    def close(self) -> None:
        pass
