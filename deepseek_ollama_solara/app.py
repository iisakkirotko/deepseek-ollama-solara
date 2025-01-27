from typing import List, cast

from typing_extensions import TypedDict

from ollama import AsyncClient

import solara
import solara.lab


class MessageDict(TypedDict):
    role: str  # "user" or "assistant"
    content: str
    chain_of_reason: str | None


messages: solara.Reactive[List[MessageDict]] = solara.reactive([])

ai_client = AsyncClient()

@solara.lab.task
async def promt_ai(message: str):
    thinking = False

    messages.value = [
        *messages.value,
        {"role": "user", "content": message, "chain_of_reason": None},
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
    messages.value = [*messages.value, {"role": "assistant", "content": "", "chain_of_reason": None}]
    # and update it with the response
    async for chunk in await response:
        if chunk.done_reason == "stop":
            return
        # replace the last message element with the appended content
        delta = chunk.message.content
        if "<think>" == delta:
            thinking = True
            continue
        if "</think>" == delta:
            thinking = False
            continue
        print("DELTA:", thinking, delta)
        assert delta is not None
        message_content = messages.value[-1]["content"]
        chain_of_reason = messages.value[-1]["chain_of_reason"] or ""
        if thinking:
            chain_of_reason += delta
        else:
            message_content += delta
        updated_message: MessageDict = {
            "role": "assistant",
            "content": message_content,
            "chain_of_reason": chain_of_reason,
        }
        # replace the last message element with the appended content
        # which will update the UI
        messages.value = [*messages.value[:-1], updated_message]


@solara.component
def Page():
    with solara.Column(
        style={"width": "100%", "height": "50vh" if len(messages.value) == 0 else "calc(100% - 44px)"},
    ):
        with solara.lab.ChatBox():
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
        solara.lab.ChatInput(send_callback=promt_ai, disabled=promt_ai.pending).key("input")
