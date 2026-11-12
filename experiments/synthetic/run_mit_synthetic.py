"""Synthetic AI-written answers vs real MIT answers: can a content rubric tell them apart?

Research only. Synthetic answers are a partial stand-in for missing AI-assisted
interviews and cover the text/content channel only. Run on a machine that can reach
OpenRouter (the Mac), from the worktree root:

  .venv-video/bin/python experiments/synthetic/run_mit_synthetic.py extract
  .venv-video/bin/python experiments/synthetic/run_mit_synthetic.py models
  .venv-video/bin/python experiments/synthetic/run_mit_synthetic.py generate --participants 8
  .venv-video/bin/python experiments/synthetic/run_mit_synthetic.py score --participants 8
  .venv-video/bin/python experiments/synthetic/run_mit_synthetic.py evaluate

Every LLM call is cached in data/processed/synthetic/llm_cache.jsonl (ignored), so
re-running is free and a larger --participants only pays for the new items. Reports in
reports/synthetic/ contain aggregate numbers only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "fusion"))

from interview_integrity.fusion.llm_brief import parse_json  # noqa: E402
from interview_integrity.llm import BudgetExceeded, CachedClient, OpenRouterClient, load_dotenv  # noqa: E402
from interview_integrity.synthetic.generate import (  # noqa: E402
    CONDITIONS, GENERATION_SYSTEM, build_generation_prompt, build_profile, clean_generation, word_count,
)
from interview_integrity.synthetic.metrics import grouped_bootstrap_auroc  # noqa: E402
from interview_integrity.synthetic.questions import EVALUATED_TYPES, QAPair, qa_pairs  # noqa: E402
from interview_integrity.synthetic.rubric import (  # noqa: E402
    DIMENSIONS, JUDGE_SYSTEM, build_judge_prompt, composite, validate_rubric,
)

MIT_LABELS = ROOT / "data/raw/video_research/mit/Labels.zip"
OUT = ROOT / "data/processed/synthetic"
REPORTS = ROOT / "reports/synthetic"
DEFAULT_GENERATORS = ["openai/gpt-4o-mini", "anthropic/claude-haiku-5.5", "meta-llama/llama-3.3-70b-instruct"]
DEFAULT_JUDGE = "google/gemini-2.5-flash"
MIN_WORDS = 40
SEED = 20261105


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"missing {path}; run the previous step first")
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def client(max_calls: int | None) -> CachedClient:
    for env in (ROOT / ".env", ROOT.parent / "ai-interview-integrity-capstone" / ".env"):
        load_dotenv(env)
    return CachedClient(OpenRouterClient(), OUT / "llm_cache.jsonl", max_calls=max_calls)


def pairs_from_rows(rows) -> list[QAPair]:
    return [QAPair(**{k: r[k] for k in QAPair.__dataclass_fields__}) for r in rows]


def eligible(p: QAPair) -> bool:
    return p.question_type in EVALUATED_TYPES and p.n_words >= MIN_WORDS


def selected_participants(pairs: list[QAPair], n: int | None) -> list[str]:
    ids = sorted({p.participant_id for p in pairs if eligible(p)}, key=lambda s: int(s[1:]))
    if n is None or n >= len(ids):
        return ids
    return sorted(random.Random(SEED).sample(ids, n), key=lambda s: int(s[1:]))


def check_models(c: CachedClient, models: list[str]) -> None:
    try:
        available = set(c.inner.list_models())
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"could not list OpenRouter models: {e}")
    missing = [m for m in models if m not in available]
    if missing:
        close = {m: [a for a in available if a.split("/")[0] == m.split("/")[0]][:8] for m in missing}
        raise SystemExit(f"model id(s) not on OpenRouter: {missing}\nsame-provider options: {json.dumps(close, indent=1)}")


# ------------------------------------------------------------------ steps

def cmd_extract(args) -> None:
    sys.path.insert(0, str(ROOT / "experiments" / "fusion"))
    from run_mit import load_transcripts  # reuse the MIT transcript loader
    transcripts = load_transcripts(MIT_LABELS)
    rows = []
    for rec in sorted(transcripts, key=lambda s: (len(s), s)):
        for p in qa_pairs(rec.upper(), transcripts[rec]):
            rows.append({**p.to_dict(), "eligible": eligible(p)})
    write_jsonl(OUT / "answers.jsonl", rows)
    el = [r for r in rows if r["eligible"]]
    log(f"extract: {len(rows)} answers, {len(el)} eligible from {len({r['participant_id'] for r in el})} participants")
    log("eligible by question type: " + json.dumps(Counter(r["question_type"] for r in el)))


def cmd_models(args) -> None:
    c = client(None)
    check_models(c, args.generators + [args.judge])
    log(f"all configured models available: {args.generators + [args.judge]}")


def _run_parallel(jobs, fn, workers):
    results, stopped = [], False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, j): j for j in jobs}
        for k, fut in enumerate(as_completed(futures), 1):
            try:
                results.append(fut.result())
            except BudgetExceeded as e:
                stopped = True
                results.append({"job": futures[fut], "error": str(e)})
            except Exception as e:  # noqa: BLE001
                results.append({"job": futures[fut], "error": f"{type(e).__name__}: {e}"})
            if k % 50 == 0:
                log(f"  {k}/{len(jobs)} done")
    if stopped:
        log("budget reached; rerun the same command to continue (finished calls are cached)")
    return results


def cmd_generate(args) -> None:
    pairs = pairs_from_rows(read_jsonl(OUT / "answers.jsonl"))
    people = set(selected_participants(pairs, args.participants))
    targets = [p for p in pairs if p.participant_id in people and eligible(p)]
    jobs = [(p, cond, gen) for p in targets for cond in args.conditions for gen in args.generators]
    log(f"generate: {len(people)} participants, {len(targets)} real answers -> {len(jobs)} generations")
    c = client(args.max_calls)
    if not args.skip_model_check:
        check_models(c, args.generators)

    def one(job):
        p, cond, gen = job
        profile = build_profile(pairs, p) if cond != "AI_VERBATIM" else ""
        prompt = build_generation_prompt(p, cond, profile)
        seed = int(hashlib.sha256(f"{p.recording_id}{p.question_id}{cond}{gen}".encode()).hexdigest()[:8], 16)
        resp = c.generate(prompt, model=gen, system=GENERATION_SYSTEM, temperature=0.9, max_tokens=600, seed=seed)
        text = clean_generation(resp.text)
        if word_count(text) < 20:  # reasoning models can spend the whole budget thinking; retry once
            resp = c.generate(prompt, model=gen, system=GENERATION_SYSTEM, temperature=0.9, max_tokens=4000, seed=seed)
            text = clean_generation(resp.text)
        return {"sample_id": f"syn/{gen}/{cond}/{p.recording_id}/{p.question_id}", "kind": "synthetic",
                "participant_id": p.participant_id, "recording_id": p.recording_id, "question_id": p.question_id,
                "question_type": p.question_type, "question_text": p.question_text, "condition": cond,
                "generator": gen, "model_returned": resp.model, "text": text, "n_words": word_count(text),
                "real_n_words": p.n_words, "valid": word_count(text) >= 20}

    results = _run_parallel(jobs, one, args.workers)
    ok = sorted((r for r in results if "error" not in r), key=lambda r: r["sample_id"])
    errors = [r for r in results if "error" in r]
    write_jsonl(OUT / "synthetic.jsonl", ok)
    log(f"generate: {len(ok)} written ({sum(not r['valid'] for r in ok)} too short/refusals), {len(errors)} errors; "
        f"new paid calls {c.calls}, cache hits {c.hits}")
    for e in errors[:5]:
        log(f"  error: {e['error'][:200]}")


def cmd_score(args) -> None:
    if args.judge in args.generators and not args.allow_same_judge:
        raise SystemExit("judge model is also a generator; pick another judge or pass --allow-same-judge")
    pairs = pairs_from_rows(read_jsonl(OUT / "answers.jsonl"))
    people = set(selected_participants(pairs, args.participants))
    items = [{"sample_id": f"real/{p.recording_id}/{p.question_id}", "kind": "real", "participant_id": p.participant_id,
              "recording_id": p.recording_id, "question_id": p.question_id, "question_type": p.question_type,
              "question_text": p.question_text, "condition": "REAL", "generator": None, "text": p.answer_text,
              "n_words": p.n_words} for p in pairs if p.participant_id in people and eligible(p)]
    syn = [r for r in read_jsonl(OUT / "synthetic.jsonl") if r["valid"] and r["participant_id"] in people]
    items += syn
    jobs = [(it, rep) for it in items for rep in range(args.repeats)]
    log(f"score: {len(items)} answers ({len(items) - len(syn)} real, {len(syn)} synthetic) x {args.repeats} "
        f"repeat(s) with judge {args.judge}")
    c = client(args.max_calls)
    if not args.skip_model_check:
        check_models(c, [args.judge])

    def one(job):
        it, rep = job
        resp = c.generate(build_judge_prompt(it["question_text"], it["text"]), model=args.judge,
                          system=JUDGE_SYSTEM, temperature=0.0, max_tokens=700, json_mode=True, seed=rep)
        try:
            obj = parse_json(resp.text)
        except (json.JSONDecodeError, ValueError):
            obj = None
        scores, quote_rate, problems = validate_rubric(obj, it["text"])
        keep = {k: it[k] for k in ("sample_id", "kind", "participant_id", "recording_id", "question_id",
                                   "question_type", "condition", "generator", "n_words")}
        return {**keep, "repeat": rep, "judge": args.judge, "scores": scores,
                "composite": composite(scores) if scores else None, "quote_found_rate": quote_rate,
                "problems": problems}

    results = _run_parallel(jobs, one, args.workers)
    ok = sorted((r for r in results if "error" not in r), key=lambda r: (r["sample_id"], r["repeat"]))
    write_jsonl(OUT / "scores.jsonl", ok)
    log(f"score: {len(ok)} written, {sum(r['scores'] is None for r in ok)} unparseable, "
        f"{sum('error' in r for r in results)} errors; new paid calls {c.calls}, cache hits {c.hits}")


def cmd_evaluate(args) -> None:
    rows = [r for r in read_jsonl(OUT / "scores.jsonl") if r["repeat"] == 0]
    valid = [r for r in rows if r["scores"]]
    real = [r for r in valid if r["kind"] == "real"]
    measures = list(DIMENSIONS) + ["composite", "n_words"]

    def value(r, m):
        return r["composite"] if m == "composite" else r["n_words"] if m == "n_words" else r["scores"][m]

    def compare(subset):
        out = {}
        for m in measures:
            items = [(r["participant_id"], 0, value(r, m)) for r in real] + \
                    [(r["participant_id"], 1, value(r, m)) for r in subset]
            out[m] = grouped_bootstrap_auroc(items)
        return out

    def means(group):
        return {m: round(statistics.mean(value(r, m) for r in group), 2) for m in measures} if group else {}

    syn = [r for r in valid if r["kind"] == "synthetic"]
    by_cond = defaultdict(list)
    by_gen = defaultdict(list)
    for r in syn:
        by_cond[r["condition"]].append(r)
        by_gen[r["generator"]].append(r)
    stability = {}
    reps = defaultdict(dict)
    for r in read_jsonl(OUT / "scores.jsonl"):
        if r["scores"]:
            reps[r["sample_id"]][r["repeat"]] = r["scores"]
    multi = [v for v in reps.values() if len(v) > 1]
    if multi:
        for d in DIMENSIONS:
            stability[d] = round(sum(v[0][d] == v[1][d] for v in multi) / len(multi), 4)

    summary = {
        "type": "exploratory; synthetic AI-written answers vs real MIT answers (content channel only)",
        "direction": "AUROC = P(synthetic scores higher than real); < 0.5 means synthetic scores lower",
        "ai_assistance_probability": None,
        "judge": sorted({r["judge"] for r in rows}),
        "participants": len({r["participant_id"] for r in valid}),
        "answers_scored": {"real": len(real), "synthetic": len(syn)},
        "unparseable": sum(r["scores"] is None for r in rows),
        "evidence_quote_found_rate": {
            k: round(statistics.mean(r["quote_found_rate"] for r in g if r["quote_found_rate"] is not None), 4)
            for k, g in (("real", real), ("synthetic", syn)) if any(r["quote_found_rate"] is not None for r in g)},
        "mean_scores": {"REAL": means(real), **{c: means(g) for c, g in sorted(by_cond.items())}},
        "auroc_all_synthetic": compare(syn),
        "auroc_by_condition": {c: compare(g) for c, g in sorted(by_cond.items())},
        "auroc_by_generator": {g: compare(v) for g, v in sorted(by_gen.items())},
        "repeat_exact_agreement": stability or None,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"mit-synthetic-content-{time.strftime('%Y%m%d')}.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")
    log(f"evaluate -> {out}")
    print(json.dumps({k: summary[k] for k in ("participants", "answers_scored", "unparseable", "mean_scores")}, indent=1))
    for c, res in summary["auroc_by_condition"].items():
        print(c, {m: res[m]["auroc"] for m in measures})


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("extract")
    for name in ("models", "generate", "score"):
        s = sub.add_parser(name)
        s.add_argument("--generators", nargs="+", default=DEFAULT_GENERATORS)
        s.add_argument("--judge", default=DEFAULT_JUDGE)
        if name != "models":
            s.add_argument("--participants", type=int, default=8, help="random participant subset (seeded)")
            s.add_argument("--workers", type=int, default=6)
            s.add_argument("--max-calls", type=int, default=1500, help="new paid calls allowed this run")
            s.add_argument("--skip-model-check", action="store_true")
        if name == "generate":
            s.add_argument("--conditions", nargs="+", default=list(CONDITIONS), choices=CONDITIONS)
        if name == "score":
            s.add_argument("--repeats", type=int, default=1)
            s.add_argument("--allow-same-judge", action="store_true")
    sub.add_parser("evaluate")
    args = p.parse_args(argv)
    {"extract": cmd_extract, "models": cmd_models, "generate": cmd_generate, "score": cmd_score,
     "evaluate": cmd_evaluate}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
