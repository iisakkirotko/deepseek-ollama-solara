import datetime
import uuid
from typing import Any

from ollama import Message as OllamaMessage
from typing_extensions import TypedDict


class Message(OllamaMessage):
    created: datetime.datetime
    chain_of_reason: str | None = None


class ChatDict(TypedDict):
    title: str
    model: str
    id: uuid.UUID


class ToolResult(TypedDict):
    message: str
    content: Any
