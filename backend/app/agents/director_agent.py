"""DirectorAgent: one conversational agent driving the whole production via tools.

The ViMax agent-loop pattern on PydanticAI's native tool loop (docs/vimax-research.md
D3): tools wrap existing services (never HTTP), the prompt carries a grounding
contract + a stage gate, and per-turn continuity comes from the project snapshot
rather than transcript replay.
"""

from dataclasses import dataclass, field

from pydantic_ai import Agent, RunContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthCtx
from app.core.config import get_settings
from app.providers.model_factory import get_model

DIRECTOR_SYSTEM = """You are the director of an AI video production, operating the
production through tools. The user is your client.

Workflow (stages build on each other): brief -> script -> cast -> visual development ->
storyboard (with keyframes) -> takes (generation) -> review -> rough cut.

GROUNDING CONTRACT: never claim that planning, generation, or edits happened unless a
tool result in THIS conversation proves it. Never claim a render started unless
generate_shot/generate_scene returned a job. When unsure what exists, call
get_project_state first — the Session block below is the authoritative state.

STAGE GATE: when planning is complete and the user did not explicitly ask to generate
or render, call no further tools — report the plan state and ask whether to revise or
start generating. Prefer revise_artifact for small changes over regenerating stages;
regeneration destroys downstream work, revision marks it stale instead.

When the client asks for the WHOLE film ("make it all", "finish the video"), prefer
produce_project over shot-by-shot tools — it runs every remaining stage and pauses at
the keyframe checkpoint for their review.

Be concise and concrete in replies: what you did (per tool results), what it changed,
and the single most useful next step."""


@dataclass
class DirectorDeps:
    session: AsyncSession
    project_id: str
    auth: AuthCtx
    actions: list[dict] = field(default_factory=list)


director_agent = Agent(
    get_model(),
    deps_type=DirectorDeps,
    system_prompt=DIRECTOR_SYSTEM,
    retries=get_settings().llm_retries,
)


def _record(ctx: RunContext[DirectorDeps], tool: str, args: dict, summary: str) -> None:
    ctx.deps.actions.append({"tool": tool, "args": args, "result_summary": summary[:300]})


@director_agent.tool
async def get_project_state(ctx: RunContext[DirectorDeps]) -> dict:
    """The authoritative project checklist: counts of scenes/shots/takes, staleness,
    cast and portrait status, jobs in flight. Call before claiming anything exists."""
    from app.services import project_state

    state = await project_state.snapshot(ctx.deps.session, ctx.deps.project_id)
    _record(ctx, "get_project_state", {}, f"{state['shots']} shots, {state['scenes']} scenes")
    return state


@director_agent.tool
async def get_storyboard(ctx: RunContext[DirectorDeps]) -> list[dict]:
    """The shot list: order, scene, purpose, duration, cast lock, staleness, keyframe."""
    from app.services import planning_service

    shots = await planning_service.list_shots(ctx.deps.session, ctx.deps.project_id)
    _record(ctx, "get_storyboard", {}, f"{len(shots)} shots")
    return [
        {
            "shot_id": s.id,
            "order": s.order,
            "scene_order": s.scene_order,
            "purpose": s.purpose,
            "duration_sec": s.duration_sec,
            "character_id": s.character_id,
            "has_keyframe": bool(s.keyframe_frame_id),
            "stale": s.stale,
        }
        for s in shots
    ]


@director_agent.tool
async def revise_artifact(ctx: RunContext[DirectorDeps], target: str, instruction: str) -> dict:
    """Revise ONE artifact in place. target = 'scene:{id}' | 'visual_brief:{scene_id}'
    | 'shot:{id}' (real ids from get_storyboard/get_project_state — never invented).
    Downstream artifacts are marked stale, not destroyed."""
    from app.services import revise_service

    revised = await revise_service.revise(
        ctx.deps.session, ctx.deps.project_id, target, instruction
    )
    _record(ctx, "revise_artifact", {"target": target, "instruction": instruction}, "revised")
    return {"target": target, "revised": revised.model_dump(mode="json")}


@director_agent.tool
async def generate_shot(
    ctx: RunContext[DirectorDeps],
    shot_id: str,
    continue_from_previous: bool = False,
    num_takes: int = 1,
) -> dict:
    """Submit generation for one shot (num_takes 1-4 fans out best-of-N).
    Returns the job — generation is asynchronous; do not claim the video exists."""
    from app.models.shot import Shot
    from app.services import generate_service

    shot = await ctx.deps.session.get(Shot, shot_id)
    if shot is None or shot.project_id != ctx.deps.project_id:
        return {"error": "shot not found — use shot_id values from get_storyboard"}
    takes = await generate_service.submit_shot_batch(
        ctx.deps.session,
        ctx.deps.project_id,
        shot,
        auth=ctx.deps.auth,
        num_takes=max(1, min(4, num_takes)),
        continue_from_previous=continue_from_previous,
    )
    version, job = takes[0]
    _record(
        ctx,
        "generate_shot",
        {"shot_id": shot_id, "num_takes": num_takes},
        f"job {job.status}: {version.routing_note}",
    )
    return {
        "submitted_takes": len(takes),
        "job_status": job.status,
        "routing_note": version.routing_note,
    }


@director_agent.tool
async def generate_scene(
    ctx: RunContext[DirectorDeps], scene_order: int, continue_from_previous: bool = False
) -> dict:
    """Render every shot of one scene. With continue_from_previous, later shots queue
    until their upstream take lands (the reconciler dispatches them)."""
    from app.services import generate_service, planning_service

    shots = [
        s
        for s in await planning_service.list_shots(ctx.deps.session, ctx.deps.project_id)
        if s.scene_order == scene_order
    ]
    if not shots:
        return {"error": f"no shots in scene {scene_order}"}
    takes = await generate_service.submit_scene_batch(
        ctx.deps.session,
        ctx.deps.project_id,
        shots,
        auth=ctx.deps.auth,
        continue_from_previous=continue_from_previous,
    )
    _record(ctx, "generate_scene", {"scene_order": scene_order}, f"{len(takes)} takes submitted")
    return {"submitted_takes": len(takes), "shots": len(shots)}


@director_agent.tool
async def get_review(ctx: RunContext[DirectorDeps], shot_id: str) -> dict:
    """The latest finished take's AI review (score, verdict, notes, fix suggestions,
    continuity notes) for a shot."""
    from sqlalchemy import select

    from app.models.generation import ShotVersion

    versions = (
        (
            await ctx.deps.session.execute(
                select(ShotVersion).where(
                    ShotVersion.shot_id == shot_id, ShotVersion.output_asset_id.is_not(None)
                )
            )
        )
        .scalars()
        .all()
    )
    if not versions:
        return {"error": "no finished take for that shot yet"}
    v = next((x for x in versions if x.selected), versions[-1])
    _record(ctx, "get_review", {"shot_id": shot_id}, f"score={v.score}")
    return {"version_id": v.id, "score": v.score, "review": v.review, "selected": v.selected}


@director_agent.tool
async def produce_project(ctx: RunContext[DirectorDeps], mode: str = "gated") -> dict:
    """Run EVERY remaining pipeline stage in one go: portraits -> keyframes -> shot
    videos -> voiceovers -> rough cut. Each stage only does still-missing work, so
    re-running resumes a paused run. mode='gated' (default) pauses after newly created
    keyframes so the client can review the board before video budget is spent;
    mode='auto' runs straight through. Asynchronous and long-running — report that the
    run STARTED (and its current stage), never that the film is done."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.project import Project
    from app.services import produce_service, review_gate_service

    project = await ctx.deps.session.get(Project, ctx.deps.project_id)
    blockers = review_gate_service.project_generation_blockers(project)
    blockers += await review_gate_service.budget_blockers(ctx.deps.session, project)
    if blockers:
        return {"error": "blocked", "blockers": blockers}
    st = produce_service.start(
        ctx.deps.project_id,
        auth=ctx.deps.auth,
        session_factory=async_sessionmaker(ctx.deps.session.bind, expire_on_commit=False),
        mode="auto" if mode == "auto" else "gated",
    )
    _record(ctx, "produce_project", {"mode": mode}, f"{st['state']} at {st.get('stage')}")
    return st


@director_agent.tool
async def assemble_rough_cut(ctx: RunContext[DirectorDeps]) -> dict:
    """Assemble the rough cut from each shot's selected/latest take (needs finished
    takes — reports missing dependencies instead of pretending it started)."""
    from app.services import project_state, rough_cut_service

    state = await project_state.snapshot(ctx.deps.session, ctx.deps.project_id)
    missing = project_state.missing_for(state, "rough_cut")
    if missing:
        return {"error": "dependency_missing", "missing": missing}
    seq = await rough_cut_service.assemble_rough_cut(ctx.deps.session, ctx.deps.project_id)
    _record(ctx, "assemble_rough_cut", {}, f"rough cut {seq.status}")
    return {"rough_cut_id": seq.id, "status": seq.status}
