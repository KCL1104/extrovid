"""The bare-name subject repair folds cast appearance into the subject deterministically."""

from types import SimpleNamespace as NS

from app.pipeline.orchestrator import _anchor_subject
from app.schemas.pipeline import CastMember

ELENA = CastMember(
    name="Elena",
    static_features="cropped dark hair, grey flight suit",
    dynamic_features="silver wristband",
)
CAST = {"elena": ELENA}


def _shot(subject: str, character_name: str | None):
    return NS(character_name=character_name, performance_spec=NS(subject=subject))


def test_bare_name_gets_anchored():
    out = _anchor_subject(_shot("Elena", "Elena"), CAST)
    assert out == "Elena (cropped dark hair, grey flight suit)"


def test_already_anchored_is_left_alone():
    assert _anchor_subject(_shot("Elena (in a red coat)", "Elena"), CAST) is None
    assert _anchor_subject(_shot("Elena, mid-stride", "Elena"), CAST) is None


def test_no_cast_or_unknown_name_left_alone():
    assert _anchor_subject(_shot("a chipped white mug", None), CAST) is None
    assert _anchor_subject(_shot("Bob", "Bob"), CAST) is None  # not in cast
