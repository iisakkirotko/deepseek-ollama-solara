from typing import List

from typing import Callable
from typing_extensions import TypedDict

from ollama import AsyncClient
import datetime
import uuid

import solara
import solara.lab
from reacton.ipyvuetify import use_event

from .database import create_message, connect_database, get_chats, get_messages, create_chat, update_chat


class MessageDict(TypedDict):
    role: str  # "user" or "assistant"
    created: datetime.datetime
    content: str
    chain_of_reason: str | None


class ChatDict(TypedDict):
    title: str
    id: uuid.UUID


chats: solara.Reactive[List[ChatDict]] = solara.reactive([])
selected_chat: solara.Reactive[ChatDict | None] = solara.reactive(None)
messages: solara.Reactive[List[MessageDict]] = solara.reactive([])

ai_client = AsyncClient()


async def init():
    await connect_database()
    chats.value = await get_chats()


@solara.lab.task
async def update_messages():
    messages.value = await get_messages(selected_chat.value["id"])


@solara.lab.task
async def promt_ai(message: str):
    thinking = False
    user_message: MessageDict = {"role": "user", "created": datetime.datetime.now(), "content": message, "chain_of_reason": None}
    if selected_chat.value is None:
        new_chat = await create_chat("New Chat", uuid.uuid4())
        selected_chat.value = {"id": new_chat["id"], "title": new_chat["title"]}

    messages.value = [
        *messages.value,
        user_message,
    ]
    # The part below can be replaced with a call to your own
    response = ai_client.chat(
        model="deepseek-r1:8b",
        # our MessageDict is compatible with the OpenAI types
        messages=messages.value,
        stream=True,
    )
    # start with an empty reply message, so we render and empty message in the chat
    # while the AI is thinking
    messages.value = [*messages.value, {"role": "assistant", "created": datetime.datetime.now(), "content": "", "chain_of_reason": None}]
    # and update it with the response
    async for chunk in await response:
        if chunk.done_reason == "stop":
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
        message_content = messages.value[-1]["content"]
        chain_of_reason = messages.value[-1]["chain_of_reason"] or ""
        if thinking:
            chain_of_reason += delta
        else:
            message_content += delta
        updated_message: MessageDict = {
            "role": "assistant",
            "created": messages.value[-1]["created"],
            "content": message_content,
            "chain_of_reason": chain_of_reason,
        }
        # replace the last message element with the appended content
        # which will update the UI
        messages.value = [*messages.value[:-1], updated_message]

    assert selected_chat.value is not None
    await create_message(selected_chat.value["id"], **user_message)
    await create_message(selected_chat.value["id"], **updated_message)


@solara.component
def Page():
    init_task = solara.lab.use_task(init, dependencies=[selected_chat.value])
    empty_chat = selected_chat.value is None or len(messages.value) == 0
    if init_task.pending:
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
                    for item in messages.value:
                        with solara.lab.ChatMessage(
                            user=item["role"] == "user",
                            avatar=False,
                            name="Deepseek" if item["role"] == "assistant" else "User",
                            color="rgba(0,0,0, 0.06)" if item["role"] == "assistant" else "#ff991f",
                            avatar_background_color="primary" if item["role"] == "assistant" else None,
                            border_radius="20px",
                        ):
                            if item["chain_of_reason"] is not None:
                                with solara.Details(summary="Chain of Thought"):
                                    solara.Markdown(item["chain_of_reason"])
                            solara.Markdown(item["content"])
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
            with solara.v.ListItemGroup(v_model=str(selected_chat.value["id"] if selected_chat.value is not None else None), on_v_model=update_selected_chat):
                for chat in chats.value:
                    with solara.v.ListItem(value=str(chat["id"]), dense=True):
                        solara.v.ListItemTitle(children=[chat["title"]])
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
        new_details: ChatDict = {"id": selected_chat.value["id"], "title": title.value}
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