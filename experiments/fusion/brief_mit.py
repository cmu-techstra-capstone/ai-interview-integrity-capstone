"""Write LLM reviewer briefs for MIT answers the follow-up rule flagged, plus demo JSON.

Run after ``run_mit.py evaluate``, on a machine that can reach OpenRouter (see
docs/demo-handoff.md). Briefs see only the computed conditions and the interviewer's
question, not the candidate's answer text. Every call is cached, so rerunning is free.

  .venv-video/bin/python experiments/fusion/brief_mit.py --model openai/gpt-4o-mini

Outputs (ignored, local only):
  data/processed/fusion/briefs.jsonl           one row per flagged answer
  data/processed/fusion/demo/<recording>.json  every answer of each flagged recording
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from interview_integrity.fusion.demo_export import answer_fragment, recording_payload, result_from_dict  # noqa: E402
from interview_integrity.fusion.followup import SUGGEST  # noqa: E402
from interview_integrity.fusion.llm_brief import generate_brief  # noqa: E402
from interview_integrity.llm import CachedClient, OpenRouterClient, load_dotenv  # noqa: E402

FUSION = ROOT / "data/processed/fusion"


def client() -> CachedClient:
    for env in (ROOT / ".env", ROOT.parent / "ai-interview-integrity-capstone" / ".env"):
        load_dotenv(env)
    return CachedClient(OpenRouterClient(), FUSION / "llm_cache.jsonl")


def main(argv=None, make_client=client) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="openai/gpt-4o-mini")
    p.add_argument("--include-question-text", action="store_true", help="put interviewer questions in demo JSON")
    p.add_argument("--fusion-dir", type=Path, default=FUSION)
    args = p.parse_args(argv)

    files = sorted((args.fusion_dir / "results").glob("*.jsonl"))
    if not files:
        raise SystemExit("no results; run experiments/fusion/run_mit.py evaluate first")
    c = make_client()
    briefs_out, n_flagged, n_ok = [], 0, 0
    for f in files:
        rows = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
        results = [result_from_dict(r) for r in rows]
        if not any(r.status == SUGGEST for r in results):
            continue
        fragments = []
        for r in results:
            brief = None
            if r.status == SUGGEST:
                n_flagged += 1
                brief = generate_brief(c, r, model=args.model)
                n_ok += brief["accepted"]
                briefs_out.append({"recording_id": r.recording_id, "question_id": r.question_id, **brief})
            fragments.append(answer_fragment(r, brief, include_text=args.include_question_text))
        demo = args.fusion_dir / "demo" / f"{f.stem}.json"
        demo.parent.mkdir(parents=True, exist_ok=True)
        demo.write_text(json.dumps(recording_payload(f.stem, fragments), indent=2, ensure_ascii=False) + "\n")
    with open(args.fusion_dir / "briefs.jsonl", "w") as out:
        for b in briefs_out:
            out.write(json.dumps(b, ensure_ascii=False) + "\n")
    print(f"briefs: {n_ok}/{n_flagged} accepted by guardrails; demo JSON in {args.fusion_dir / 'demo'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
