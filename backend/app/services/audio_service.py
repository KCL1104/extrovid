"""Per-shot voiceover: resolve a voice, synthesize the line, persist it on the shot.

Voice identity is persisted on ``CharacterProfile.voice_lock`` (the reserved dict) so a
character keeps the same voice across shots — the audio analogue of the portrait sheet.
A shot whose speaker is "narrator" (or has no cast) uses the project's default narrator
voice. Audio is stored as an ImageAsset with ``content_type=audio/wav`` and billed against
the dedicated audio cap (NOT image spend).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthCtx
from app.core.config import get_settings
from app.core.pricing import tts_cost_usd
from app.models.asset import ImageAsset
from app.models.memory import CharacterProfile
from app.models.shot import Shot
from app.providers.audio_factory import synthesize_speech
from app.services.asset_service import store_bytes
from app.services.usage_service import assert_within_cap

# qwen3-tts voice presets (VERIFY exact names against a live key before real mode)
_NARRATOR_VOICE = "Chelsie"
_FEMALE_WORDS = ("woman", "female", "she ", "girl", "lady", "her ")
_MALE_WORDS = ("man", "male", "he ", "boy", "guy", "his ")


def resolve_voice(character: CharacterProfile | None) -> dict:
    """The voice config for a character (persisted in voice_lock), seeded from a static
    gender heuristic on first use. Narrator / no-cast → the default narrator voice."""
    settings = get_settings()
    if character and character.voice_lock:
        return character.voice_lock
    desc = (character.description.lower() if character and character.description else "")
    if any(w in f" {desc} " for w in _FEMALE_WORDS):
        voice = "Cherry"
    elif any(w in f" {desc} " for w in _MALE_WORDS):
        voice = "Ethan"
    else:
        voice = _NARRATOR_VOICE
    return {
        "provider": "dashscope",
        "model": settings.qwen_tts_model,
        "voice": voice,
        "language": "en",
        "instruction": None,
    }


def _tone_instruction(shot: Shot, voice: dict) -> str | None:
    """A per-shot performance emotion becomes a TTS tone instruction (which activates the
    instruct model). Falls back to the voice's own instruction when no emotion is set;
    voice_lock still pins the voice identity, this only layers tone per synthesis."""
    emotion = str((shot.performance_spec or {}).get("emotion") or "").strip()
    return f"Speak with a {emotion} tone." if emotion else voice.get("instruction")


async def synthesize_shot_voiceover(
    session: AsyncSession, project_id: str, shot: Shot, *, auth: AuthCtx
) -> ImageAsset:
    """Synthesize the shot's spoken line into a stored audio asset; point the shot at it."""
    line = (shot.dialogue or "").strip()
    if not line:
        raise LookupError("shot has no dialogue to voice")
    await assert_within_cap(session, "audio", 1, auth=auth)

    settings = get_settings()
    # resolve the speaker's voice; persist a seeded voice_lock so it stays stable
    character: CharacterProfile | None = None
    if shot.character_id and (shot.speaker or "").lower() != "narrator":
        character = await session.get(CharacterProfile, shot.character_id)
        if character and character.project_id != project_id:
            character = None
    voice = resolve_voice(character)
    if character is not None and not character.voice_lock:
        character.voice_lock = voice
        session.add(character)

    result = await synthesize_speech(
        line,
        voice=str(voice.get("voice") or _NARRATOR_VOICE),
        instruction=_tone_instruction(shot, voice),
        language=voice.get("language"),
    )
    asset = await store_bytes(
        session,
        project_id,
        result.audio,
        result.content_type,
        prompt=f"voiceover — {line[:120]}",
        source_model=result.source_model,
        use_mock=settings.use_mock_tts,
        cost_usd=0.0 if settings.use_mock_tts else tts_cost_usd(),
    )
    shot.vo_asset_id = asset.id
    session.add(shot)
    await session.commit()
    await session.refresh(asset)
    return asset
