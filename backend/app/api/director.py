"""Director chat: one conversational agent that operates the production via tools."""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)
from pydantic_ai.usage import UsageLimits
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.director_agent import DirectorDeps, director_agent
from app.api.deps import get_owned_project
from app.core import event_bus
from app.core.auth import AuthCtx, current_auth
from app.core.db import get_session
from app.models.director import DirectorTurn
from app.schemas.api import DirectorRequest, DirectorResponse
from app.services import project_state

router = APIRouter(
    prefix="/projects/{project_id}", tags=["director"], dependencies=[Depends(get_owned_project)]
)

_HISTORY_TURNS = 12
_MAX_TOOL_PASSES = 8


def _director_prompt(state, history: list[DirectorTurn], message: str) -> str:
    history_block = (
        "\nConversation so far:\n" + "".join(f"{t.role}: {t.content}\n" for t in history)
        if history
        else ""
    )
    return (
        "Session (authoritative project state):\n"
        f"{state}\n"
        f"{history_block}\n"
        f"user: {message}"
    )


async def _recent_turns(session: AsyncSession, project_id: str) -> list[DirectorTurn]:
    rows = (
        (
            await session.execute(
                select(DirectorTurn)
                .where(DirectorTurn.project_id == project_id)
                .order_by(DirectorTurn.created_at.desc())
                .limit(_HISTORY_TURNS)
            )
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


@router.get("/director/turns")
async def director_history(project_id: str, session: AsyncSession = Depends(get_session)):
    """The chat history (oldest first) so the panel survives reloads."""
    turns = await _recent_turns(session, project_id)
    return [
        {"id": t.id, "role": t.role, "content": t.content, "created_at": t.created_at.isoformat()}
        for t in turns
    ]


@router.post("/director", response_model=DirectorResponse)
async def director_chat(
    project_id: str,
    body: DirectorRequest,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """One director turn. Continuity = per-turn state snapshot + recent flat-text
    history (ViMax's resume model) — never transcript replay."""
    state = await project_state.snapshot(session, project_id)
    history = await _recent_turns(session, project_id)
    prompt = _director_prompt(state, history, body.message)

    deps = DirectorDeps(session=session, project_id=project_id, auth=auth)
    result = await director_agent.run(
        prompt, deps=deps, usage_limits=UsageLimits(request_limit=_MAX_TOOL_PASSES)
    )
    reply = result.output

    session.add(DirectorTurn(project_id=project_id, role="user", content=body.message))
    session.add(DirectorTurn(project_id=project_id, role="assistant", content=reply))
    await session.commit()

    return DirectorResponse(
        reply=reply,
        actions=deps.actions,
        state=await project_state.snapshot(session, project_id),
    )


@router.post("/director/stream")
async def director_stream(
    project_id: str,
    body: DirectorRequest,
    auth: AuthCtx = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
):
    """Same director turn as POST /director, streamed over SSE: `text_delta` frames as the
    model writes its reply, `tool_start`/`tool_result` as it works, then a final `done` with
    the full reply + actions + fresh state. Model-request nodes stream token deltas; both the
    mock (FunctionModel stream_function) and the real Qwen (OpenAI-compatible) provider support it."""
    state = await project_state.snapshot(session, project_id)
    history = await _recent_turns(session, project_id)
    prompt = _director_prompt(state, history, body.message)
    deps = DirectorDeps(session=session, project_id=project_id, auth=auth)
    limits = UsageLimits(request_limit=_MAX_TOOL_PASSES)

    async def gen():
        reply = ""
        try:
            async with director_agent.iter(prompt, deps=deps, usage_limits=limits) as run:
                async for node in run:
                    if Agent.is_model_request_node(node):
                        # stream the model's text tokens as it writes the reply
                        async with node.stream(run.ctx) as request_stream:
                            async for event in request_stream:
                                if (
                                    isinstance(event, PartStartEvent)
                                    and isinstance(event.part, TextPart)
                                    and event.part.content
                                ):
                                    yield event_bus.sse(
                                        {"type": "text_delta", "delta": event.part.content}
                                    )
                                elif isinstance(event, PartDeltaEvent) and isinstance(
                                    event.delta, TextPartDelta
                                ):
                                    yield event_bus.sse(
                                        {"type": "text_delta", "delta": event.delta.content_delta}
                                    )
                    elif Agent.is_call_tools_node(node):
                        async with node.stream(run.ctx) as stream:
                            async for event in stream:
                                if isinstance(event, FunctionToolCallEvent):
                                    # carry which shot/scene the call touches so the board can
                                    # highlight the affected card(s) as the director works
                                    raw = event.part.args
                                    if isinstance(raw, str):
                                        try:
                                            raw = json.loads(raw)
                                        except (ValueError, TypeError):
                                            raw = {}
                                    ref = (
                                        {
                                            k: raw[k]
                                            for k in ("shot_id", "scene_order", "target")
                                            if k in raw
                                        }
                                        if isinstance(raw, dict)
                                        else {}
                                    )
                                    yield event_bus.sse(
                                        {
                                            "type": "tool_start",
                                            "tool": event.part.tool_name,
                                            "ref": ref,
                                        }
                                    )
                                elif isinstance(event, FunctionToolResultEvent):
                                    part = event.part
                                    yield event_bus.sse(
                                        {
                                            "type": "tool_result",
                                            "tool": getattr(part, "tool_name", ""),
                                            "error": getattr(part, "part_kind", "")
                                            == "retry-prompt",
                                        }
                                    )
                reply = run.result.output if run.result else ""
        except Exception as exc:  # noqa: BLE001 - surface a clean error frame, never 500 mid-stream
            yield event_bus.sse({"type": "error", "message": str(exc)})

        session.add(DirectorTurn(project_id=project_id, role="user", content=body.message))
        session.add(DirectorTurn(project_id=project_id, role="assistant", content=reply))
        await session.commit()
        yield event_bus.sse(
            {
                "type": "done",
                "reply": reply,
                "actions": deps.actions,
                "state": await project_state.snapshot(session, project_id),
            }
        )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
