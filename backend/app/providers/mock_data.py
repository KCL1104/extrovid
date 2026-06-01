"""Deterministic fake LLM responses for ``USE_MOCK_LLM=true``.

A single ``FunctionModel`` callable that inspects the expected output schema and returns a
canned object that passes EVERY validator (schema + agent output validators), so the whole
pipeline runs end-to-end with no network. This is the single source of fake data shared by
the mocked-API path and the test suite.

Markers the orchestrator embeds in prompts let the mock stay consistent with the brief:
- ``TARGET_DURATION_SEC=<int>`` — storyboard durations sum to this (duration validator)
- ``SCENE_ORDER=<int>`` — the scene a visual plan belongs to (scene_order match)
"""

import re

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo

from app.models.enums import (
    MIN_CONCEPT_FRAMES,
    MIN_SHOTS,
    AspectRatio,
    ConceptSetStatus,
    ConceptSetType,
    PreferredModel,
    PromotedAs,
    ShotTransition,
)


def _user_text(messages) -> str:
    parts: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            if part.__class__.__name__ == "UserPromptPart":
                content = getattr(part, "content", "")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    parts.extend(x for x in content if isinstance(x, str))
    return "\n".join(parts)


def _marker_int(text: str, key: str, default: int) -> int:
    m = re.search(rf"{key}\s*=\s*(\d+)", text)
    return int(m.group(1)) if m else default


def _parse_target_from_brief(text: str, default: int = 20) -> int:
    """Infer a duration like '30s' / '15 sec' / '45 seconds' from free brief text."""
    m = re.search(r"(\d{1,3})\s*(?:s\b|sec|seconds?)", text, flags=re.IGNORECASE)
    if m:
        return max(5, min(120, int(m.group(1))))
    return default


# --------------------------------------------------------------------------- #
# canned builders (return plain dicts matching the pipeline schemas)
# --------------------------------------------------------------------------- #


def _brief_dict(text: str) -> dict:
    return {
        "raw_prompt": text.strip() or "untitled brief",
        "product": "sample product",
        "story": "a short, punchy product moment",
        "platform": "generic",
        "target_duration_sec": _parse_target_from_brief(text),
        "aspect_ratio": AspectRatio.R9_16.value,
        "style": "clean, modern, cinematic",
        "audience": "general consumers",
    }


def _script_dict(text: str) -> dict:
    target = _parse_target_from_brief(text) or 20
    half = round(target / 2, 1)
    return {
        "logline": "A product reveal that turns a everyday moment into a hero shot.",
        "scenes": [
            {
                "order": 0,
                "title": "Hook",
                "summary": "Open on the everyday problem.",
                "beats": [{"order": 0, "description": "Establish the setting and tension."}],
                "est_duration_sec": half,
            },
            {
                "order": 1,
                "title": "Reveal",
                "summary": "The product solves it; end on the logo.",
                "beats": [{"order": 0, "description": "Product hero shot and payoff."}],
                "est_duration_sec": target - half,
            },
        ],
    }


def _scene_visual_plan_dict(text: str) -> dict:
    scene_order = _marker_int(text, "SCENE_ORDER", 0)
    frames = [
        {
            "prompt": f"concept frame {i}: warm cinematic lighting, product centered",
            "tags": ["cinematic", "warm"],
            "type": ConceptSetType.STYLE.value,
            "promoted_as": PromotedAs.NONE.value,
            "selected": False,
            "image_asset_id": None,
        }
        for i in range(MIN_CONCEPT_FRAMES)
    ]
    return {
        "visual_brief": {
            "scene_order": scene_order,
            "visual_style": "modern cinematic",
            "mood": "warm and aspirational",
            "palette": ["#2b2b2b", "#d9a066", "#f5f0e6"],
            "lighting": "soft golden-hour key light",
            "camera_language": "slow push-ins and gentle handheld",
            "character_notes": None,
            "environment_notes": "minimal, uncluttered set",
            "negative_rules": ["no harsh shadows", "no busy backgrounds"],
        },
        "concept_set": {
            "scene_order": scene_order,
            "brief": "warm cinematic look for the scene",
            "type": ConceptSetType.STYLE.value,
            "status": ConceptSetStatus.PLANNED.value,
            "candidate_look_frames": frames,
        },
    }


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _storyboard_dict(text: str) -> dict:
    target = _marker_int(text, "TARGET_DURATION_SEC", 20)
    n = _clamp(round(target / 4), MIN_SHOTS, 10)
    base = round(target / n, 2)
    durations = [base] * n
    durations[-1] = round(target - base * (n - 1), 2)  # absorb rounding remainder
    # keep within (0, 15]
    durations = [min(15.0, max(0.5, d)) for d in durations]
    shots = [
        {
            "order": i,
            "scene_order": 0,
            "purpose": "advance the story beat",
            "duration_sec": durations[i],
            "beat": "beat",
            "camera_spec": {
                "shot_size": "MS",
                "angle": "eye-level",
                "movement": "static",
                "lens": None,
            },
            "performance_spec": {
                "subject": "product",
                "action": "is presented",
                "emotion": "confident",
            },
            "preferred_model": PreferredModel.T2V.value if i % 2 == 0 else PreferredModel.I2V.value,
            "acceptance_rules": ["subject clearly in frame", "matches the scene mood"],
            "reference_look_frame_ids": [],
            "transition": ShotTransition.CUT.value,
        }
        for i in range(n)
    ]
    return {"scenes": [{"scene_order": 0, "shots": shots}]}


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #


def dispatch_mock(messages, info: AgentInfo) -> ModelResponse:
    if not info.output_tools:
        # no structured output requested — return a trivial text response
        from pydantic_ai.messages import TextPart

        return ModelResponse(parts=[TextPart(content="ok")])

    tool = info.output_tools[0]
    props = set(tool.parameters_json_schema.get("properties", {}))
    text = _user_text(messages)

    if "raw_prompt" in props:
        args = _brief_dict(text)
    elif "logline" in props:
        args = _script_dict(text)
    elif "visual_brief" in props:
        args = _scene_visual_plan_dict(text)
    elif "scenes" in props:
        args = _storyboard_dict(text)
    else:  # pragma: no cover - defensive
        raise ValueError(f"mock has no canned data for output schema with props {sorted(props)}")

    return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=args)])
