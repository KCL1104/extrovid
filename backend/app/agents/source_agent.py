"""Long-source import agents: compression -> autoregressive events -> scenes.

The novel2movie planning ladder from ViMax (docs/vimax-research.md E1), ported to
PydanticAI: a lossy global summary preserves structure, events are extracted ONE PER
CALL with the full prior-event context until the model sets is_last (unbounded length
without unbounded context), and an index-echo output validator turns ordering drift
into a ModelRetry instead of silent corruption.
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext

from app.core.config import get_settings
from app.providers.model_factory import get_model
from app.schemas.pipeline import SceneDraft

COMPRESS_SYSTEM = """You compress a long narrative source (novel chapter, script,
transcript) into a faithful, much shorter retelling. Preserve every key plot
development, character, and the strongest lines of dialogue. Where chunk boundaries
overlap, resolve duplicates by keeping the LATER chunk's version. Write plain prose,
no commentary. Output only the compressed text."""

EVENT_SYSTEM = """You segment a narrative into dramatic EVENTS, one per call.
An event is a unit of dramatic purpose, not of place — a chase that moves through a
market, alleys, and a rooftop is ONE event if it serves one purpose.
You are given the source, all previously extracted events, and EVENT_INDEX — the index
your event MUST carry. Continue from where the previous events stopped. Set
is_last=true only when your event reaches the source's ending. process_chain lists the
event's causal steps in order, each one concrete and filmable.
Return only the structured object."""

SCENE_IMPORT_SYSTEM = """You adapt ONE narrative event into 1-5 screenplay scenes.
Each scene is a single time and place; start a new scene when either changes. Ground
every scene in the event's content — every line of dialogue must have a basis in it.
Scene orders start at 0 within this event (global numbering is handled elsewhere).
Estimate each scene's duration in seconds (10-60s). Return only the structured
object.""" + """
Writing rules: no metaphors (video models render them literally); concrete observable
action only; name subjects explicitly in every beat."""


class SourceEventDraft(BaseModel):
    index: int = Field(..., ge=0, description="MUST equal the EVENT_INDEX you were given.")
    is_last: bool = Field(..., description="True only when this event reaches the ending.")
    description: str = Field(..., min_length=1)
    process_chain: list[str] = Field(
        ..., min_length=1, description="The event's causal steps, in order, each filmable."
    )


class ImportedScenes(BaseModel):
    event_index: int = Field(..., ge=0)
    scenes: list[SceneDraft] = Field(..., min_length=1, max_length=5)


compressor_agent = Agent(
    get_model(),
    output_type=str,
    system_prompt=COMPRESS_SYSTEM,
    retries=get_settings().llm_retries,
)

event_agent = Agent(
    get_model(),
    output_type=SourceEventDraft,
    deps_type=int,  # the expected event index
    system_prompt=EVENT_SYSTEM,
    retries=2,
)


@event_agent.output_validator
async def _index_echo(ctx: RunContext[int], out: SourceEventDraft) -> SourceEventDraft:
    # ViMax's index-echo assert: ordering drift becomes a retry, never corruption
    if out.index != ctx.deps:
        raise ModelRetry(f"index must be {ctx.deps} (you returned {out.index}).")
    return out


scene_import_agent = Agent(
    get_model(),
    output_type=ImportedScenes,
    system_prompt=SCENE_IMPORT_SYSTEM,
    retries=2,
)
