"""Cost estimation from actual generation parameters (model / duration / resolution).

DashScope doesn't return a price, so we compute from published-rate config × actual params.
This is far more accurate than a flat per-op estimate.
"""

from app.core.config import get_settings


def video_cost_usd(duration_sec: float, resolution: str) -> float:
    s = get_settings()
    rate = (
        s.cost_per_video_sec_1080p
        if "1080" in (resolution or "").upper()
        else s.cost_per_video_sec_720p
    )
    return round(max(0.0, duration_sec) * rate, 4)


def image_cost_usd(model: str) -> float:
    s = get_settings()
    return s.cost_per_image_pro_usd if "pro" in (model or "").lower() else s.cost_per_image_usd


def tts_cost_usd() -> float:
    return get_settings().cost_per_tts_usd
