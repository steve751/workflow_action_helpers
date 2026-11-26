"""Access to the workflow engine's step API, which is only present inside the engine's venv."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EngineApi:
    """The pieces of ``datahub_workflow_actions.steps`` that step modules build on."""

    registry: Any
    step: Any
    step_params: Any
    run_context: Any


def load_engine() -> Optional[EngineApi]:
    """Return the engine's step API, or None when the engine is not installed.

    Returning None (instead of raising) lets this package be imported, and its pure
    helpers be tested, in an environment without the engine.
    """
    try:
        from datahub_workflow_actions.steps import (  # type: ignore[import-not-found]
            REGISTRY,
            RunContext,
            StepParams,
            step,
        )
    except ImportError:
        logger.debug("workflow engine is not installed; skipping step registration")
        return None
    return EngineApi(
        registry=REGISTRY, step=step, step_params=StepParams, run_context=RunContext
    )
