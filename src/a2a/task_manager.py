"""In-memory A2A task storage and Judge/Masker task execution."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterable, Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from src.a2a.types import (
    Artifact,
    JSONRPCResponse,
    Message,
    SendTaskRequest,
    SendTaskResponse,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskError,
    TaskSendParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from src.a2a.utils import are_modalities_compatible, new_incompatible_types_error

logger = logging.getLogger(__name__)

SUPPORTED_MODES = ["text", "text/plain"]
AgentCall = Callable[[str], Awaitable[str]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InMemoryTaskManager:
    """Store A2A tasks in process memory."""

    def __init__(self) -> None:
        self.tasks: dict[str, Task] = {}
        self.task_messages: dict[str, list[Message]] = {}
        self.push_notifications: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def upsert_task(self, params: TaskSendParams) -> Task:
        async with self._lock:
            task_id = params.id
            session_id = params.sessionId or str(uuid.uuid4())
            if task_id not in self.tasks:
                task = Task(
                    id=task_id,
                    sessionId=session_id,
                    status=TaskStatus(state=TaskState.SUBMITTED, timestamp=_utc_now()),
                    history=[],
                    artifacts=[],
                )
                self.tasks[task_id] = task
                self.task_messages[task_id] = []
            else:
                task = self.tasks[task_id]

            self.task_messages[task_id].append(params.message)
            history = self.task_messages[task_id]
            task.history = history[-params.historyLength :] if params.historyLength else history
            task.status = TaskStatus(state=TaskState.WORKING, timestamp=_utc_now())
            return task

    async def get_task(self, task_id: str, history_length: int = 0) -> Task | None:
        async with self._lock:
            task = self.tasks.get(task_id)
            if task is None:
                return None
            messages = self.task_messages.get(task_id, [])
            task.history = messages[-history_length:] if history_length > 0 else messages
            return task

    async def cancel_task(self, task_id: str) -> Task | None:
        async with self._lock:
            task = self.tasks.get(task_id)
            if task is None:
                return None
            task.status = TaskStatus(state=TaskState.CANCELED, timestamp=_utc_now())
            return task

    async def set_push_notification(self, task_id: str, config: dict[str, Any]) -> dict[str, Any]:
        self.push_notifications[task_id] = config
        return {"id": task_id, "pushNotificationConfig": config}

    async def get_push_notification(self, task_id: str) -> dict[str, Any]:
        return {
            "id": task_id,
            "pushNotificationConfig": self.push_notifications.get(task_id),
        }

    async def on_send_task(self, request: SendTaskRequest) -> JSONRPCResponse:
        raise NotImplementedError

    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        raise NotImplementedError


def _validate_request(
    request: SendTaskRequest | SendTaskStreamingRequest,
) -> JSONRPCResponse | None:
    params = request.params
    if are_modalities_compatible(params.acceptedOutputModes, SUPPORTED_MODES):
        return None
    logger.warning(
        "Unsupported output mode. Received %s, support %s",
        params.acceptedOutputModes,
        SUPPORTED_MODES,
    )
    return new_incompatible_types_error(request.id)


def _part_text(part: Any) -> str | None:
    if isinstance(part, TextPart):
        return part.text
    if isinstance(part, dict) and part.get("type") == "text":
        return str(part.get("text", ""))
    return None


def user_query(params: TaskSendParams) -> str:
    """Return the first text part of a task message."""
    for part in params.message.parts:
        text = _part_text(part)
        if text is not None:
            return text
    raise ValueError("Only text parts are supported")


class _AgentTaskManager(InMemoryTaskManager):
    """Run one async agent call for send and sendSubscribe."""

    def __init__(self, agent_call: AgentCall) -> None:
        super().__init__()
        self.call_agent = agent_call

    async def on_send_task(self, request: SendTaskRequest) -> JSONRPCResponse:
        error = _validate_request(request)
        if error is not None:
            return error
        await self.upsert_task(request.params)
        return await self._invoke(request)

    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        error = _validate_request(request)
        if error is not None:
            return error
        await self.upsert_task(request.params)
        return self._stream(request)

    async def _stream(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[JSONRPCResponse]:
        params = request.params
        try:
            yield SendTaskStreamingResponse(
                id=request.id,
                result=TaskStatusUpdateEvent(
                    id=params.id,
                    status=TaskStatus(state=TaskState.WORKING),
                    final=False,
                ),
            )
            result = await self.call_agent(user_query(params))
            parts = [{"type": "text", "text": result}]
            message = Message(role="agent", parts=parts)
            status = TaskStatus(state=TaskState.COMPLETED, message=message)
            artifacts = [Artifact(parts=parts, index=0, lastChunk=True)]
            await self._update_store(params.id, status, artifacts)
            yield SendTaskStreamingResponse(
                id=request.id,
                result=TaskArtifactUpdateEvent(id=params.id, artifact=artifacts[0]),
            )
            yield SendTaskStreamingResponse(
                id=request.id,
                result=TaskStatusUpdateEvent(id=params.id, status=status, final=True),
            )
        except Exception as exc:
            logger.error("Error streaming response: %s", exc)
            yield JSONRPCResponse(
                id=request.id,
                error=TaskError(message=f"Error streaming response: {exc}"),
            )

    async def _update_store(
        self,
        task_id: str,
        status: TaskStatus,
        artifacts: list[Artifact],
    ) -> Task:
        async with self._lock:
            try:
                task = self.tasks[task_id]
            except KeyError as exc:
                logger.error("Task %s not found for update", task_id)
                raise ValueError(f"Task {task_id} not found") from exc
            task.status = status
            if task.artifacts is None:
                task.artifacts = []
            task.artifacts.extend(artifacts)
            return task

    async def _invoke(self, request: SendTaskRequest) -> JSONRPCResponse:
        params = request.params
        try:
            result = await self.call_agent(user_query(params))
        except Exception as exc:
            logger.error("Error invoking agent: %s", exc)
            return JSONRPCResponse(
                id=request.id,
                error=TaskError(message=f"Error invoking agent: {exc}"),
            )

        parts = [{"type": "text", "text": result}]
        task = await self._update_store(
            params.id,
            TaskStatus(
                state=TaskState.COMPLETED,
                message=Message(role="agent", parts=parts),
            ),
            [Artifact(parts=parts, index=0)],
        )
        return SendTaskResponse(id=request.id, result=task)


class JudgeTaskManager(_AgentTaskManager):
    def __init__(self, judge_agent_call: AgentCall) -> None:
        super().__init__(agent_call=judge_agent_call)


class MaskTaskManager(_AgentTaskManager):
    def __init__(self, mask_agent_call: AgentCall) -> None:
        super().__init__(agent_call=mask_agent_call)
