"""Demo scoring engine: explainable 0-9 "signal of possible AI assistance" score.

IMPORTANT (read before presenting): this is a transparent, hand-weighted DEMO HEURISTIC built
on the repo's linguistic/timing features. It is NOT a trained or validated detector, it has no
measured accuracy, and it must be shown as decision support only - never as proof of misconduct.
Many ASR systems drop disfluencies ("um", "uh"), which makes natural speech look more polished.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from interview_integrity.features.linguistic import extract_linguistic_features  # noqa: E402

# ----------------------------------------------------------------------------- lexicons

TRANSITIONS = [
    "furthermore", "moreover", "additionally", "in addition", "in conclusion", "to summarize",
    "in summary", "overall", "consequently", "ultimately", "importantly", "it is important",
    "it's important", "it is worth noting", "worth noting", "firstly", "secondly", "thirdly",
    "first and foremost", "on the other hand", "as a result", "by doing so", "this ensures",
    "this allows", "this approach", "key takeaway", "at the end of the day",
]
AI_WORDS = [
    "leverage", "leveraging", "robust", "comprehensive", "holistic", "seamless", "seamlessly",
    "delve", "pivotal", "crucial", "foster", "streamline", "facilitate", "ensure", "ensuring",
    "optimize", "scalable", "stakeholders", "synergy", "cutting-edge", "best practices",
    "multifaceted", "landscape", "paradigm", "underscores", "enhance", "navigate", "actionable",
    "proactive", "end-to-end", "mitigate", "alignment", "impactful",
]
HEDGES = [
    "i think", "i guess", "maybe", "kind of", "sort of", "probably", "i'm not sure", "not sure",
    "i don't know", "i believe", "pretty much", "a bit", "honestly", "to be honest", "i suppose",
    "or something", "i don't remember", "if i remember",
]
PERSONAL = [
    "i remember", "when i was", "my manager", "my team", "my last", "my previous", "i once",
    "one time", "i worked", "we had", "our team", "i built", "i led", "back at", "at my",
    "in my last", "my boss", "my professor", "my friend", "my teammate", "i broke", "i messed",
    "i got", "we shipped", "i shipped",
]

# Zones on the 0-9 scale (as requested for the demo): 0-3.9 low, 4-5.9 review, 6-9 high.
ZONES = [(0.0, 4.0, "low", "#22c55e"), (4.0, 6.0, "review", "#f59e0b"), (6.0, 9.01, "high", "#ef4444")]

PRIOR = 0.25  # neutral starting point that short/low-evidence answers shrink toward


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def zone_for(score: float) -> tuple[str, str]:
    for lo, hi, name, color in ZONES:
        if lo <= score < hi:
            return name, color
    return "high", "#ef4444"


def _phrase_count(text_lower: str, phrases: list[str]) -> int:
    n = 0
    for p in phrases:
        n += len(re.findall(r"(?<![a-z'])" + re.escape(p) + r"(?![a-z'])", text_lower))
    return n


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if re.search(r"[A-Za-z0-9]", s)]


def _proper_nouns(text: str) -> int:
    count, prev = 0, ""
    for i, tok in enumerate(text.split()):
        core = tok.strip(".,;:!?()\"'")
        if (
            i > 0
            and len(core) > 2
            and core[0].isupper()
            and core != "I"
            and not core.isupper()
            and prev
            and prev[-1] not in ".!?"
        ):
            count += 1
        prev = tok
    return count


def _structure_markers(text: str) -> int:
    n = len(re.findall(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+\S", text))
    n += len(re.findall(r"\*\*[^*]+\*\*", text))
    n += len(re.findall(r"\b(?:first|second|third|finally)\b[,:]", text.lower()))
    return n


# ----------------------------------------------------------------------------- text scoring


def score_text(answer: str, question: str | None = None) -> dict[str, Any]:
    """Score ONE candidate answer. Returns raw 0-1 likelihood, confidence and per-signal evidence."""
    answer = (answer or "").strip()
    feats = extract_linguistic_features(answer, question_text=question)
    wc = int(feats["word_count"] or 0)
    low = answer.lower()
    per100 = (lambda n: 100.0 * n / wc) if wc else (lambda n: 0.0)
    signals: list[dict[str, Any]] = []

    def add(name: str, label: str, value: float, weight: float, detail: str) -> None:
        signals.append(
            {"name": name, "label": label, "value": round(clamp(value), 3), "weight": weight,
             "detail": detail, "fired": value >= 0.55}
        )

    if wc >= 20:
        hedge_n = _phrase_count(low, HEDGES)
        disfl = (feats["filler_rate_per_100_words"] or 0) + per100(feats["self_correction_count"] or 0) + 0.6 * per100(hedge_n)
        v = 1 - disfl / 4.0
        add(
            "spontaneity", "Few spontaneous-speech markers", v, 0.28,
            f"{feats['filler_word_count']} fillers, {feats['self_correction_count']} repeats/self-corrections, "
            f"{hedge_n} hedges in {wc} words"
            + (" - natural speech usually has some" if v >= 0.55 else " - looks naturally disfluent"),
        )

    trans_n = _phrase_count(low, TRANSITIONS)
    struct_n = _structure_markers(answer)
    if wc >= 15:
        v = clamp(per100(trans_n) / 2.0) * 0.75 + (0.5 if struct_n else 0.0) + (0.15 if struct_n >= 3 else 0.0)
        add(
            "polish", "Polished transitions / list-like structure", v, 0.22,
            f"{trans_n} formal transitions, {struct_n} list/enumeration markers"
            + (" - reads like a prepared or generated answer" if v >= 0.55 else ""),
        )

    if wc >= 15:
        ai_n = _phrase_count(low, AI_WORDS)
        v = per100(ai_n) / 2.0
        add("buzzwords", "Generic buzzword vocabulary", v, 0.15,
            f"{ai_n} buzzwords per {wc} words" + (" (e.g. leverage/robust/comprehensive)" if ai_n else ""))

    sents = _sentences(answer)
    if len(sents) >= 3:
        lens = [len(s.split()) for s in sents]
        mean = sum(lens) / len(lens)
        sd = (sum((x - mean) ** 2 for x in lens) / len(lens)) ** 0.5
        cv = sd / mean if mean else 0
        v = clamp((0.6 - cv) / 0.35) * (1.0 if 12 <= mean <= 32 else 0.5)
        add("rhythm", "Uniform sentence length", v, 0.13,
            f"sentence length averages {mean:.0f} words, variation {cv:.2f}"
            + (" - unusually even" if v >= 0.55 else ""))

    if wc >= 30:
        specifics = (
            _phrase_count(low, PERSONAL) + 0.5 * len(re.findall(r"\d+", answer)) + 0.7 * _proper_nouns(answer)
        )
        v = 1 - per100(specifics) / 3.0
        add("generic", "Lacks personal / concrete detail", v, 0.14,
            f"{specifics:.1f} personal/concrete cues in {wc} words"
            + (" - answer stays generic" if v >= 0.55 else " - contains concrete detail"))

    if wc >= 40:
        overlap = feats["qa_content_word_overlap"]
        v = 0.6 * clamp((wc - 60) / 140) + 0.4 * (clamp((overlap - 0.2) / 0.5) if overlap is not None else 0)
        add("complete", "Long, fully-covering answer", v, 0.08,
            f"{wc} words" + (f", {overlap:.0%} of question terms echoed" if overlap is not None else ""))

    total_w = sum(s["weight"] for s in signals)
    raw = sum(s["value"] * s["weight"] for s in signals) / total_w if total_w else PRIOR
    conf = clamp((wc - 10) / 60)
    adj = PRIOR + conf * (raw - PRIOR)
    return {
        "word_count": wc, "raw": round(raw, 3), "confidence": round(conf, 3), "adj": round(adj, 3),
        "score": to_scale(adj), "signals": signals, "features": feats,
    }


def to_scale(adj: float) -> float:
    """Map adjusted 0-1 likelihood onto the demo's 0-9 scale."""
    return round(9 * clamp((adj - 0.05) / 0.85), 1)


# ----------------------------------------------------------------------------- timing / audio


def timing_signals(f: dict[str, Any], word_count: int | None = None) -> list[dict[str, Any]]:
    """Weak timing/cadence signals from repo timing features. UNCALIBRATED demo thresholds."""
    out: list[dict[str, Any]] = []

    def add(name, label, value, weight, detail):
        out.append({"name": name, "label": label, "value": round(clamp(value), 3), "weight": weight,
                    "detail": detail, "fired": value >= 0.55})

    dur = f.get("answer_duration") or 0
    n_seg = f.get("speech_segment_count") or 0
    mean_seg = f.get("mean_speech_segment_duration")
    std_seg = f.get("speech_segment_duration_std")
    if n_seg >= 3 and mean_seg and std_seg is not None:
        cv = std_seg / mean_seg
        add("uniform_cadence", "Even speaking bursts (reading-like cadence)", (0.9 - cv) / 0.6, 0.35,
            f"speech-burst length varies {cv:.2f} across {n_seg} bursts")
    ratio = f.get("pause_ratio")
    if ratio is not None and dur >= 8:
        add("few_pauses", "Few thinking pauses", (0.22 - ratio) / 0.14, 0.3,
            f"{ratio:.0%} of the answer is pauses ({f.get('pause_count')} pauses)")
    art = f.get("articulation_rate_wpm")
    if art:
        add("fast_fluent", "Fast, fluent delivery", (art - 155) / 45, 0.2, f"{art:.0f} words/min while speaking")
    lat = f.get("response_latency")
    if lat is not None:
        add("latency", "Long pause before a fluent answer", (lat - 2.0) / 5.0, 0.15,
            f"{lat:.1f}s between question end and answer start")
    return out


def timing_raw(signals: list[dict[str, Any]]) -> float | None:
    w = sum(s["weight"] for s in signals)
    return sum(s["value"] * s["weight"] for s in signals) / w if w else None


def combine(text: dict[str, Any] | None, timing: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Blend text (70%) and timing (30%) evidence. Either may be missing."""
    t_raw = timing_raw(timing or [])
    if text is None and t_raw is None:
        return {"adj": PRIOR, "score": to_scale(PRIOR), "confidence": 0.0}
    if text is None:
        conf = 0.5
        adj = PRIOR + conf * (t_raw - PRIOR)
    elif t_raw is None:
        return text
    else:
        raw = 0.7 * text["raw"] + 0.3 * t_raw
        conf = max(text["confidence"], 0.4)
        adj = PRIOR + conf * (raw - PRIOR)
    return {"adj": round(adj, 3), "score": to_scale(adj), "confidence": round(conf, 3)}


# ----------------------------------------------------------------------------- interview level


def parse_transcript(text: str) -> list[dict[str, str]]:
    """Parse pasted transcript into turns. Understands 'Interviewer:/Q:' and 'Candidate:/A:' labels.

    Unlabelled paragraphs (blank-line separated) are treated as candidate answers.
    """
    turns: list[dict[str, str]] = []
    label_re = re.compile(
        r"^\s*(interviewer|interviewee|candidate|question|answer|q|a|i|c)\s*[:\-]\s*(.*)$", re.I
    )
    saw_label = False
    cur: dict[str, str] | None = None
    for line in text.replace("\r", "").split("\n"):
        m = label_re.match(line)
        if m:
            saw_label = True
            who = m.group(1).lower()
            role = "interviewer" if who in ("interviewer", "question", "q", "i") else "candidate"
            cur = {"role": role, "text": m.group(2).strip()}
            turns.append(cur)
        elif cur is not None and line.strip():
            cur["text"] += " " + line.strip()
    if not saw_label:
        turns = [{"role": "candidate", "text": p.strip().replace("\n", " ")}
                 for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [t for t in turns if t["text"]]


def pair_qa(turns: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Group turns into (question, answer) pairs; consecutive candidate turns merge into one answer."""
    pairs: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for t in turns:
        if t["role"] == "interviewer":
            if cur is not None and cur["answer"]:
                pairs.append(cur)
                cur = None
            if cur is None:
                cur = {"question": t["text"], "answer": ""}
            else:
                cur["question"] += " " + t["text"]
        else:
            if cur is None:
                cur = {"question": "", "answer": ""}
            cur["answer"] = (cur["answer"] + " " + t["text"]).strip()
    if cur is not None and cur["answer"]:
        pairs.append(cur)
    return pairs


def running_scores(items: list[dict[str, Any]], decay: float = 0.8) -> list[dict[str, Any]]:
    """Recency-weighted running score after each answer (adj/confidence from score_text)."""
    out = []
    for i in range(len(items)):
        num = den = 0.0
        for j in range(i + 1):
            w = (0.06 + items[j]["confidence"]) * (decay ** (i - j))
            num += w * items[j]["adj"]
            den += w
        adj = num / den if den else PRIOR
        score = to_scale(adj)
        zone, color = zone_for(score)
        out.append({"running_score": score, "zone": zone, "color": color})
    return out


def score_interview(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Score every Q/A pair and the recency-weighted running score after each."""
    results = []
    for p in pairs:
        r = score_text(p["answer"], p.get("question"))
        zone, color = zone_for(r["score"])
        r.update(question=p.get("question", ""), answer=p["answer"], zone=zone, color=color)
        results.append(r)
    runs = running_scores(results)
    for r, run in zip(results, runs):
        r.update(run)
    final = runs[-1] if runs else {"running_score": 0.0, "zone": "low", "color": ZONES[0][3]}
    return {"turns": results, "overall": final}
