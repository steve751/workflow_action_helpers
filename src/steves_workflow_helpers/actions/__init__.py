"""Step types provided by this package. Add a new step's ``register`` function to REGISTRARS."""

from __future__ import annotations

from typing import Callable

from steves_workflow_helpers.actions import log_message
from steves_workflow_helpers.engine import EngineApi

REGISTRARS: list[Callable[[EngineApi], None]] = [log_message.register]
