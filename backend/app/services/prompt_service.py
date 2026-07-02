"""Compose the final video-generation prompt from project memory.

This is the memory-injection layer the spec calls for: instead of a mechanical join of
shot fields, the prompt sent to Wan carries the scene's persisted VisualBrief (style,
lighting, palette, camera language), the project's StylePack, CharacterProfile constraints,
and negative rules. Deterministic composition — no LLM call — so it is fast, free, and
fully testable; the creative intelligence already lives in the planning agents' outputs.
"""

from app.models.enums import ShotTransition
from app.models.memory import CharacterProfile, StylePack
from app.models.shot import Shot


def _join(parts: list[str]) -> str:
    return ". ".join(p.strip().rstrip(".") for p in parts if p and p.strip()) + "."


# Portrait-view selection (ViMax reference-selection prior): at most ONE portrait view per
# character, chosen by what the camera will see. Shared by the video reference path
# (generate_service) and the keyframe image path (imagegen_service) so both anchor identity
# from the same view instead of always defaulting to the front portrait.
_BACK_VIEW_CUES = (
    "from behind",
    "over-the-shoulder",
    "over the shoulder",
    "back view",
    "walking away",
    "from the back",
    "back to camera",
)
_SIDE_VIEW_CUES = ("profile", "side view", "from the side", "facing left", "facing right")

# Always-on negative-prompt floor: artifact classes worth suppressing on every shot regardless
# of what the planner authored. Appended AFTER authored negatives so authored rules win the cap.
_BASELINE_NEGATIVES = (
    "deformed hands",
    "extra fingers",
    "extra limbs",
    "warped face",
    "identity drift",
    "camera jitter",
    "flicker",
    "text artifacts",
    "watermark",
)


def portrait_view_for(shot: Shot | None) -> str:
    """Return the portrait view ('front' | 'side' | 'back') matching the shot's direction."""
    if shot is None:
        return "front"
    text = " ".join(
        [
            str(shot.framing or ""),
            str((shot.performance_spec or {}).get("subject", "")),
            str((shot.performance_spec or {}).get("action", "")),
            str(shot.first_frame_desc or ""),
        ]
    ).lower()
    if any(cue in text for cue in _BACK_VIEW_CUES):
        return "back"
    if any(cue in text for cue in _SIDE_VIEW_CUES):
        return "side"
    return "front"


# the planned transition shapes how the take should END (consumed as an ending hint)
_TRANSITION_ENDINGS = {
    ShotTransition.MATCH_CUT.value: (
        "ending: compose the final frames to graphically match the next shot's opening"
    ),
    ShotTransition.DISSOLVE.value: "ending: let the motion settle gently toward the end",
    ShotTransition.FADE.value: "ending: let the motion settle gently toward the end",
}

# what a caller-supplied reference image contributes, by role (seedance @-reference concept).
# 'identity' is already folded into the portrait/subject line, so it has no extra clause.
_REFERENCE_ROLE_CLAUSE = {
    "outfit": "the subject's wardrobe matches the reference image",
    "prop": "the key object/prop matches the reference image",
    "scene": "the scene and background match the reference image",
    "style": "the visual style references the reference image",
}

# house defaults when the brief leaves style/lighting blank — keeps even a bare shot from
# reaching the model with no look direction at all. Authored values always win.
_DEFAULT_STYLE = "cinematic, shallow depth of field"
_DEFAULT_LIGHTING = "natural, motivated lighting"

# style-agnostic photographic quality tail for STILL keyframes/portraits (lighting and
# camera/lens language have the highest leverage on image quality; these are the render-
# quality floor that works for both photoreal and stylized looks)
_IMAGE_QUALITY_TAIL = (
    "a single crisp still frame, no motion blur, sharp focus, rich fine detail, "
    "professional color grading, masterful composition"
)


def compose_shot_prompt(
    shot: Shot,
    *,
    visual_brief: dict | None = None,
    style_pack: StylePack | None = None,
    character: CharacterProfile | None = None,
    has_reference_images: bool = False,
    reference_roles: list[str] | None = None,
    supporting_cast: list[str] | None = None,
    clarifications: list[dict] | None = None,
) -> str:
    cam = shot.camera_spec or {}
    perf = shot.performance_spec or {}
    vb = visual_brief or {}

    parts: list[str] = []
    if has_reference_images:
        if character:
            parts.append(
                f"The primary subject matches the reference portrait of {character.name}"
            )
        else:
            parts.append("The main subject matches the reference image")
        # supporting cast whose portraits ride along as extra identity references
        if supporting_cast:
            names = ", ".join(dict.fromkeys(supporting_cast))
            parts.append(f"the supporting cast ({names}) each match their reference portraits")
        # per-reference role clauses tell the model what to take from each non-identity ref
        for clause in dict.fromkeys(
            _REFERENCE_ROLE_CLAUSE[r]
            for r in (reference_roles or [])
            if r in _REFERENCE_ROLE_CLAUSE
        ):
            parts.append(clause)

    # action first — what the camera sees. With a cast lock, anchor the subject by
    # visible appearance inline (the video model never sees the character bible, so
    # "Alice is walking" must become "Alice (short hair, green dress) is walking").
    subject = perf.get("subject", "")
    appearance_inlined = False
    if character:
        appearance_bits = []
        desc = (character.description or "").strip()
        if desc:
            appearance_bits.append(desc.split(".")[0].strip())
        if character.wardrobe_rules:
            appearance_bits.append(str(character.wardrobe_rules[0]))
        idx = subject.lower().find(character.name.lower())
        if appearance_bits and idx >= 0 and "(" not in subject:
            end = idx + len(character.name)
            subject = f"{subject[:end]} ({', '.join(appearance_bits)}){subject[end:]}"
            appearance_inlined = True
    subject_action = f"{subject} {perf.get('action', '')}".strip()
    parts.append(shot.purpose)
    # the planned motion (keyframe contract) is the most precise action description —
    # it already references characters by visible appearance, never bare names
    if shot.motion_desc and shot.motion_desc.strip():
        parts.append(shot.motion_desc.strip())
    elif subject_action:
        parts.append(subject_action)
    if perf.get("emotion"):
        parts.append(f"mood: {perf['emotion']}")

    # explicit per-shot director notes carry the highest creative priority — keep them
    # right next to the action so the model treats them as direction, not decoration
    if shot.extra_direction and shot.extra_direction.strip():
        parts.append(f"Director's notes: {shot.extra_direction.strip()}")

    # persisted director Q&A — durable creative direction reaches execution too
    answered = [
        a for a in clarifications or [] if str(a.get("answer", "")).strip()
    ]
    if answered:
        distilled = "; ".join(str(a["answer"]).strip() for a in answered[:4])
        parts.append(f"Creative direction: {distilled}")

    # camera language: shot-level spec, enriched by the scene's camera direction
    cam_desc = " ".join(
        filter(None, [cam.get("shot_size"), cam.get("angle"), cam.get("movement"), cam.get("lens")])
    )
    if cam_desc:
        parts.append(f"camera: {cam_desc}")
    elif vb.get("camera_language"):
        parts.append(f"camera: {vb['camera_language']}")

    # blocking: subject frame positions + facing directions (planned by the storyboard)
    if shot.framing and shot.framing.strip():
        parts.append(f"framing: {shot.framing.strip()}")
    # screen-direction continuity (the 180-degree line)
    if shot.screen_direction and shot.screen_direction.strip():
        parts.append(f"screen direction: {shot.screen_direction.strip()}")
    # a spoken line cues mouth movement / performance (the audio itself is added later as VO)
    if shot.dialogue and shot.dialogue.strip() and (shot.speaker or "").lower() != "narrator":
        parts.append(f"the subject is speaking the line: {shot.dialogue.strip()}")

    # visual direction from the persisted scene brief
    style_bits = [vb.get("visual_style"), vb.get("mood")]
    if style_pack and style_pack.visual_style:
        style_bits.append(style_pack.visual_style)
    style = ", ".join(dict.fromkeys(s for s in style_bits if s))
    parts.append(f"style: {style or _DEFAULT_STYLE}")
    lighting = (style_pack.lighting if style_pack else None) or vb.get("lighting")
    parts.append(f"lighting: {lighting or _DEFAULT_LIGHTING}")
    palette = (style_pack.palette if style_pack and style_pack.palette else None) or vb.get(
        "palette"
    )
    if palette:
        parts.append(f"palette: {', '.join(str(c) for c in palette[:4])}")
    if vb.get("environment_notes"):
        parts.append(f"setting: {vb['environment_notes']}")

    # character constraints (identity memory)
    if character:
        if appearance_inlined:
            # appearance already inlined into the subject — don't restate the full desc
            parts.append(f"featuring {character.name}")
        else:
            desc = (character.description or "").strip()
            parts.append(f"featuring {character.name}" + (f": {desc}" if desc else ""))
        if character.wardrobe_rules:
            parts.append(f"wardrobe: {', '.join(str(r) for r in character.wardrobe_rules[:3])}")

    # a planned closing snapshot beats the generic transition-shaped hint
    if shot.last_frame_desc and shot.last_frame_desc.strip():
        parts.append(f"ending state: {shot.last_frame_desc.strip()}")
    else:
        ending_hint = _TRANSITION_ENDINGS.get(shot.transition or "")
        if ending_hint:
            parts.append(ending_hint)

    return _join(parts)


def compose_keyframe_prompt(
    shot: Shot,
    *,
    visual_brief: dict | None = None,
    style_pack: StylePack | None = None,
    character: CharacterProfile | None = None,
    kind: str = "first",
) -> str:
    """Image prompt for a shot keyframe — a pure static snapshot.

    ``kind="first"`` renders the opening frame; ``kind="last"`` renders the planned closing
    frame (``last_frame_desc``) used as the NEXT shot's continuity seed. Identity and
    composition resolve in the image domain (cheap, retryable) before any video is rendered;
    the video model then only animates from this anchor.
    """
    cam = shot.camera_spec or {}
    perf = shot.performance_spec or {}
    vb = visual_brief or {}
    desc = (shot.last_frame_desc if kind == "last" else shot.first_frame_desc) or ""

    parts: list[str] = []
    if desc.strip():
        parts.append(desc.strip())
    else:
        subject = perf.get("subject", "")
        moment = "the closing frame" if kind == "last" else "the opening frame"
        edge = "the shot ends" if kind == "last" else "the shot begins"
        parts.append(f"{moment} of a shot: {subject} in place, frozen at the moment {edge}")
    # Facing/direction is continuity-critical for the i2v seed — always carry it (the video
    # prompt does the same), so the keyframe doesn't default the subject to facing camera when
    # the shot intends e.g. "walking away" or a screen-direction the next shot must respect.
    if shot.framing and shot.framing.strip():
        parts.append(f"framing: {shot.framing.strip()}")
    if shot.screen_direction and shot.screen_direction.strip():
        parts.append(f"screen direction: {shot.screen_direction.strip()}")
    if character:
        desc = (character.description or "").strip()
        if desc:
            parts.append(f"the character is {character.name}: {desc}")
        if character.wardrobe_rules:
            parts.append(f"wardrobe: {', '.join(str(r) for r in character.wardrobe_rules[:2])}")
    cam_desc = " ".join(filter(None, [cam.get("shot_size"), cam.get("angle"), cam.get("lens")]))
    if cam_desc:
        parts.append(f"camera: {cam_desc}")
    style_bits = [vb.get("visual_style"), vb.get("mood")]
    if style_pack and style_pack.visual_style:
        style_bits.append(style_pack.visual_style)
    style = ", ".join(dict.fromkeys(s for s in style_bits if s))
    parts.append(f"style: {style or _DEFAULT_STYLE}")
    lighting = (style_pack.lighting if style_pack else None) or vb.get("lighting")
    parts.append(f"lighting: {lighting or _DEFAULT_LIGHTING}")
    if vb.get("environment_notes"):
        parts.append(f"setting: {vb['environment_notes']}")
    parts.append(_IMAGE_QUALITY_TAIL)
    return _join(parts)


def compose_negative_prompt(
    *,
    visual_brief: dict | None = None,
    style_pack: StylePack | None = None,
    character: CharacterProfile | None = None,
) -> str | None:
    """The avoid-list as a real ``negative_prompt`` parameter.

    Diffusion models treat the positive prompt as content to render, so negatives no
    longer ride inside it — they are conditioned against natively by Wan/Qwen-Image.
    """
    vb = visual_brief or {}
    negatives: list[str] = []
    for source in (vb.get("negative_rules") or [], style_pack.negative_rules if style_pack else []):
        negatives.extend(str(r) for r in source)
    if character and character.forbidden_changes:
        negatives.extend(str(r) for r in character.forbidden_changes)
    # authored negatives first, then the always-on baseline; dedupe preserves order so authored
    # rules stay ahead of the baseline and survive the cap when both are present.
    negatives.extend(_BASELINE_NEGATIVES)
    deduped = list(dict.fromkeys(n for n in negatives if n and n.strip()))
    if not deduped:
        return None
    return "; ".join(deduped[:10])
