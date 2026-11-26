"""Helpers shared by step implementations."""

from __future__ import annotations

from typing import Any, Optional


def other_workflow_skip(expected: Optional[str], ctx: Any) -> Optional[dict[str, Any]]:
    """Return a skip result when the step is pinned to a workflow other than the one that fired.

    Several workflows can share one engine, and a rule fires for any of them, so steps
    take an optional ``workflow_urn`` param to ignore events from the others. Return
    the dict as the step result; None means carry on.
    """
    if not expected:
        return None
    actual = ((getattr(ctx, "context", None) or {}).get("workflow") or {}).get("urn")
    if actual and actual != expected:
        return {"skipped": True, "reason": f"workflow {actual} != {expected}"}
    return None
