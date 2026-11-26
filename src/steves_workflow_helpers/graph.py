"""GraphQL helper for steps that write to DataHub."""

from __future__ import annotations

from typing import Any, Optional


class GraphQLStepError(RuntimeError):
    """A GraphQL call made by a step failed or returned an unusable result."""


def run_graphql(
    graph: Any,
    *,
    query: str,
    operation_name: str,
    variables: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Execute a GraphQL operation and return its ``data`` payload.

    Wraps any client failure in GraphQLStepError naming the operation, so the engine
    log shows which step call failed rather than a bare transport error.
    """
    try:
        result = graph.execute_graphql(
            query=query, variables=variables or {}, operation_name=operation_name
        )
    except Exception as e:
        raise GraphQLStepError(f"{operation_name} failed: {e}") from e
    if not isinstance(result, dict):
        raise GraphQLStepError(f"{operation_name} returned no data")
    return result
