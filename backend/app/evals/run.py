"""Run the quality eval and print a markdown scorecard.

uv run python -m app.evals.run                 # structural metrics (mock or real)
uv run python -m app.evals.run --judge         # + narrative-coherence judge (real LLM only)
uv run python -m app.evals.run --ids coffee-ad-20s,scifi-trailer-30s
uv run python -m app.evals.run --out evals_report.md
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.config import get_settings
from app.evals import golden as goldens_mod
from app.evals import metrics as metrics_mod
from app.evals.golden import Golden
from app.evals.judge import judge_coherence
from app.pipeline.orchestrator import run_pipeline
from app.schemas.pipeline import BriefInput


async def _evaluate_one(g: Golden, with_judge: bool) -> dict:
    try:
        result = await run_pipeline(
            BriefInput(raw_prompt=g.raw_prompt), target_duration_sec=g.target_duration_sec
        )
    except Exception as exc:  # noqa: BLE001 - one bad prompt shouldn't sink the report
        return {"golden": g, "error": str(exc)}
    scored = metrics_mod.compute(result)
    verdict = await judge_coherence(result) if with_judge else None
    # cast expectation flagged inline so a 0-cast story stands out
    scored["cast_expectation_met"] = (len(result.cast) > 0) == g.expect_cast
    return {"golden": g, "scored": scored, "verdict": verdict}


def render_report(rows: list[dict], *, judged: bool) -> str:
    out: list[str] = ["# Quality eval — planning engine", ""]
    overalls = [r["scored"]["overall"] for r in rows if "scored" in r]
    if overalls:
        mean = sum(overalls) / len(overalls)
        out.append(f"**Mean score: {mean:.1f}/100** across {len(overalls)} prompt(s)")
        out.append("")

    for r in rows:
        g: Golden = r["golden"]
        out.append(f"## {g.id}  ·  {g.target_duration_sec}s")
        out.append(f"> {g.raw_prompt}")
        out.append("")
        if "error" in r:
            out.append(f"❌ **pipeline failed:** {r['error']}")
            out.append("")
            continue
        s = r["scored"]
        t = s["totals"]
        out.append(
            f"**{s['overall']}/100** · tier `{s['tier']}` · "
            f"{t['scenes']} scenes / {t['shots']} shots / {t['cast']} cast · "
            f"{t['planned_sec']}s planned"
        )
        if not s["cast_expectation_met"]:
            out.append(
                f"⚠️ cast expectation not met (expected_cast={g.expect_cast}, got {t['cast']})"
            )
        out.append("")
        out.append("| metric | score | detail |")
        out.append("|---|---|---|")
        for m in s["metrics"]:
            sc = "  n/a" if not m.applicable else f"{m.score * 100:4.0f}%"
            out.append(f"| {m.key} | {sc} | {m.value} |")
        out.append("")
        if judged:
            v = r.get("verdict")
            if v is None:
                out.append(
                    "_judge skipped (mock LLM — run with real models for a coherence score)_"
                )
            else:
                out.append(f"**Narrative coherence (LLM judge): {v.coherence}/10**")
                for issue in v.issues:
                    out.append(f"- {issue}")
            out.append("")

    out.append("---")
    out.append("## Not yet measured (needs real image generation)")
    out.append(
        "- Keyframe **identity drift** — does the same character look consistent across shots? "
        "(vision diff of generated keyframes vs the cast portrait)"
    )
    out.append(
        "- **Render quality** — artifacting, motion naturalness, prompt adherence of the clips."
    )
    out.append("")
    out.append("## Human spot-check (watch one generated video per prompt, tick honestly)")
    for q in (
        "Would I actually share this?",
        "Does the same character stay recognizably the same person?",
        "Is the motion natural (no morphing, no teleporting)?",
        "Does the cut hold attention end-to-end, or sag in the middle?",
        "Does the ending land?",
    ):
        out.append(f"- [ ] {q}")
    out.append("")
    return "\n".join(out)


async def _main(ids: list[str] | None, with_judge: bool) -> str:
    chosen = [g for g in goldens_mod.GOLDEN if not ids or g.id in ids]
    rows = [await _evaluate_one(g, with_judge) for g in chosen]
    return render_report(rows, judged=with_judge)


def main() -> None:
    ap = argparse.ArgumentParser(description="Quality eval for the planning engine")
    ap.add_argument(
        "--judge", action="store_true", help="run the LLM coherence judge (real LLM only)"
    )
    ap.add_argument("--ids", help="comma-separated golden ids to run (default: all)")
    ap.add_argument("--out", help="write the markdown report here (default: stdout)")
    args = ap.parse_args()

    if args.judge and get_settings().use_mock_llm:
        print(
            "note: USE_MOCK_LLM is on — the judge will be skipped (structural metrics still run).\n"
        )
    ids = [s.strip() for s in args.ids.split(",")] if args.ids else None
    report = asyncio.run(_main(ids, args.judge))
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(report)
        print(f"wrote {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
