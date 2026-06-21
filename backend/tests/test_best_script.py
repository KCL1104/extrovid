"""Best-of-N script selection picks the highest-coherence draft."""

from app.agents.script_review_agent import ScriptCoherence
from app.pipeline.orchestrator import _pick_best_index


def test_picks_highest_coherence():
    v = [
        ScriptCoherence(coherence=4.0),
        ScriptCoherence(coherence=8.0),
        ScriptCoherence(coherence=6.0),
    ]
    assert _pick_best_index(v) == 1


def test_none_sorts_last():
    v = [None, ScriptCoherence(coherence=3.0), None]
    assert _pick_best_index(v) == 1


def test_all_none_returns_first():
    assert _pick_best_index([None, None]) == 0
