"""``log_message``: write a message to the engine log. A template for new step types.

Copy this file to add a step: keep the pure logic in a plain function so it can be
tested without the engine, and do the engine-specific wiring inside ``register``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from steves_workflow_helpers.engine import EngineApi
from steves_workflow_helpers.workflow import other_workflow_skip

logger = logging.getLogger(__name__)

STEP_NAME = "log_message"
_LEVELS = {"debug", "info", "warning", "error"}


def log_message(message: str, level: str) -> dict[str, Any]:
    """Log ``message`` at ``level`` and return the step output."""
    if level not in _LEVELS:
        raise ValueError(f"level must be one of {sorted(_LEVELS)}, got {level!r}")
    getattr(logger, level)("%s", message)
    return {"message": message, "level": level}


def register(engine: EngineApi) -> None:
    if STEP_NAME in engine.registry:
        return

    class LogMessageParams(engine.step_params):  # type: ignore[name-defined,misc]
        message: str
        level: str = "info"
        workflow_urn: Optional[str] = None

    @engine.step(
        STEP_NAME,
        label="Log message",
        description="Write a message to the engine log.",
        group="Utilities",
        params=LogMessageParams,
        outputs={"message": "The message that was logged"},
    )
    def log_message_step(params: LogMessageParams, ctx: Any) -> dict[str, Any]:
        skipped = other_workflow_skip(params.workflow_urn, ctx)
        if skipped:
            return skipped
        if ctx.dry_run:
            return {"dryRun": True, "message": params.message, "level": params.level}
        return log_message(params.message, params.level)
