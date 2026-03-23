"""
/chat — Claude-powered assistant endpoint.

Accepts a conversation history and returns the next assistant message.
The agent has three live tools:
  • search_papers   — keyword / title search on OpenAlex
  • resolve_doi     — look up a specific DOI and return metadata
  • search_authors  — find an OpenAlex author profile by name
"""

import json
import logging
from typing import Annotated

import httpx
from anthropic import AsyncAnthropic, BadRequestError, APIStatusError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.config import get_settings
from app.deps import get_current_user
from app.services.openalex import get_work_by_doi, search_authors

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are Citey Assistant, a friendly helper embedded in Citey — \
a web application that helps academic researchers track when their published papers are cited.

Your job is to help users:
1. Add their papers to Citey by DOI (e.g. 10.1038/s41586-021-03819-2)
2. Find the correct DOI for a paper they've published
3. Import all their papers at once via their OpenAlex author profile
4. Understand how citation tracking works
5. Troubleshoot common issues (paper not found, author mismatch, etc.)

About Citey:
- Citey monitors OpenAlex and Semantic Scholar for new citations to a user's papers
- Users track papers by adding a DOI on the dashboard ("Add Paper" button)
- Users can also bulk-import via "Import Papers" — search your name, select your profile
- New citations trigger an email digest
- The dashboard shows tracked papers and new citation notifications

A DOI looks like: 10.1038/s41586-021-03819-2 or https://doi.org/10.1038/s41586-021-03819-2
Both formats are accepted by Citey.

If a user doesn't know their DOI, use the search_papers tool to find it. \
If they provide one, use resolve_doi to confirm it's correct before they add it.

Be concise, warm, and direct. When you find a paper's DOI, present it clearly \
and ask the user to confirm it's the right one."""

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "name": "search_papers",
        "description": (
            "Search OpenAlex for academic papers by title keywords or topic. "
            "Use this when a user describes a paper but doesn't know its DOI."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Title keywords or topic to search for",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "resolve_doi",
        "description": (
            "Look up a specific paper by DOI. Returns title, authors, and year. "
            "Use this to verify a DOI the user has provided."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doi": {
                    "type": "string",
                    "description": "The DOI to look up (e.g. 10.1038/s41586-021-03819-2)",
                }
            },
            "required": ["doi"],
        },
    },
    {
        "name": "search_authors",
        "description": (
            "Search for an academic author on OpenAlex by name. "
            "Returns name, works count, and affiliations. "
            "Use this to help users find their OpenAlex author profile for bulk import."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The author's full name to search for",
                }
            },
            "required": ["name"],
        },
    },
]

_OA_BASE = "https://api.openalex.org"
_OA_HEADERS = {"User-Agent": "Citey/0.1 (mailto:support@citey.app)"}

# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


async def _run_tool(name: str, tool_input: dict) -> str:
    """Execute a named tool and return a JSON string result."""
    try:
        if name == "resolve_doi":
            work = await get_work_by_doi(tool_input["doi"])
            if not work:
                return json.dumps({"found": False, "message": "No paper found for that DOI."})
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in work.get("authorships", [])[:5]
            ]
            return json.dumps({
                "found": True,
                "title": work.get("title", "Unknown title"),
                "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
                "year": work.get("publication_year"),
                "authors": [a for a in authors if a],
            })

        if name == "search_papers":
            async with httpx.AsyncClient(headers=_OA_HEADERS, timeout=15.0) as client:
                resp = await client.get(
                    f"{_OA_BASE}/works",
                    params={
                        "search": tool_input["query"],
                        "per_page": 5,
                        "mailto": "support@citey.app",
                    },
                )
            if resp.status_code != 200:
                return json.dumps({"results": [], "error": "Search unavailable."})
            results = []
            for w in resp.json().get("results", []):
                doi_raw = (w.get("doi") or "").replace("https://doi.org/", "")
                results.append({
                    "title": w.get("title", ""),
                    "doi": doi_raw,
                    "year": w.get("publication_year"),
                    "authors": [
                        a.get("author", {}).get("display_name", "")
                        for a in w.get("authorships", [])[:3]
                    ],
                })
            return json.dumps({"results": results})

        if name == "search_authors":
            raw = await search_authors(tool_input["name"])
            candidates = []
            for a in raw[:5]:
                affiliations = []
                for aff in a.get("affiliations", [])[:2]:
                    inst = aff.get("institution", {})
                    if inst.get("display_name"):
                        affiliations.append(inst["display_name"])
                candidates.append({
                    "id": a.get("id", "").replace("https://openalex.org/", ""),
                    "name": a.get("display_name", ""),
                    "works_count": a.get("works_count", 0),
                    "affiliations": affiliations,
                })
            return json.dumps({"results": candidates})

    except Exception as exc:
        logger.error("Tool %s raised an error: %s", name, exc)
        return json.dumps({"error": str(exc)})

    return json.dumps({"error": "Unknown tool"})


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    uid: Annotated[str, Depends(get_current_user)],
) -> ChatResponse:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat assistant is not configured (missing API key).",
        )

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages: list[dict] = [{"role": m.role, "content": m.content} for m in body.messages]

    try:
        # Agentic loop — keep going until Claude stops requesting tools (max 5 rounds)
        for _ in range(5):
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                text = " ".join(
                    block.text for block in response.content if hasattr(block, "text")
                ).strip()
                return ChatResponse(message=text)

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.info("Chat tool call: %s(%s)", block.name, block.input)
                        result = await _run_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                continue

            break  # unexpected stop reason

    except BadRequestError as exc:
        error_body = exc.response.json() if exc.response else {}
        message = (error_body.get("error") or {}).get("message", str(exc))
        if "credit balance is too low" in message:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The assistant is temporarily unavailable. Please try again later.",
            ) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc
    except APIStatusError as exc:
        logger.error("Anthropic API error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is temporarily unavailable. Please try again later.",
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Assistant did not produce a response.",
    )
