"""Long-source import: text beyond one planning prompt becomes scenes + cast.

The ViMax novel2movie ladder, scoped for extrovid (docs/vimax-research.md E1):
compress (only when the source is large) -> autoregressive event extraction with
per-event persistence (resume = continue past max(index)) -> 1-5 scenes per event ->
cast upsert. The FAISS/reranker RAG layer is deliberately deferred — for sources up
to a few hundred KB the compressed text carries enough; embeddings arrive only if
book-length imports become a real workload.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.cast_agent import cast_agent
from app.agents.source_agent import compressor_agent, event_agent, scene_import_agent
from app.core.logging import log
from app.models.enums import MAX_SCENES, ProjectStatus
from app.models.project import Project
from app.models.source import SourceEvent
from app.schemas.pipeline import SceneDraft, ScriptDraft
from app.services import memory_service, planning_service

CHUNK_CHARS = 12_000  # sized for Qwen's window with room for instructions
CHUNK_OVERLAP = 1_500
MAX_EVENTS = 20  # runaway backstop, far above any real short-form import


async def _compress(text: str) -> str:
    """Map-reduce compression; skipped entirely for sources that fit one prompt."""
    if len(text) <= CHUNK_CHARS:
        return text
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + CHUNK_CHARS])
        start += CHUNK_CHARS - CHUNK_OVERLAP
    compressed_parts = [
        (await compressor_agent.run(f"Compress this chunk:\n{c}")).output for c in chunks
    ]
    joined = "\n".join(compressed_parts)
    if len(compressed_parts) == 1:
        return joined
    # aggregate pass resolves the overlap duplicates (later chunk wins)
    return (
        await compressor_agent.run(
            "Splice these overlapping compressed chunks into one coherent retelling, "
            f"resolving duplicated boundaries (keep the later version):\n{joined}"
        )
    ).output


async def list_events(session: AsyncSession, project_id: str) -> list[SourceEvent]:
    return list(
        (
            await session.execute(
                select(SourceEvent)
                .where(SourceEvent.project_id == project_id)
                .order_by(SourceEvent.index)
            )
        )
        .scalars()
        .all()
    )


async def _extract_events(
    session: AsyncSession, project_id: str, source: str
) -> list[SourceEvent]:
    """One event per LLM call until is_last, persisted as each lands (crash-resume:
    a re-run continues from the first missing index)."""
    events = await list_events(session, project_id)
    while not (events and events[-1].is_last) and len(events) < MAX_EVENTS:
        idx = len(events)
        prior = "\n".join(f"[{e.index}] {e.description}" for e in events) or "(none yet)"
        result = await event_agent.run(
            f"EVENT_INDEX={idx}\nPreviously extracted events:\n{prior}\n\nSource:\n{source}",
            deps=idx,
        )
        draft = result.output
        row = SourceEvent(
            project_id=project_id,
            index=draft.index,
            description=draft.description,
            process_chain=draft.process_chain,
            is_last=draft.is_last,
        )
        session.add(row)
        await session.commit()  # per-event checkpoint
        events.append(row)
    return events


async def import_source(session: AsyncSession, project_id: str, text: str) -> dict:
    """text -> SourceEvents -> scenes (persisted as the project's script) + cast."""
    source = await _compress(text)

    events = await _extract_events(session, project_id, source)

    # each event becomes 1-5 scenes; orders renumbered globally in Python
    all_scenes: list[SceneDraft] = []
    for event in events:
        if len(all_scenes) >= MAX_SCENES:
            log.warning("import.scenes_truncated project=%s at=%d", project_id, len(all_scenes))
            break
        steps = "; ".join(str(s) for s in event.process_chain)
        result = await scene_import_agent.run(
            f"EVENT_INDEX={event.index}\nEvent: {event.description}\nCausal steps: {steps}"
        )
        for scene in result.output.scenes:
            if len(all_scenes) >= MAX_SCENES:
                break
            all_scenes.append(scene.model_copy(update={"order": len(all_scenes)}))

    script = ScriptDraft(
        logline=(events[0].description if events else "imported source")[:200],
        scenes=all_scenes,
    )
    await planning_service.replace_scenes(session, project_id, script)

    # cast from the compressed source — canonical-name grouping does the alignment
    cast = (await cast_agent.run(f"Extract the cast from this source:\n{source}")).output
    profiles = await memory_service.upsert_cast(session, project_id, cast.characters)

    project = await session.get(Project, project_id)
    if project and project.status == ProjectStatus.DRAFT.value:
        project.status = ProjectStatus.SCRIPTED.value
        session.add(project)
    await session.commit()
    log.info(
        "import.source project=%s events=%d scenes=%d cast=%d",
        project_id,
        len(events),
        len(all_scenes),
        len(profiles),
    )
    return {
        "events": len(events),
        "scenes": len(all_scenes),
        "cast": [p.name for p in profiles],
        "logline": script.logline,
    }


async def clear_source(session: AsyncSession, project_id: str) -> None:
    await session.execute(delete(SourceEvent).where(SourceEvent.project_id == project_id))
    await session.commit()
