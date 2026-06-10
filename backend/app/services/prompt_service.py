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


# the planned transition shapes how the take should END (consumed as an ending hint)
_TRANSITION_ENDINGS = {
    ShotTransition.MATCH_CUT.value: (
        "ending: compose the final frames to graphically match the next shot's opening"
    ),
    ShotTransition.DISSOLVE.value: "ending: let the motion settle gently toward the end",
    ShotTransition.FADE.value: "ending: let the motion settle gently toward the end",
}


def compose_shot_prompt(
    shot: Shot,
    *,
    visual_brief: dict | None = None,
    style_pack: StylePack | None = None,
    character: CharacterProfile | None = None,
    has_reference_images: bool = False,
) -> str:
    cam = shot.camera_spec or {}
    perf = shot.performance_spec or {}
    vb = visual_brief or {}

    parts: list[str] = []
    if has_reference_images:
        parts.append("The main subject matches the reference image")

    # action first — what the camera sees
    subject_action = f"{perf.get('subject', '')} {perf.get('action', '')}".strip()
    parts.append(shot.purpose)
    if subject_action:
        parts.append(subject_action)
    if perf.get("emotion"):
        parts.append(f"mood: {perf['emotion']}")

    # explicit per-shot director notes carry the highest creative priority — keep them
    # right next to the action so the model treats them as direction, not decoration
    if shot.extra_direction and shot.extra_direction.strip():
        parts.append(f"Director's notes: {shot.extra_direction.strip()}")

    # camera language: shot-level spec, enriched by the scene's camera direction
    cam_desc = " ".join(
        filter(None, [cam.get("shot_size"), cam.get("angle"), cam.get("movement"), cam.get("lens")])
    )
    if cam_desc:
        parts.append(f"camera: {cam_desc}")
    elif vb.get("camera_language"):
        parts.append(f"camera: {vb['camera_language']}")

    # visual direction from the persisted scene brief
    style_bits = [vb.get("visual_style"), vb.get("mood")]
    if style_pack and style_pack.visual_style:
        style_bits.append(style_pack.visual_style)
    style = ", ".join(dict.fromkeys(s for s in style_bits if s))
    if style:
        parts.append(f"style: {style}")
    lighting = (style_pack.lighting if style_pack else None) or vb.get("lighting")
    if lighting:
        parts.append(f"lighting: {lighting}")
    palette = (style_pack.palette if style_pack and style_pack.palette else None) or vb.get(
        "palette"
    )
    if palette:
        parts.append(f"palette: {', '.join(str(c) for c in palette[:4])}")
    if vb.get("environment_notes"):
        parts.append(f"setting: {vb['environment_notes']}")

    # character constraints (identity memory)
    if character:
        desc = (character.description or "").strip()
        parts.append(f"featuring {character.name}" + (f": {desc}" if desc else ""))
        if character.wardrobe_rules:
            parts.append(f"wardrobe: {', '.join(str(r) for r in character.wardrobe_rules[:3])}")

    ending_hint = _TRANSITION_ENDINGS.get(shot.transition or "")
    if ending_hint:
        parts.append(ending_hint)

    parts.append(f"beat: {shot.beat}")

    prompt = _join(parts)

    # negative rules go last, as an explicit avoid-list
    negatives: list[str] = []
    for source in (vb.get("negative_rules") or [], style_pack.negative_rules if style_pack else []):
        negatives.extend(str(r) for r in source)
    if character and character.forbidden_changes:
        negatives.extend(str(r) for r in character.forbidden_changes)
    if negatives:
        prompt += " Avoid: " + "; ".join(list(dict.fromkeys(negatives))[:6]) + "."
    return prompt
