import datetime
import json
import uuid
from collections.abc import AsyncIterator
from typing import List, cast

import solara
import solara.lab
from ollama import AsyncClient, ChatResponse
from ollama._types import ResponseError

from .database import (
    connect_database,
    create_chat,
    create_messages,
    get_chats,
    get_messages,
)
from .interface import ChatMessage, ChatTitle
from .tools import tool_callables, tools
from .types import ChatDict, Message

SUPPORTS_TOOLS: dict[str, bool] = {}

chats: solara.Reactive[List[ChatDict]] = solara.reactive([])
selected_chat: solara.Reactive[ChatDict | None] = solara.reactive(None)
messages: solara.Reactive[List[Message]] = solara.reactive([])
models: solara.Reactive[List[str]] = solara.reactive([])
current_model: solara.Reactive[str] = solara.reactive("deepseek-r1:8b")
use_tools: solara.Reactive[bool] = solara.reactive(False)


async def init():
    ai_client = AsyncClient()
    await connect_database()
    chats.value = await get_chats()
    available_models = await ai_client.list()
    models.value = [model.model for model in available_models.models]
    for model in available_models.models:
        if model.model not in SUPPORTS_TOOLS:
            SUPPORTS_TOOLS[model.model] = True


async def process_response(response: AsyncIterator[ChatResponse]) -> list[Message]:
    thinking = False
    tool_messages: list[Message] = []
    assistant_message: Message | None = None
    async for chunk in response:
        if chunk.message.tool_calls is not None:
            for tool_call in chunk.message.tool_calls:
                tool_callable = tool_callables[tool_call.function.name]
                tool_result = await tool_callable(**tool_call.function.arguments)  # type: ignore
                tool_message = Message(
                    role="tool",
                    created=datetime.datetime.now(),
                    content=json.dumps(tool_result),
                    chain_of_reason=None,
                )
                tool_messages.append(tool_message)
                messages.value = [*messages.value, tool_message]
            break

        # replace the last message element with the appended content
        delta = chunk.message.content
        if "<think>" == delta:
            thinking = True
            continue
        if "</think>" == delta:
            thinking = False
            continue
        assert delta is not None
        created = (
            assistant_message.created if assistant_message is not None else datetime.datetime.now()
        )
        message_content = assistant_message.content if assistant_message is not None else None
        chain_of_reason = (
            assistant_message.chain_of_reason if assistant_message is not None else None
        )

        if thinking:
            if chain_of_reason is None:
                chain_of_reason = ""
            chain_of_reason += delta
        else:
            if message_content is None:
                message_content = ""
            message_content += delta

        updated_message = Message(
            role="assistant",
            created=created,
            content=message_content,
            chain_of_reason=chain_of_reason,
        )
        # if we don't have an assistant message yet, create one
        if assistant_message is None:
            messages.value = [*messages.value, updated_message]
        else:
            # replace the last message element with the appended content
            # which will update the UI
            messages.value = [*messages.value[:-1], updated_message]

        assistant_message = updated_message

        if chunk.done_reason == "stop":
            break

    messages_to_create = tool_messages
    if assistant_message is not None:
        messages_to_create.append(assistant_message)
    return messages_to_create


async def chat_loop(ai_client: AsyncClient, model_to_use: str):
    # The part below can be replaced with a call to your own
    response = await ai_client.chat(
        model=model_to_use,
        # our MessageDict is compatible with the OpenAI types
        messages=messages.value,
        stream=True,
        tools=tools if (SUPPORTS_TOOLS[model_to_use] and use_tools.value) else None,
    )

    try:
        messages_to_create = await process_response(response)
    except ResponseError as e:
        if "does not support tools" in str(e):
            SUPPORTS_TOOLS[model_to_use] = False

            response = await ai_client.chat(
                model=model_to_use,
                # our MessageDict is compatible with the OpenAI types
                messages=messages.value,
                stream=True,
            )
            messages_to_create = await process_response(response)

    if messages_to_create[-1].role == "tool":
        messages_to_create += await chat_loop(ai_client=ai_client, model_to_use=model_to_use)

    return messages_to_create


@solara.lab.task
async def update_messages():
    messages.value = await get_messages(selected_chat.value["id"])


@solara.lab.task(prefer_threaded=False)
async def promt_ai(message: str):
    ai_client = AsyncClient()
    model_to_use = (
        current_model.value if selected_chat.value is None else selected_chat.value["model"]
    )
    user_message = Message(
        role="user", created=datetime.datetime.now(), content=message, chain_of_reason=None
    )
    if selected_chat.value is None:
        new_chat = await create_chat("New Chat", uuid.uuid4(), current_model.value)
        selected_chat.value = cast(
            ChatDict, {"id": new_chat["id"], "title": new_chat["title"], "model": new_chat["model"]}
        )

    messages.value = [*messages.value, user_message]

    messages_to_create = await chat_loop(ai_client=ai_client, model_to_use=model_to_use)

    assert selected_chat.value is not None
    await create_messages(selected_chat.value["id"], [user_message, *messages_to_create])


@solara.component
def Page():
    init_task = solara.lab.use_task(init, dependencies=[selected_chat.value])
    empty_chat = selected_chat.value is None or len(messages.value) == 0
    if init_task.pending:
        with solara.Column(
            style={"width": "100%", "height": "100%", "justify-content": "center"}, align="center"
        ):
            solara.SpinnerSolara()
            solara.Text("Loading...")
    else:
        with solara.Column(
            style={"width": "100%", "height": "50vh" if empty_chat else "100%"},
        ):
            if selected_chat.value is not None:
                ChatTitle(selected_chat=selected_chat)
            with solara.lab.ChatBox():
                if update_messages.pending:
                    solara.Text("Loading messages...")
                else:
                    if empty_chat:
                        model_name = current_model.value.split(":")[0]
                    else:
                        model_name = selected_chat.value["model"].split(":")[0]

                        for message in messages.value:
                            ChatMessage(message, model_name)
            if promt_ai.pending:
                solara.Text("I'm thinking...", style={"font-size": "1rem", "padding-left": "20px"})
                solara.ProgressLinear()
            # if we don't call .key(..) with a unique key, the ChatInput component will be re-created
            # and we'll lose what we typed.
            chatinput_style = {
                "width": "50%" if empty_chat else "auto",
                "align-self": "center" if empty_chat else "stretch",
            }
            solara.lab.ChatInput(
                send_callback=promt_ai, disabled=promt_ai.pending, style=chatinput_style
            ).key("input")
            ChatOptions()


@solara.component
def Layout(children=[]):
    def update_selected_chat(value: str | None):
        if value is None:
            selected_chat.set(None)
            messages.set([])
        else:
            selected_chat.set(next(chat for chat in chats.value if chat["id"] == uuid.UUID(value)))
            update_messages()

    with solara.Row(style={"width": "100%", "height": "100dvh"}, gap=0):
        with solara.v.NavigationDrawer(v_model=True):
            solara.Button(
                label="New Chat",
                on_click=lambda: update_selected_chat(None),
                style={"width": "100%", "justify-content": "flex-start"},
                text=True,
                icon_name="add",
            )
            with solara.v.ListItemGroup(
                v_model=str(selected_chat.value["id"] if selected_chat.value is not None else None),
                on_v_model=update_selected_chat,
                style_="max-height: calc(100% - 115px); overflow-y: auto;",
            ):
                for chat in chats.value:
                    with solara.v.ListItem(value=str(chat["id"]), dense=True):
                        solara.v.ListItemTitle(children=[chat["title"]])
            if len(models.value) > 1:
                solara.Select(
                    label="Model",
                    values=models.value,
                    value=current_model,
                    style={
                        "align-self": "flex-end",
                        "position": "absolute",
                        "bottom": "0",
                        "padding": "0 16px",
                    },
                )
        with solara.Column(
            children=children,
            gap=0,
            style={"height": "calc(100dvh - 44px)", "flex": 1, "padding": "20px"},
        ):
            pass


@solara.component
def ChatOptions():
    model_in_use = (
        current_model.value if selected_chat.value is None else selected_chat.value["model"]
    )

    with solara.Row():
        with solara.Tooltip(
            "Using tools (function calling), will disable streaming responses, since Ollama does not support this yet."
            if SUPPORTS_TOOLS[model_in_use]
            else "Current model does not support tools (function calling)"
        ):
            solara.Switch(
                value=use_tools,
                label="Use Tools",
                style={"margin": "0"},
                disabled=SUPPORTS_TOOLS[model_in_use] is False,
            )
