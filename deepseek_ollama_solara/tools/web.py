from typing import TypedDict, cast

from duckduckgo_search import DDGS
from mediawiki import MediaWiki

from ..types import ToolResult


class SearchResult(TypedDict):
    title: str
    url: str | None
    content: str | None


async def search_duckduckgo(query: str, result_count: int = 5):
    with DDGS() as ddgs:
        try:
            results = ddgs.text(query, max_results=result_count)
        except Exception as e:
            return ToolResult(
                message=f"Attempted to search DuckDuckGo for '{query}', but an error occurred",
                content=f"Error: {e}"
            )
        if results:
            search_results = [
                SearchResult(
                    title=result.get("title", "No Title"),
                    url=result.get("href"),
                    content=result.get("body")
                ) for result in results]
            return ToolResult(
                message=f"Searched DuckDuckGo for '{query}'",
                content=search_results
            )
        else:
            return ToolResult(message=f"Searched DuckDuckGo for '{query}'", content=cast(list[SearchResult], []))
        

async def lookup_wikipedia(name: str):
    wikipedia = MediaWiki()
    try:
        wikipedia_page = wikipedia.page(title=name, auto_suggest=True)
        return ToolResult(
            message=f"[Looked up '{name}' on Wikipedia]({wikipedia_page.url})",
            content=SearchResult(
                title=wikipedia_page.title,
                url=wikipedia_page.url,
                content=wikipedia_page.content
            )
        )
    except Exception as e:
        return ToolResult(
            message=f"Attempted to look up '{name}' on Wikipedia, but an error occurred",
            content=f"Error: {e}"
        )
