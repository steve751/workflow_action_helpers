from __future__ import annotations

from typing import Any, Callable

import pytest

from steves_workflow_helpers.engine import EngineApi


class FakeStepParams:
    """Stand-in for the engine's pydantic ``StepParams`` base (keyword-initialised)."""

    def __init__(self, **kwargs: Any) -> None:
        for name in getattr(type(self), "__annotations__", {}):
            setattr(self, name, kwargs.get(name, getattr(type(self), name, None)))


@pytest.fixture
def fake_engine() -> EngineApi:
    registry: dict[str, Callable[..., Any]] = {}

    def step(name: str, **_meta: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            registry[name] = fn
            return fn

        return decorate

    return EngineApi(
        registry=registry, step=step, step_params=FakeStepParams, run_context=object
    )
