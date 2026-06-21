"""Quality eval harness.

A small, runnable feedback loop on the PLANNING engine: run a handful of golden prompts
through the pipeline and score the output deterministically (duration adherence, continuity
baton, cast integrity, keyframe-contract coverage, subject anchoring…), with an optional
LLM-as-judge pass on narrative coherence. Tells you whether the engine's machinery actually
pays off — instead of guessing.

Run it:  uv run python -m app.evals.run            # structural only (works on mock or real)
         uv run python -m app.evals.run --judge    # + narrative-coherence judge (real LLM only)

Scope (v1): plan-level. Vision-level keyframe identity-drift scoring needs real image
generation + a persisted project, and is the next increment — see report's "Not yet measured".
"""
