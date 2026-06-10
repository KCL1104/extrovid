"""Director chat: one conversational agent that operates the production via tools."""

from fastapi import APIRouter, Depends
from pydantic_ai.usage import UsageLimits
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.director_agent import DirectorDeps, director_agent
from app.api.deps import get_owned_project
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
    history_block = (
        "\nConversation so far:\n"
        + "".join(f"{t.role}: {t.content}\n" for t in history)
        if history
        else ""
    )
    prompt = (
        "Session (authoritative project state):\n"
        f"{state}\n"
        f"{history_block}\n"
        f"user: {body.message}"
    )

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
