import datetime
from typing import Any
import uuid
from typing_extensions import TypedDict

from ollama import Message as OllamaMessage


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