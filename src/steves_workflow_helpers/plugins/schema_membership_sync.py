"""DataHub Action: keep a data product's datasets in step with the schemas it contains.

When a schema (or any container whose subtype is listed in ``schema_subtypes``) is added to a data
product, every dataset inside it is added too. When the schema is removed, those datasets are removed.

Recipe::

    name: data_product_schema_sync
    source:
      type: datahub-cloud
      config:
        topics: ["MetadataChangeLog_Versioned_v1"]
    filter:
      event_type: MetadataChangeLogEvent_v1
      event:
        entityType: dataProduct
        aspectName: dataProductProperties
    action:
      type: schema_membership_sync        # or steves_workflow_helpers.plugins.schema_membership_sync:SchemaMembershipSyncAction
      config:
        schema_subtypes: ["Schema"]
        dry_run: true

The action's own writes re-emit ``dataProductProperties`` change logs. Those only add or remove
datasets, which are not containers, so the second pass finds nothing to do and the loop ends.
"""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional, Set

from pydantic import Field

from datahub.configuration.common import ConfigModel
from datahub.metadata.schema_classes import (
    DataProductPropertiesClass,
    GenericAspectClass,
    MetadataChangeLogClass,
    SubTypesClass,
)
from datahub.specific.dataproduct import DataProductPatchBuilder
from datahub_actions.action.action import Action
from datahub_actions.event.event_envelope import EventEnvelope
from datahub_actions.event.event_registry import METADATA_CHANGE_LOG_EVENT_V1_TYPE
from datahub_actions.pipeline.pipeline_context import PipelineContext

logger = logging.getLogger(__name__)

CONTAINER_URN_PREFIX = "urn:li:container:"


class SchemaMembershipSyncConfig(ConfigModel):
    schema_subtypes: List[str] = Field(
        default=["Schema"],
        description=(
            "Container subtypes that count as a schema. Platforms label their schema level "
            "differently, so list every label that should expand. Add 'Database' to expand "
            "databases too."
        ),
    )
    batch_size: int = Field(
        default=200, gt=0, description="Assets added or removed per emitted patch."
    )
    dry_run: bool = Field(
        default=False, description="Log what would change without writing anything."
    )


def asset_urns(aspect: Optional[GenericAspectClass]) -> Set[str]:
    """The asset URNs in a serialized ``dataProductProperties`` aspect; empty when there is none."""
    if aspect is None:
        return set()
    properties = DataProductPropertiesClass.from_obj(json.loads(aspect.value))
    return {asset.destinationUrn for asset in properties.assets or []}


class SchemaMembershipSyncAction(Action):
    def __init__(self, config: SchemaMembershipSyncConfig, ctx: PipelineContext) -> None:
        self.config = config
        if ctx.graph is None:
            raise ValueError("schema_membership_sync needs a DataHub connection (`datahub:` block)")
        self.graph: Any = ctx.graph.graph

    @classmethod
    def create(cls, config_dict: dict, ctx: PipelineContext) -> "SchemaMembershipSyncAction":
        return cls(SchemaMembershipSyncConfig.model_validate(config_dict or {}), ctx)

    def act(self, event: EventEnvelope) -> None:
        if event.event_type != METADATA_CHANGE_LOG_EVENT_V1_TYPE:
            return
        mcl = event.event
        if not isinstance(mcl, MetadataChangeLogClass):
            return
        if mcl.entityType != "dataProduct" or mcl.aspectName != "dataProductProperties":
            return
        if mcl.aspect is None or mcl.entityUrn is None:
            return

        product_urn = mcl.entityUrn
        current = asset_urns(mcl.aspect)
        previous = asset_urns(mcl.previousAspectValue)

        for schema_urn in sorted(self._schemas(current - previous)):
            datasets = self._datasets_in(schema_urn)
            self._apply(product_urn, datasets - current, add=True, schema_urn=schema_urn)

        removed = self._schemas(previous - current)
        if removed:
            # A dataset stays if another schema still in the product covers it, e.g. a database
            # and one of its schemas are both members and only the schema was removed.
            covered: Set[str] = set()
            for schema_urn in self._schemas(current):
                covered |= self._datasets_in(schema_urn)
            for schema_urn in sorted(removed):
                datasets = self._datasets_in(schema_urn)
                self._apply(
                    product_urn,
                    (datasets & current) - covered,
                    add=False,
                    schema_urn=schema_urn,
                )

    def _schemas(self, urns: Set[str]) -> Set[str]:
        wanted = {name.lower() for name in self.config.schema_subtypes}
        schemas: Set[str] = set()
        for urn in urns:
            if not urn.startswith(CONTAINER_URN_PREFIX):
                continue
            subtypes = self.graph.get_aspect(urn, SubTypesClass)
            if subtypes and wanted & {name.lower() for name in subtypes.typeNames}:
                schemas.add(urn)
            else:
                logger.debug("Skipping container %s: not a schema", urn)
        return schemas

    def _datasets_in(self, schema_urn: str) -> Set[str]:
        # container= matches through browsePathV2, so datasets in nested containers are included.
        return set(self.graph.get_urns_by_filter(entity_types=["dataset"], container=schema_urn))

    def _apply(self, product_urn: str, urns: Set[str], *, add: bool, schema_urn: str) -> None:
        if not urns:
            return
        verb = "add" if add else "remove"
        logger.info(
            "%s%s %d datasets for schema %s on %s",
            "[dry run] " if self.config.dry_run else "",
            verb,
            len(urns),
            schema_urn,
            product_urn,
        )
        if self.config.dry_run:
            return
        ordered = sorted(urns)
        for start in range(0, len(ordered), self.config.batch_size):
            builder = DataProductPatchBuilder(product_urn)
            for urn in ordered[start : start + self.config.batch_size]:
                if add:
                    builder.add_asset(urn)
                else:
                    builder.remove_asset(urn)
            self.graph.emit_mcps(builder.build())

    def close(self) -> None:
        pass
