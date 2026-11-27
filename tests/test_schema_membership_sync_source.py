from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("datahub_actions")

from datahub_actions.pipeline.pipeline_config import PipelineConfig  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from steves_workflow_helpers.plugins.schema_membership_sync_source import (  # noqa: E402
    SchemaMembershipSyncSource,
    SchemaMembershipSyncSourceConfig,
    build_pipeline_config,
    datahub_client_config,
)


def test_pipeline_config_is_a_valid_actions_pipeline() -> None:
    config = SchemaMembershipSyncSourceConfig.model_validate(
        {"schema_subtypes": ["Schema", "Database"], "batch_size": 50, "dry_run": True}
    )
    built = build_pipeline_config(config, {"server": "http://gms", "token": "t"})

    parsed = PipelineConfig.model_validate(built)

    assert parsed.name == "schema-membership-sync"
    assert parsed.source.type == "datahub-cloud"
    assert parsed.source.config["topics"] == ["MetadataChangeLog_Versioned_v1"]
    assert parsed.filter.event_type == "MetadataChangeLogEvent_v1"
    assert parsed.filter.event == {
        "entityType": "dataProduct",
        "aspectName": "dataProductProperties",
    }
    assert parsed.action.type == "schema_membership_sync"
    assert parsed.action.config == {
        "schema_subtypes": ["Schema", "Database"],
        "batch_size": 50,
        "dry_run": True,
        "skip_datasets_in_other_products": True,
    }


def test_cloud_events_overrides_win() -> None:
    config = SchemaMembershipSyncSourceConfig.model_validate(
        {"pipeline_name": "mine", "cloud_events": {"lookback_days": 3}}
    )
    built = build_pipeline_config(config, None)

    assert built["name"] == "mine"
    assert built["source"]["config"]["lookback_days"] == 3
    assert "datahub" not in built


def test_config_rejects_unknown_keys_and_bad_batch_size() -> None:
    with pytest.raises(ValidationError):
        SchemaMembershipSyncSourceConfig.model_validate({"nope": 1})
    with pytest.raises(ValidationError):
        SchemaMembershipSyncSourceConfig.model_validate({"batch_size": 0})


def test_datahub_client_config_prefers_the_run_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAHUB_GMS_URL", "http://from-env")
    ctx = SimpleNamespace(graph=SimpleNamespace(config=SimpleNamespace(server="http://run", token="abc")))
    assert datahub_client_config(ctx) == {"server": "http://run", "token": "abc"}


def test_datahub_client_config_falls_back_to_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATAHUB_GMS_HOST", raising=False)
    monkeypatch.setenv("DATAHUB_GMS_URL", "http://from-env")
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "tok")
    assert datahub_client_config(SimpleNamespace(graph=None)) == {
        "server": "http://from-env",
        "token": "tok",
    }
    monkeypatch.delenv("DATAHUB_GMS_URL")
    assert datahub_client_config(SimpleNamespace(graph=None)) is None


def test_source_without_a_connection_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DATAHUB_GMS_URL", "DATAHUB_GMS_HOST", "DATAHUB_GMS_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    source = SchemaMembershipSyncSource.create({}, SimpleNamespace(graph=None, pipeline_name="x"))
    with pytest.raises(ValueError, match="needs a DataHub connection"):
        list(source.get_workunits())
