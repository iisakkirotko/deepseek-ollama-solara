import json
from typing import Callable

import solara
from reacton.ipyvuetify import use_event

from .database import update_chat
from .types import ChatDict, Message


@solara.component
def ChatMessage(
    message: Message,
    model_name: str,
):
    if message["role"] == "tool":
        tool_result = json.loads(message["content"])
        with solara.Column(align="flex-start"):
            solara.Markdown(tool_result["message"])
    else:
        with solara.lab.ChatMessage(
            user=message["role"] == "user",
            avatar=False,
            name=model_name if message["role"] == "assistant" else "User",
            color="rgba(0,0,0, 0.06)" if message["role"] == "assistant" else "#ff991f",
            avatar_background_color="primary" if message["role"] == "assistant" else None,
            border_radius="20px",
        ):
            if message["chain_of_reason"] is not None:
                with solara.Details(summary="Chain of Thought"):
                    solara.Markdown(message["chain_of_reason"] or "")
            solara.Markdown(message["content"] or "")


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


@solara.component
def ChatTitle(selected_chat: solara.Reactive[ChatDict]):
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
        new_details: ChatDict = {
            "id": selected_chat.value["id"],
            "title": title.value,
            "model": selected_chat.value["model"],
        }
        selected_chat.value = new_details

    save_title = solara.lab.use_task(_save_title, dependencies=None)

    with solara.Div(
        style={
            "display": "flex",
            "justify-content": "flex-start",
            "flex-shrink": "0",
            "max-width": "600px",
            "overflow": "hidden",
        }
    ):
        if editing.value:
            solara.InputText(label="Chat Title", value=title)
            IconButton("check", on_click=lambda: save_title())
            IconButton("cancel", on_click=cancel_editing)

        else:
            H3(
                children=[title.value],
                on_click=start_editing,
                style={"cursor": "pointer", "flex": 1},
            )
