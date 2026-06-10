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


def _cast_dict(text: str) -> dict:
    """Deterministic planned cast. CAST_FORCE_EMPTY lets tests exercise no-cast scripts."""
    if "CAST_FORCE_EMPTY" in text:
        return {"characters": []}
    return {
        "characters": [
            {
                "name": "Maya",
                "static_features": "woman in her early 30s, athletic build, shoulder-length "
                "black hair, warm brown eyes, light tan skin",
                "dynamic_features": "rust-orange utility jacket over a cream tee, dark "
                "slim jeans, brass wristwatch",
            }
        ]
    }


def _review_dict(text: str) -> dict:
    """Deterministic dailies review. The marker REVIEW_FORCE=revise lets tests (and the
    mock pipeline) exercise the revise path; everything else passes with a solid score."""
    revise = re.search(r"REVIEW_FORCE\s*=\s*revise", text) is not None
    if revise:
        return {
            "verdict": "revise",
            "score": 4.5,
            "notes": [
                "Subject drifts out of frame on the move.",
                "Lighting reads flatter than the visual brief's golden-hour key.",
            ],
            "suggestions": [
                {"kind": "edit", "instruction": "warm up the lighting to golden hour"},
                {"kind": "retake", "instruction": "keep the subject centered for the full move"},
            ],
        }
    return {
        "verdict": "pass",
        "score": 8.2,
        "notes": [
            "Subject is clearly framed and the move lands on the beat.",
            "Mood matches the scene's visual brief.",
        ],
        "suggestions": [],
    }


_CLARIFY_QUESTIONS = [
    {
        "id": "q-style",
        "question": "What visual style should the video have?",
        "why": "Style drives every look-dev and camera choice downstream.",
        "options": ["Clean and modern", "Cinematic film look", "Playful and colorful"],
        "allow_custom": True,
    },
    {
        "id": "q-mood",
        "question": "What mood or tone should it carry?",
        "why": "Mood sets the lighting, pacing and music direction.",
        "options": ["Warm and aspirational", "Bold and energetic", "Calm and premium"],
        "allow_custom": True,
    },
    {
        "id": "q-setting",
        "question": "Where does the story take place?",
        "why": "The setting anchors environments and continuity across shots.",
        "options": ["Minimal studio set", "Urban outdoors", "Cozy home interior"],
        "allow_custom": True,
    },
]

_STYLE_MOOD_WORDS = (
    "style",
    "cinematic",
    "mood",
    "tone",
    "lighting",
    "aesthetic",
    "noir",
    "vibrant",
    "minimal",
    "moody",
    "warm",
    "playful",
)


def _clarify_dict(text: str) -> dict:
    """Deterministic clarify triage. Markers ``CLARIFY_FORCE_NONE`` / ``CLARIFY_FORCE_ASK``
    pin the branch for tests (REVIEW_FORCE precedent); otherwise short prompts or prompts
    lacking style/mood words get the 3 canned questions, detailed prompts get none."""
    if "CLARIFY_FORCE_NONE" in text:
        return {
            "needs_clarification": False,
            "questions": [],
            "prompt_assessment": "Clear: subject, setting, style and mood are all specified.",
        }
    lower = text.lower()
    vague = len(text.strip()) < 80 or not any(w in lower for w in _STYLE_MOOD_WORDS)
    if "CLARIFY_FORCE_ASK" not in text and not vague:
        return {
            "needs_clarification": False,
            "questions": [],
            "prompt_assessment": "Clear: the prompt is detailed enough to plan from.",
        }
    return {
        "needs_clarification": True,
        "questions": _CLARIFY_QUESTIONS,
        "prompt_assessment": "Clear: the core idea. Missing: visual style, mood and setting.",
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
            "framing": "product centered, facing camera, focus on the label",
            "camera_id": i % 2,  # alternate between two camera setups
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
    elif "verdict" in props:
        args = _review_dict(text)
    elif "needs_clarification" in props:
        args = _clarify_dict(text)
    elif "characters" in props:
        args = _cast_dict(text)
    elif "scenes" in props:
        args = _storyboard_dict(text)
    else:  # pragma: no cover - defensive
        raise ValueError(f"mock has no canned data for output schema with props {sorted(props)}")

    return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=args)])
