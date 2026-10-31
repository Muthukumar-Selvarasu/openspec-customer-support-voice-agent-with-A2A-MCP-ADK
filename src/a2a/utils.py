"""Helpers for modality checks and JSON-RPC payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.a2a.types import InvalidRequestError, JSONRPCResponse


def are_modalities_compatible(
    client_modalities: list[str] | None,
    agent_modalities: list[str],
) -> bool:
    """Return True when the client accepts any mode the agent can emit."""
    if not client_modalities:
        return True
    return any(modality in agent_modalities for modality in client_modalities)


def new_incompatible_types_error(request_id: int) -> JSONRPCResponse:
    """JSON-RPC error for an output mode the agent cannot produce."""
    return JSONRPCResponse(
        id=request_id,
        error=InvalidRequestError(
            message=(
                "Incompatible modalities. The agent does not support any of "
                "the requested output modalities."
            )
        ),
    )


def dump_model(model: BaseModel) -> dict[str, Any]:
    """Serialize a protocol model for a JSON-RPC HTTP response."""
    return model.model_dump(mode="json", exclude_none=True)
