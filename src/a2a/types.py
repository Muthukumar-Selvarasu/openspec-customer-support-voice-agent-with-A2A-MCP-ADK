"""JSON-RPC 2.0 and agent-card models for the A2A task protocol."""

from __future__ import annotations

from enum import Enum
from typing import Any, Union

from pydantic import BaseModel


class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"
    UNKNOWN = "unknown"


class TextPart(BaseModel):
    type: str = "text"
    text: str


class FilePart(BaseModel):
    type: str = "file"
    file: dict[str, Any]


class DataPart(BaseModel):
    type: str = "data"
    data: dict[str, Any]


Part = Union[TextPart, FilePart, DataPart]


class Message(BaseModel):
    role: str
    parts: list[Part]
    metadata: dict[str, Any] = {}


class Artifact(BaseModel):
    name: str | None = None
    description: str | None = None
    parts: list[Part]
    metadata: dict[str, Any] = {}
    index: int
    append: bool | None = False
    lastChunk: bool | None = False


class TaskStatus(BaseModel):
    state: TaskState
    message: Message | None = None
    timestamp: str | None = None


class Task(BaseModel):
    id: str
    sessionId: str
    status: TaskStatus
    history: list[Message] | None = None
    artifacts: list[Artifact] | None = None
    metadata: dict[str, Any] = {}


class TaskStatusUpdateEvent(BaseModel):
    id: str
    status: TaskStatus
    final: bool
    metadata: dict[str, Any] | None = None


class TaskArtifactUpdateEvent(BaseModel):
    id: str
    artifact: Artifact
    metadata: dict[str, Any] | None = None


class PushNotificationConfig(BaseModel):
    url: str
    token: str | None = None
    authentication: dict[str, Any] | None = None


class TaskSendParams(BaseModel):
    id: str
    sessionId: str | None = None
    message: Message
    historyLength: int | None = None
    pushNotification: PushNotificationConfig | None = None
    metadata: dict[str, Any] = {}
    acceptedOutputModes: list[str] | None = None


class AgentCapabilities(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False
    stateTransitionHistory: bool = False


class AgentProvider(BaseModel):
    organization: str
    url: str


class AgentAuthentication(BaseModel):
    schemes: list[str]
    credentials: str | None = None


class AgentSkill(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str]
    examples: list[str] | None = None
    inputModes: list[str] | None = None
    outputModes: list[str] | None = None


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    provider: AgentProvider | None = None
    version: str
    documentationUrl: str | None = None
    capabilities: AgentCapabilities
    authentication: AgentAuthentication | None = None
    defaultInputModes: list[str]
    defaultOutputModes: list[str]
    skills: list[AgentSkill]


class JsonRpcError(BaseModel):
    code: int
    message: str


class InternalError(JsonRpcError):
    code: int = -32603
    message: str


class MethodNotFoundError(JsonRpcError):
    code: int = -32601
    message: str = "Method not found"


class InvalidRequestError(JsonRpcError):
    code: int = -32600
    message: str


class TaskError(JsonRpcError):
    """JSON-RPC server error used for task failures and missing tasks."""

    code: int = -32000
    message: str


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: int
    result: Any | None = None
    error: JsonRpcError | None = None


class SendTaskRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: int
    method: str = "tasks/send"
    params: TaskSendParams


class SendTaskResponse(JSONRPCResponse):
    result: Task | None = None


class SendTaskStreamingRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: int
    method: str = "tasks/sendSubscribe"
    params: TaskSendParams


class SendTaskStreamingResponse(JSONRPCResponse):
    result: TaskStatusUpdateEvent | TaskArtifactUpdateEvent | None = None


class GetTaskRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: int
    method: str = "tasks/get"
    params: dict[str, Any]


class GetTaskResponse(JSONRPCResponse):
    result: Task | None = None


class MissingAPIKeyError(Exception):
    """Raised when a live model call is attempted without credentials."""
