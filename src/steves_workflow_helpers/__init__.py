"""Custom step types and helpers for the DataHub workflow actions engine."""

from __future__ import annotations

import logging

from steves_workflow_helpers.actions import REGISTRARS
from steves_workflow_helpers.engine import EngineApi, load_engine

logger = logging.getLogger(__name__)


def register_engine_steps(engine: EngineApi | None = None) -> None:
    """Register every step in this package on the engine, if the engine is installed.

    Runs from a ``.pth`` file at interpreter start in every Python process in the
    engine's venv (pip, the executor, ...), so a failing step must never prevent
    start-up: failures are logged and swallowed.
    """
    engine = engine or load_engine()
    if engine is None:
        return
    for registrar in REGISTRARS:
        try:
            registrar(engine)
        except Exception:
            logger.exception("failed to register step via %s", registrar)


register_engine_steps()
