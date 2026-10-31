"""FastAPI server for A2A discovery and JSON-RPC task methods."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ValidationError

from src.a2a.types import (
    AgentCard,
    GetTaskRequest,
    GetTaskResponse,
    JSONRPCResponse,
    SendTaskRequest,
    SendTaskStreamingRequest,
)
from src.a2a.utils import dump_model

logger = logging.getLogger(__name__)


def _rpc_error(request_id: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    )


class A2AServer:
    """Serve one agent card and the A2A JSON-RPC methods on ``/rpc``."""

    def __init__(
        self,
        agent_card: AgentCard,
        task_manager: Any,
        host: str = "localhost",
        port: int = 8000,
    ) -> None:
        self.agent_card = agent_card
        self.task_manager = task_manager
        self.host = host
        self.port = port
        self.app = FastAPI()
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self._setup_routes()

    def _setup_routes(self) -> None:
        @self.app.get("/.well-known/agent.json")
        async def get_agent_card() -> dict[str, Any]:
            return dump_model(self.agent_card)

        @self.app.post("/rpc", response_model=None)
        async def handle_rpc(request: Request) -> JSONResponse | StreamingResponse:
            body: dict[str, Any] = {}
            try:
                body = await request.json()
                request_id = body.get("id", 0)
                method = body.get("method")
                if not method:
                    return _rpc_error(request_id, -32600, "Invalid request: no method")
                if method == "tasks/send":
                    return await self._send(body)
                if method == "tasks/sendSubscribe":
                    return await self._send_subscribe(body)
                if method == "tasks/get":
                    return await self._get(body)
                if method == "tasks/cancel":
                    return await self._cancel(body)
                if method == "tasks/pushNotification/set":
                    return await self._set_push(body)
                if method == "tasks/pushNotification/get":
                    return await self._get_push(body)
                return _rpc_error(request_id, -32601, f"Method not found: {method}")
            except ValidationError as exc:
                logger.error("Invalid JSON-RPC request: %s", exc)
                return _rpc_error(body.get("id", 0) if body else 0, -32600, f"Invalid request: {exc}")
            except Exception as exc:
                logger.error("Error handling request: %s", exc)
                return _rpc_error(
                    body.get("id", 0) if body else 0,
                    -32603,
                    f"Internal error: {exc}",
                )

    async def _send(self, body: dict[str, Any]) -> JSONResponse:
        request_obj = SendTaskRequest(**body)
        response = await self.task_manager.on_send_task(request_obj)
        return JSONResponse(dump_model(response))

    async def _send_subscribe(self, body: dict[str, Any]) -> JSONResponse | StreamingResponse:
        request_obj = SendTaskStreamingRequest(**body)
        result = await self.task_manager.on_send_task_subscribe(request_obj)
        if isinstance(result, JSONRPCResponse):
            return JSONResponse(dump_model(result))

        async def stream(events: AsyncIterable[BaseModel]):
            async for event in events:
                payload = dump_model(event)
                yield f"data: {json.dumps(payload)}\n\n"

        return StreamingResponse(stream(result), media_type="text/event-stream")

    async def _get(self, body: dict[str, Any]) -> JSONResponse:
        request_obj = GetTaskRequest(**body)
        task_id = request_obj.params.get("id")
        history_length = request_obj.params.get("historyLength", 0)
        task = await self.task_manager.get_task(task_id, history_length)
        if task is None:
            return _rpc_error(request_obj.id, -32000, f"Task {task_id} not found")
        return JSONResponse(dump_model(GetTaskResponse(id=request_obj.id, result=task)))

    async def _cancel(self, body: dict[str, Any]) -> JSONResponse:
        request_id = body.get("id", 0)
        task_id = body.get("params", {}).get("id")
        if not task_id:
            return _rpc_error(request_id, -32602, "Invalid params: missing id")
        task = await self.task_manager.cancel_task(task_id)
        if task is None:
            return _rpc_error(request_id, -32000, f"Task {task_id} not found")
        return JSONResponse(
            {"jsonrpc": "2.0", "id": request_id, "result": dump_model(task)}
        )

    async def _set_push(self, body: dict[str, Any]) -> JSONResponse:
        request_id = body.get("id", 0)
        task_id = body.get("params", {}).get("id")
        config = body.get("params", {}).get("pushNotificationConfig")
        if not task_id or not config:
            return _rpc_error(
                request_id,
                -32602,
                "Invalid params: missing id or pushNotificationConfig",
            )
        result = await self.task_manager.set_push_notification(task_id, config)
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})

    async def _get_push(self, body: dict[str, Any]) -> JSONResponse:
        request_id = body.get("id", 0)
        task_id = body.get("params", {}).get("id")
        if not task_id:
            return _rpc_error(request_id, -32602, "Invalid params: missing id")
        result = await self.task_manager.get_push_notification(task_id)
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})

    def start(self) -> None:
        import uvicorn

        logger.info("Starting A2A server on %s:%s", self.host, self.port)
        uvicorn.run(self.app, host=self.host, port=self.port)
