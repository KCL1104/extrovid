"""Text-to-speech: real DashScope qwen3-tts (sync) or an offline mock.

Gated by ``USE_MOCK_TTS``. Mock returns deterministic, valid WAV bytes so the whole
voiceover lifecycle is testable offline. The real path is written to the documented
qwen3-tts shape but MUST be verified against a live key before enabling — endpoint URL,
response envelope, and intl-region availability are all unconfirmed (see config note).
"""

import struct
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.http import request_with_retry


def _mock_wav(seconds: float = 1.0) -> bytes:
    """A minimal, decodable mono 8kHz silent WAV — enough for ffmpeg to mix in tests."""
    rate = 8000
    n = max(1, int(rate * seconds))
    data = b"\x00\x00" * n  # 16-bit silence
    block_align = 2
    byte_rate = rate * block_align
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, byte_rate, block_align, 16)
    header += b"data" + struct.pack("<I", len(data))
    return header + data


MOCK_WAV = _mock_wav(1.0)


@dataclass
class SpeechResult:
    audio: bytes
    content_type: str
    source_model: str


async def synthesize_speech(
    text: str, *, voice: str, instruction: str | None = None, language: str | None = None
) -> SpeechResult:
    """Synthesize one spoken line. Returns the audio bytes + the model that produced them."""
    settings = get_settings()
    model = settings.qwen_tts_instruct_model if instruction else settings.qwen_tts_model

    if settings.use_mock_tts:
        return SpeechResult(audio=MOCK_WAV, content_type="audio/wav", source_model=f"mock:{model}")

    # Real path (UNVERIFIED — confirm endpoint/envelope/region against a live intl key first).
    inp: dict = {"text": text, "voice": voice}
    if instruction:
        inp["instruction"] = instruction
    if language:
        inp["language_type"] = language
    body = {"model": model, "input": inp, "parameters": {}}
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    resp = await request_with_retry(
        "POST", settings.dashscope_tts_url, headers=headers, json=body, timeout_sec=60
    )
    resp.raise_for_status()
    out = resp.json().get("output", {})
    audio_url = (out.get("audio") or {}).get("url") if isinstance(out.get("audio"), dict) else None
    if not audio_url:
        raise RuntimeError("qwen-tts returned no audio url (verify response envelope)")
    # URLs expire ~24h — download and store immediately (caller persists the bytes)
    audio = (await request_with_retry("GET", audio_url, timeout_sec=120)).content
    return SpeechResult(audio=audio, content_type="audio/wav", source_model=model)
