"""Two-second sanity check: python demo/smoke_test.py  (no installs needed)."""

import json
import sys
from pathlib import Path

import scoring
from samples import SAMPLES

ok = True


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok
    ok = ok and cond
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


for key in ("natural", "ai", "mixed"):
    r = scoring.score_interview(scoring.pair_qa(SAMPLES[key]["turns"]))
    check(f"sample '{key}' scores", len(r["turns"]) == 5, f"final running {r['overall']['running_score']} ({r['overall']['zone']})")
    if key == "natural":
        check("natural stays LOW", r["overall"]["zone"] == "low")
    if key == "ai":
        check("ai-style reaches HIGH", r["overall"]["zone"] == "high")
    if key == "mixed":
        runs = [t["running_score"] for t in r["turns"]]
        check("mixed climbs over time", runs[-1] > runs[0] + 4, " -> ".join(str(x) for x in runs))

tdir = Path(__file__).resolve().parents[1] / "processed" / "transcripts" / "michigan_deception"
files = sorted(tdir.glob("*.json"))
if files:
    high = sum(1 for f in files if scoring.score_text(json.loads(f.read_text())["text"])["score"] >= 6)
    check("real human clips: none flagged HIGH", high == 0, f"{high}/{len(files)} high")
else:
    print("SKIP real-human check (processed/transcripts not found on this branch)")

sys.exit(0 if ok else 1)
