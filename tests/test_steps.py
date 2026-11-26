from __future__ import annotations

from types import SimpleNamespace

import pytest

from steves_workflow_helpers import register_engine_steps
from steves_workflow_helpers.actions.log_message import STEP_NAME, log_message
from steves_workflow_helpers.engine import EngineApi
from steves_workflow_helpers.graph import GraphQLStepError, run_graphql
from steves_workflow_helpers.workflow import other_workflow_skip


def test_register_adds_step_once(fake_engine: EngineApi) -> None:
    register_engine_steps(fake_engine)
    first = fake_engine.registry[STEP_NAME]
    register_engine_steps(fake_engine)
    assert fake_engine.registry[STEP_NAME] is first


def test_registered_step_runs_and_honours_dry_run(fake_engine: EngineApi) -> None:
    register_engine_steps(fake_engine)
    step = fake_engine.registry[STEP_NAME]
    params = SimpleNamespace(message="hello", level="info", workflow_urn=None)

    assert step(params, SimpleNamespace(dry_run=False, context={})) == {
        "message": "hello",
        "level": "info",
    }
    assert step(params, SimpleNamespace(dry_run=True, context={}))["dryRun"] is True


def test_registered_step_skips_other_workflow(fake_engine: EngineApi) -> None:
    register_engine_steps(fake_engine)
    step = fake_engine.registry[STEP_NAME]
    params = SimpleNamespace(message="x", level="info", workflow_urn="urn:li:actionWorkflow:a")
    ctx = SimpleNamespace(dry_run=False, context={"workflow": {"urn": "urn:li:actionWorkflow:b"}})
    assert step(params, ctx)["skipped"] is True


def test_log_message_rejects_unknown_level() -> None:
    with pytest.raises(ValueError):
        log_message("x", "loud")


def test_other_workflow_skip() -> None:
    ctx = SimpleNamespace(context={"workflow": {"urn": "urn:li:actionWorkflow:b"}})
    assert other_workflow_skip(None, ctx) is None
    assert other_workflow_skip("urn:li:actionWorkflow:b", ctx) is None
    assert other_workflow_skip("urn:li:actionWorkflow:a", ctx) is not None


def test_run_graphql_wraps_client_errors() -> None:
    class Graph:
        def execute_graphql(self, **_: object) -> dict:
            raise ConnectionError("boom")

    with pytest.raises(GraphQLStepError, match="myOp failed"):
        run_graphql(Graph(), query="query { me }", operation_name="myOp")
