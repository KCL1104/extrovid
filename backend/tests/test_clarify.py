"""Clarifying-questions flow — agent behavior, the /clarify endpoint, and the deterministic
folding of director Q&A answers into the prompt fed to the BriefAgent. All offline."""

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.brief_agent import brief_agent
from app.agents.clarify_agent import clarify_agent
from app.pipeline import orchestrator
from app.providers.mock_data import _user_text
from app.schemas.api import ClarifyAnswer, ClarifyResult

DETAILED_PROMPT = (
    "a 30s vertical ad for a coffee brand, warm cinematic style, golden-hour mood, "
    "set in a cozy mountain cabin kitchen at dawn, slow push-ins, ends on the logo"
)

# --------------------------------------------------------------------------- #
# agent level — explicit override for the ask / none paths
# --------------------------------------------------------------------------- #


def _clarify_args(ask: bool) -> dict:
    if not ask:
        return {"needs_clarification": False, "questions": [], "prompt_assessment": "all clear"}
    return {
        "needs_clarification": True,
        "questions": [
            {
                "id": "q-era",
                "question": "Which era should it be set in?",
                "why": "The era drives production design and wardrobe.",
                "options": ["1920s", "Present day"],
                "allow_custom": True,
            }
        ],
        "prompt_assessment": "Clear: subject. Missing: era.",
    }


async def test_clarify_agent_override_ask_path():
    def fn(messages, info: AgentInfo) -> ModelResponse:
        name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name=name, args=_clarify_args(True))])

    with clarify_agent.override(model=FunctionModel(fn)):
        out = (await clarify_agent.run("anything")).output
    assert isinstance(out, ClarifyResult)
    assert out.needs_clarification is True
    assert out.questions[0].id == "q-era"
    assert 2 <= len(out.questions[0].options) <= 4
    assert out.questions[0].allow_custom is True


async def test_clarify_agent_override_none_path():
    def fn(messages, info: AgentInfo) -> ModelResponse:
        name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name=name, args=_clarify_args(False))])

    with clarify_agent.override(model=FunctionModel(fn)):
        out = (await clarify_agent.run("anything")).output
    assert out.needs_clarification is False
    assert out.questions == []
    assert out.prompt_assessment


# --------------------------------------------------------------------------- #
# mock-model heuristics (what the running app does with USE_MOCK_LLM=true)
# --------------------------------------------------------------------------- #


async def test_mock_asks_for_vague_prompt():
    out = (await clarify_agent.run("a dog video")).output
    assert out.needs_clarification is True
    assert 1 <= len(out.questions) <= 4
    for q in out.questions:
        assert q.id and q.question and q.why
        assert 2 <= len(q.options) <= 4


async def test_mock_skips_detailed_prompt():
    out = (await clarify_agent.run(DETAILED_PROMPT)).output
    assert out.needs_clarification is False
    assert out.questions == []


async def test_mock_force_markers():
    forced_none = (await clarify_agent.run("a dog video CLARIFY_FORCE_NONE")).output
    assert forced_none.needs_clarification is False
    forced_ask = (await clarify_agent.run(DETAILED_PROMPT + " CLARIFY_FORCE_ASK")).output
    assert forced_ask.needs_clarification is True


# --------------------------------------------------------------------------- #
# endpoint
# --------------------------------------------------------------------------- #


async def test_clarify_endpoint_is_stateless(client):
    pid = (await client.post("/api/projects", json={"title": "Clarify"})).json()["id"]
    r = await client.post(f"/api/projects/{pid}/clarify", json={"raw_prompt": "a dog video"})
    assert r.status_code == 200
    body = r.json()
    assert body["needs_clarification"] is True
    assert len(body["questions"]) == 3
    assert {"id", "question", "why", "options", "allow_custom"} <= set(body["questions"][0])
    assert body["prompt_assessment"]
    # stateless: nothing was persisted by the call
    assert (await client.get(f"/api/projects/{pid}/script")).json() == []
    assert (await client.get(f"/api/projects/{pid}/storyboard")).json() == []

    r2 = await client.post(
        f"/api/projects/{pid}/clarify", json={"raw_prompt": "a dog video CLARIFY_FORCE_NONE"}
    )
    assert r2.status_code == 200
    assert r2.json()["needs_clarification"] is False
    assert r2.json()["questions"] == []


# --------------------------------------------------------------------------- #
# folding answers into the brief prompt
# --------------------------------------------------------------------------- #


def test_fold_clarifications_format_and_skips():
    answers = [
        ClarifyAnswer(question_id="q1", question="Which era?", answer="1920s Paris"),
        ClarifyAnswer(question_id="q2", question="What mood?", answer="   "),  # skipped
        ClarifyAnswer(question_id="q3", question="Ending?", answer=""),  # skipped
    ]
    folded = orchestrator.fold_clarifications("a dog video", answers)
    assert folded == (
        "a dog video\n\nCreative direction (director Q&A):\n- Which era? -> 1920s Paris\n"
    )
    # no usable answers -> prompt untouched
    assert orchestrator.fold_clarifications("a dog video", answers[1:]) == "a dog video"
    assert orchestrator.fold_clarifications("a dog video", None) == "a dog video"


async def test_run_brief_folds_answers_into_agent_prompt():
    captured: dict = {}

    def fn(messages, info: AgentInfo) -> ModelResponse:
        captured["prompt"] = _user_text(messages)
        name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name=name, args={"raw_prompt": "ok"})])

    answers = [ClarifyAnswer(question_id="q1", question="Which era?", answer="1920s Paris")]
    with brief_agent.override(model=FunctionModel(fn)):
        await orchestrator.run_brief("a dog video", answers)
    assert captured["prompt"].startswith("a dog video")
    assert "Creative direction (director Q&A):" in captured["prompt"]
    assert "- Which era? -> 1920s Paris" in captured["prompt"]

    with brief_agent.override(model=FunctionModel(fn)):
        await orchestrator.run_brief("a dog video")
    assert captured["prompt"] == "a dog video"  # backwards compatible: verbatim


async def test_brief_endpoint_accepts_clarifications(client):
    pid = (await client.post("/api/projects", json={"title": "Fold"})).json()["id"]
    r = await client.post(
        f"/api/projects/{pid}/brief",
        json={
            "raw_prompt": "a 20s teaser",
            "clarifications": [
                {"question_id": "q-style", "question": "What visual style?", "answer": "Film noir"}
            ],
        },
    )
    assert r.status_code == 200
    # the mock brief echoes the prompt it received -> proves the answers were folded in
    assert "- What visual style? -> Film noir" in r.json()["raw_prompt"]


async def test_run_endpoint_accepts_clarifications(client):
    pid = (await client.post("/api/projects", json={"title": "FoldRun"})).json()["id"]
    r = await client.post(
        f"/api/projects/{pid}/run",
        json={
            "raw_prompt": "a 20s teaser",
            "clarifications": [
                {"question_id": "q-mood", "question": "What mood?", "answer": "Bold and energetic"}
            ],
        },
    )
    assert r.status_code == 200
    assert "- What mood? -> Bold and energetic" in r.json()["brief"]["raw_prompt"]
    # and without clarifications stays backwards compatible
    r2 = await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    assert r2.status_code == 200
