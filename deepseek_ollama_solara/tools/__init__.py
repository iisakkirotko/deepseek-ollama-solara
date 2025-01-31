from typing import Any, Coroutine, Callable
from ..types import ToolResult
from .web import search_duckduckgo, lookup_wikipedia

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_duckduckgo",
            "description": "Search for information on the internet using the search engine DuckDuckGo",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                    "result_count": {
                        "type": "integer",
                        "description": "The number of results to return",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_wikipedia",
            "description": "Look up an article on Wikipedia.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the article to look up.",
                    },
                },
                "required": ["name"],
            },
        },
    },
]

# Note: Tools should be async
tool_callables: dict[str, Callable[[Any], Coroutine[Any, Any, ToolResult]]] = {
    "search_duckduckgo": search_duckduckgo,
    "lookup_wikipedia": lookup_wikipedia,
}