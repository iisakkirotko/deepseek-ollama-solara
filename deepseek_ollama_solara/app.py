from collections.abc import AsyncIterator
import json
from typing import List, cast

from typing import Callable

from ollama import AsyncClient, ChatResponse
from ollama._types import ResponseError
import datetime
import uuid

import solara
import solara.lab
from reacton.ipyvuetify import use_event

from .database import create_messages, connect_database, get_chats, get_messages, create_chat, update_chat
from .tools import tools, tool_callables
from .types import Message, ChatDict

SUPPORTS_TOOLS: dict[str, bool] = {}

chats: solara.Reactive[List[ChatDict]] = solara.reactive([])
selected_chat: solara.Reactive[ChatDict | None] = solara.reactive(None)
messages: solara.Reactive[List[Message]] = solara.reactive([])
models: solara.Reactive[List[str]] = solara.reactive([])
current_model: solara.Reactive[str] = solara.reactive("deepseek-r1:8b")


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
                tool_result = await tool_callable(**tool_call.function.arguments) # type: ignore
                tool_message = Message(role="tool", created=datetime.datetime.now(), content=json.dumps(tool_result), chain_of_reason=None)
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
        created = assistant_message.created if assistant_message is not None else datetime.datetime.now()
        message_content = assistant_message.content if assistant_message is not None else None
        chain_of_reason = assistant_message.chain_of_reason if assistant_message is not None else None
        
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
        tools=tools if SUPPORTS_TOOLS[model_to_use] else None,
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
    model_to_use = current_model.value if selected_chat.value is None else selected_chat.value["model"]
    user_message = Message(role="user", created=datetime.datetime.now(), content=message, chain_of_reason=None)
    if selected_chat.value is None:
        new_chat = await create_chat("New Chat", uuid.uuid4(), current_model.value)
        selected_chat.value = cast(ChatDict, {"id": new_chat["id"], "title": new_chat["title"], "model": new_chat["model"]})

    messages.value = [*messages.value, user_message]

    messages_to_create = await chat_loop(ai_client=ai_client, model_to_use=model_to_use)

    assert selected_chat.value is not None
    await create_messages(selected_chat.value["id"], [user_message, *messages_to_create])


@solara.component
def Page():
    init_task = solara.lab.use_task(init, dependencies=[selected_chat.value])
    empty_chat = selected_chat.value is None or len(messages.value) == 0
    if init_task.pending:
        with solara.Column(style={"width": "100%", "height": "100%", "justify-content": "center"}, align="center"):
            solara.SpinnerSolara()
            solara.Text("Loading...")
    else:
        with solara.Column(
            style={"width": "100%", "height": "50vh" if empty_chat else "100%"},
        ):
            if selected_chat.value is not None:
                ChatTitle()
            with solara.lab.ChatBox():
                if update_messages.pending:
                    solara.Text("Loading messages...")
                else:
                    if empty_chat:
                        model_name = current_model.value.split(":")[0]
                    else:
                        model_name = selected_chat.value["model"].split(":")[0]
                    
                    for item in messages.value:
                        if item["role"] == "tool":
                            tool_result = json.loads(item["content"])
                            with solara.Column(align="flex-start"):
                                solara.Markdown(tool_result["message"])
                        else:
                            with solara.lab.ChatMessage(
                                user=item["role"] == "user",
                                avatar=False,
                                name=model_name if item["role"] == "assistant" else "User",
                                color="rgba(0,0,0, 0.06)" if item["role"] == "assistant" else "#ff991f",
                                avatar_background_color="primary" if item["role"] == "assistant" else None,
                                border_radius="20px",
                            ):
                                if item["chain_of_reason"] is not None:
                                    with solara.Details(summary="Chain of Thought"):
                                        solara.Markdown(item["chain_of_reason"] or "")
                                solara.Markdown(item["content"] or "")
            if promt_ai.pending:
                solara.Text("I'm thinking...", style={"font-size": "1rem", "padding-left": "20px"})
                solara.ProgressLinear()
            # if we don't call .key(..) with a unique key, the ChatInput component will be re-created
            # and we'll lose what we typed.
            chatinput_style = {"width": "50%" if empty_chat else "auto", "align-self": "center" if empty_chat else "stretch"}
            solara.lab.ChatInput(send_callback=promt_ai, disabled=promt_ai.pending, style=chatinput_style).key("input")


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
            solara.Button(label="New Chat", on_click=lambda: update_selected_chat(None), style={"width": "100%", "justify-content": "flex-start"}, text=True, icon_name="add")
            with solara.v.ListItemGroup(v_model=str(selected_chat.value["id"] if selected_chat.value is not None else None), on_v_model=update_selected_chat, style_="max-height: calc(100% - 115px); overflow-y: auto;"):
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
        with solara.Column(children=children, gap=0, style={"height": "calc(100dvh - 44px)", "flex": 1, "padding": "20px"}):
            pass


@solara.component
def ChatTitle():
    editing = solara.use_reactive(False)
    # Keep a local copy of the selected chat that we can modify
    # And then use to update the database
    title = solara.use_reactive(selected_chat.value["title"])

    def start_editing(*_ignore):
        editing.set(True)
    
    def cancel_editing(*_ignore):
        editing.set(False)

    async def _save_title(*_ignore):
        cancel_editing()
        await update_chat(selected_chat.value["id"], title.value)
        new_details: ChatDict = {"id": selected_chat.value["id"], "title": title.value, "model": selected_chat.value["model"]}
        selected_chat.value = new_details

    save_title = solara.lab.use_task(_save_title, dependencies=None)
    
    with solara.Div(style={"display": "flex", "justify-content": "flex-start", "flex-shrink": "0", "max-width": "600px", "overflow": "hidden"}):
        if editing.value:
            solara.InputText(label="Chat Title", value=title)
            IconButton("check", on_click=lambda: save_title())
            IconButton("cancel", on_click=cancel_editing)
            
        else:
            H3(children=[title.value], on_click=start_editing, style={"cursor": "pointer", "flex": 1})


@solara.component
def IconButton(icon: str, on_click: Callable[[], None] | None = None):
    def _on_click(*_):
        if on_click is not None:
            on_click()
    
    with solara.v.Btn(icon=True) as button:
        solara.v.Icon(children=[icon])
    
    use_event(button, "click", _on_click)


@solara.component
def H3(children=[], on_click=None, style: dict[str, str] | str = {}):
    _style = solara.util._flatten_style(style)
    with solara.v.Html(tag="h3", children=children, style_=_style) as title_el:
        pass

    def add_click_handler():
        def _on_click(*_):
            if on_click is not None:
                on_click()
        
        widget = solara.get_widget(title_el)
        widget.on_event("click", _on_click)

        def cleanup():
            widget.on_event("click", _on_click, remove=True)

        return cleanup

    solara.use_effect(add_click_handler, [])