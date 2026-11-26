from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional

import pytest

pytest.importorskip("datahub_actions")

from datahub.metadata.schema_classes import (  # noqa: E402
    DataProductAssociationClass,
    DataProductPropertiesClass,
    GenericAspectClass,
    MetadataChangeLogClass,
    SubTypesClass,
)
from datahub_actions.event.event_envelope import EventEnvelope  # noqa: E402
from datahub_actions.event.event_registry import (  # noqa: E402
    ENTITY_CHANGE_EVENT_V1_TYPE,
    METADATA_CHANGE_LOG_EVENT_V1_TYPE,
)
from pydantic import ValidationError  # noqa: E402

from steves_workflow_helpers.plugins.schema_membership_sync import (  # noqa: E402
    SchemaMembershipSyncAction,
    SchemaMembershipSyncConfig,
    asset_urns,
)

PRODUCT = "urn:li:dataProduct:sales"
SCHEMA_A = "urn:li:container:schema_a"
SCHEMA_B = "urn:li:container:schema_b"
DATABASE = "urn:li:container:database"
TABLE_CONTAINER = "urn:li:container:not_a_schema"


def ds(name: str) -> str:
    return f"urn:li:dataset:(urn:li:dataPlatform:snowflake,{name},PROD)"


class FakeGraph:
    def __init__(
        self,
        subtypes: Dict[str, List[str]],
        contents: Dict[str, List[str]],
    ) -> None:
        self.subtypes = subtypes
        self.contents = contents
        self.emitted: List[Any] = []

    def get_aspect(self, urn: str, aspect_type: type) -> Optional[SubTypesClass]:
        assert aspect_type is SubTypesClass
        names = self.subtypes.get(urn)
        return SubTypesClass(typeNames=names) if names is not None else None

    def get_urns_by_filter(self, *, entity_types: Any, container: str) -> Iterable[str]:
        assert list(entity_types) == ["dataset"]
        return iter(self.contents.get(container, []))

    def emit_mcps(self, mcps: Iterable[Any]) -> None:
        self.emitted.extend(mcps)

    def ops(self) -> List[Dict[str, Any]]:
        """Every JSON-patch operation emitted so far, in order."""
        result: List[Dict[str, Any]] = []
        for mcp in self.emitted:
            assert mcp.entityUrn == PRODUCT
            assert mcp.aspectName == "dataProductProperties"
            result.extend(json.loads(mcp.aspect.value))
        return result

    def changed(self, op: str) -> List[str]:
        return [o["path"].rsplit("/", 1)[-1] for o in self.ops() if o["op"] == op]


def make_graph() -> FakeGraph:
    return FakeGraph(
        subtypes={
            SCHEMA_A: ["Schema"],
            SCHEMA_B: ["schema"],
            DATABASE: ["Database"],
            TABLE_CONTAINER: ["Folder"],
        },
        contents={
            SCHEMA_A: [ds("db.a.t1"), ds("db.a.t2")],
            SCHEMA_B: [ds("db.b.t1")],
            DATABASE: [ds("db.a.t1"), ds("db.a.t2"), ds("db.b.t1")],
            TABLE_CONTAINER: [ds("misc.t1")],
        },
    )


def make_action(graph: FakeGraph, **config: Any) -> SchemaMembershipSyncAction:
    ctx = SimpleNamespace(graph=SimpleNamespace(graph=graph))
    return SchemaMembershipSyncAction.create(config, ctx)  # type: ignore[arg-type]


def aspect(urns: Iterable[str]) -> GenericAspectClass:
    props = DataProductPropertiesClass(
        name="Sales", assets=[DataProductAssociationClass(destinationUrn=u) for u in urns]
    )
    return GenericAspectClass(
        value=json.dumps(props.to_obj()).encode(), contentType="application/json"
    )


def mcl_event(
    current: Optional[Iterable[str]],
    previous: Optional[Iterable[str]] = None,
    *,
    entity_type: str = "dataProduct",
    aspect_name: str = "dataProductProperties",
) -> EventEnvelope:
    mcl = MetadataChangeLogClass(
        entityType=entity_type,
        entityUrn=PRODUCT,
        changeType="UPSERT",
        aspectName=aspect_name,
        aspect=aspect(current) if current is not None else None,
        previousAspectValue=aspect(previous) if previous is not None else None,
    )
    return EventEnvelope(METADATA_CHANGE_LOG_EVENT_V1_TYPE, mcl, {})


def test_asset_urns_handles_missing_aspect() -> None:
    assert asset_urns(None) == set()
    assert asset_urns(aspect([SCHEMA_A, ds("x")])) == {SCHEMA_A, ds("x")}


def test_adding_a_schema_adds_its_datasets() -> None:
    graph = make_graph()
    make_action(graph).act(mcl_event([SCHEMA_A], previous=[]))
    assert sorted(graph.changed("add")) == sorted([ds("db.a.t1"), ds("db.a.t2")])
    assert graph.changed("remove") == []


def test_first_write_with_no_previous_aspect_counts_everything_as_added() -> None:
    graph = make_graph()
    make_action(graph).act(mcl_event([SCHEMA_B], previous=None))
    assert graph.changed("add") == [ds("db.b.t1")]


def test_datasets_already_in_the_product_are_not_re_added() -> None:
    graph = make_graph()
    make_action(graph).act(mcl_event([SCHEMA_A, ds("db.a.t1")], previous=[ds("db.a.t1")]))
    assert graph.changed("add") == [ds("db.a.t2")]


def test_subtype_match_is_case_insensitive() -> None:
    graph = make_graph()
    make_action(graph).act(mcl_event([SCHEMA_B], previous=[]))
    assert graph.changed("add") == [ds("db.b.t1")]


def test_containers_with_other_subtypes_are_ignored() -> None:
    graph = make_graph()
    make_action(graph).act(mcl_event([TABLE_CONTAINER, DATABASE], previous=[]))
    assert graph.emitted == []


def test_database_expands_only_when_its_subtype_is_configured() -> None:
    graph = make_graph()
    make_action(graph, schema_subtypes=["Schema", "Database"]).act(
        mcl_event([DATABASE], previous=[])
    )
    assert len(graph.changed("add")) == 3


def test_removing_a_schema_removes_its_datasets() -> None:
    graph = make_graph()
    current = [ds("db.a.t1"), ds("db.a.t2"), ds("db.b.t1")]
    make_action(graph).act(mcl_event(current, previous=[*current, SCHEMA_A]))
    assert sorted(graph.changed("remove")) == sorted([ds("db.a.t1"), ds("db.a.t2")])
    assert graph.changed("add") == []


def test_removing_a_schema_keeps_datasets_covered_by_another_schema_in_the_product() -> None:
    graph = make_graph()
    graph.contents[SCHEMA_B] = [ds("db.a.t1"), ds("db.b.t1")]  # t1 is covered by both schemas
    current = [SCHEMA_B, ds("db.a.t1"), ds("db.a.t2"), ds("db.b.t1")]
    make_action(graph).act(mcl_event(current, previous=[*current, SCHEMA_A]))
    assert graph.changed("remove") == [ds("db.a.t2")]


def test_removing_a_schema_only_removes_datasets_actually_in_the_product() -> None:
    graph = make_graph()
    make_action(graph).act(mcl_event([ds("db.a.t1")], previous=[SCHEMA_A, ds("db.a.t1")]))
    assert graph.changed("remove") == [ds("db.a.t1")]


def test_dry_run_writes_nothing() -> None:
    graph = make_graph()
    make_action(graph, dry_run=True).act(mcl_event([SCHEMA_A], previous=[]))
    assert graph.emitted == []


def test_adds_are_emitted_in_batches() -> None:
    graph = make_graph()
    graph.contents[SCHEMA_A] = [ds(f"db.a.t{i}") for i in range(5)]
    make_action(graph, batch_size=2).act(mcl_event([SCHEMA_A], previous=[]))
    assert len(graph.emitted) == 3
    assert len(graph.changed("add")) == 5


def test_the_actions_own_follow_up_event_does_nothing() -> None:
    graph = make_graph()
    before = [SCHEMA_A]
    after = [SCHEMA_A, ds("db.a.t1"), ds("db.a.t2")]
    make_action(graph).act(mcl_event(after, previous=before))
    assert graph.emitted == []


@pytest.mark.parametrize(
    "event",
    [
        mcl_event([SCHEMA_A], previous=[], entity_type="dataset"),
        mcl_event([SCHEMA_A], previous=[], aspect_name="dataProductKey"),
        mcl_event(None, previous=[SCHEMA_A]),
        EventEnvelope(ENTITY_CHANGE_EVENT_V1_TYPE, SimpleNamespace(), {}),
    ],
)
def test_unrelated_events_are_ignored(event: EventEnvelope) -> None:
    graph = make_graph()
    make_action(graph).act(event)
    assert graph.emitted == []


def test_config_defaults_and_validation() -> None:
    config = SchemaMembershipSyncConfig.model_validate({})
    assert config.schema_subtypes == ["Schema"]
    assert config.dry_run is False
    with pytest.raises(ValidationError):
        SchemaMembershipSyncConfig.model_validate({"batch_size": 0})


def test_create_requires_a_datahub_connection() -> None:
    with pytest.raises(ValueError, match="DataHub connection"):
        SchemaMembershipSyncAction.create({}, SimpleNamespace(graph=None))  # type: ignore[arg-type]
