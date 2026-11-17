"""Load a speaker-labelled interview transcript for ``analyze_video``.

Accepted inputs (the analysis needs to know who asked and who answered):

1. Text in the MIT style: ``Interviewer: ...|Interviewee: ...``.
2. JSON list of turns: ``[{"speaker": "interviewer", "text": "...", "start": 1.0, "end": 4.2,
   "words": [{"text": "So", "start": 1.0, "end": 1.2}, ...]}, ...]``. Times and words are optional.
3. ``analysis.v1`` style: an object with ``answers[].transcript_segments`` or a top-level
   ``transcript_segments`` list (``speaker``, ``text``, ``start_seconds``/``end_seconds``, ``words``).

Speakers named ``interviewer`` / ``interviewee`` / ``candidate`` are recognised. Other names (e.g.
Meet display names) need ``interviewer_names``; everyone else is treated as the candidate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .turns import INTERVIEWEE, INTERVIEWER, TimedTurn, Turn, Word, parse_turker_transcript

ROLE_ALIASES = {"interviewer": INTERVIEWER, "interviewee": INTERVIEWEE, "candidate": INTERVIEWEE}


class TranscriptError(ValueError):
    pass


def _role(speaker: str, interviewer_names: set[str]) -> str:
    s = (speaker or "").strip()
    if s.lower() in ROLE_ALIASES:
        return ROLE_ALIASES[s.lower()]
    if interviewer_names:
        return INTERVIEWER if s.lower() in interviewer_names else INTERVIEWEE
    raise TranscriptError(f"unknown speaker {speaker!r}; pass interviewer_names (e.g. the interviewer's display name)")


def _num(seg: dict, *keys) -> float | None:
    for k in keys:
        v = seg.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def _segments(obj: Any) -> list[dict]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        if isinstance(obj.get("transcript_segments"), list):
            return obj["transcript_segments"]
        if isinstance(obj.get("turns"), list):
            return obj["turns"]
        if isinstance(obj.get("answers"), list):
            segs = [s for a in obj["answers"] for s in (a.get("transcript_segments") or [])]
            if segs:
                return segs
    raise TranscriptError("JSON transcript must be a list of turns or contain transcript_segments")


def turns_from_segments(segments: Iterable[dict], interviewer_names: Iterable[str] = ()) -> list[Turn] | list[TimedTurn]:
    """Merge consecutive same-speaker segments. Returns TimedTurns only if every segment has times."""
    names = {n.strip().lower() for n in interviewer_names if n.strip()}
    merged: list[dict] = []
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        role = _role(str(seg.get("speaker", "")), names)
        start, end = _num(seg, "start", "start_seconds"), _num(seg, "end", "end_seconds")
        words = tuple(Word(str(w.get("text", "")).strip(), float(w["start"]), float(w["end"]))
                      for w in (seg.get("words") or []) if _num(w, "start") is not None and _num(w, "end") is not None)
        if merged and merged[-1]["speaker"] == role:
            m = merged[-1]
            m["text"] = f"{m['text']} {text}"
            m["end"] = end if end is not None else m["end"]
            m["timed"] = m["timed"] and start is not None and end is not None
            m["words"] += words
        else:
            merged.append({"speaker": role, "text": text, "start": start, "end": end,
                           "timed": start is not None and end is not None, "words": words})
    if not merged:
        raise TranscriptError("transcript has no text")
    if all(m["timed"] for m in merged):
        return [TimedTurn(m["speaker"], m["text"], m["start"], m["end"], 1.0, True, True,
                          tuple(sorted(m["words"], key=lambda w: (w.start, w.end)))) for m in merged]
    return [Turn(m["speaker"], m["text"]) for m in merged]


def load_transcript(path: str | Path, interviewer_names: Iterable[str] = ()) -> list[Turn] | list[TimedTurn]:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        return turns_from_segments(_segments(json.loads(raw)), interviewer_names)
    turns = parse_turker_transcript(raw)
    if not turns:
        raise TranscriptError("text transcript needs 'Interviewer: ...|Interviewee: ...' turns")
    return turns


def needs_asr(turns: list[Turn] | list[TimedTurn]) -> bool:
    """ASR word timings are needed when turns are untimed or carry no word-level times."""
    if not turns or not isinstance(turns[0], TimedTurn):
        return True
    return not any(t.words for t in turns if t.speaker == INTERVIEWEE)
