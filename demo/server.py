"""Zero-install local demo server (Python standard library only).

    python demo/server.py            # then open http://127.0.0.1:8765

Binds to localhost only. Optional env vars for LLM follow-up questions:
    ANTHROPIC_API_KEY  (or OPENROUTER_API_KEY), DEMO_LLM_MODEL
Without a key, follow-ups use an offline template fallback.
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
import tempfile
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import audio
import followups
import scoring
from samples import SAMPLES

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
MAX_BODY = 300 * 1024 * 1024
_baseline_cache: dict | None = None


def baseline() -> dict:
    """Score the repo's real human transcripts (Michigan deception clips) as a false-positive sanity check."""
    global _baseline_cache
    if _baseline_cache is None:
        files = sorted(glob.glob(str(REPO / "processed" / "transcripts" / "michigan_deception" / "*.json")))
        if not files:
            return {"available": False}
        scores = []
        for f in files:
            text = json.loads(Path(f).read_text()).get("text", "")
            scores.append(scoring.score_text(text)["score"])
        _baseline_cache = {
            "available": True, "clips": len(scores), "mean": round(statistics.mean(scores), 2),
            "low": sum(1 for s in scores if s < 4), "review": sum(1 for s in scores if 4 <= s < 6),
            "high": sum(1 for s in scores if s >= 6),
        }
    return _baseline_cache


class Handler(BaseHTTPRequestHandler):
    server_version = "InterviewIntegrityDemo/1.0"

    def log_message(self, fmt, *args):  # quiet; never log request bodies
        pass

    # ---- helpers
    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj).encode(), "application/json")

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("upload too large")
        return self.rfile.read(n)

    # ---- routes
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/samples":
            self._json(SAMPLES)
        elif path == "/api/baseline":
            self._json(baseline())
        elif path == "/api/config":
            import os

            llm = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENROUTER_API_KEY"))
            self._json({"llm": llm})
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        url = urlparse(self.path)
        try:
            if url.path == "/api/audio":
                self._json(self._audio(parse_qs(url.query)))
                return
            data = json.loads(self._body() or b"{}")
            if url.path == "/api/parse":
                self._json({"turns": scoring.parse_transcript(data.get("text", ""))})
            elif url.path == "/api/score":
                pairs = scoring.pair_qa(data.get("turns", []))
                self._json(scoring.score_interview(pairs))
            elif url.path == "/api/followups":
                self._json(followups.suggest(
                    data.get("question", ""), data.get("answer", ""), data.get("signals", []), data.get("history", [])
                ))
            elif url.path == "/api/score_combined":
                text = scoring.score_text(data.get("answer", ""), data.get("question"))
                combined = scoring.combine(text, data.get("timing_signals", []))
                zone, color = scoring.zone_for(combined["score"])
                self._json({"text_score": text["score"], "combined": combined, "zone": zone, "color": color,
                            "signals": text["signals"]})
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as exc:  # demo server: report errors to the UI instead of dying
            traceback.print_exc()
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 400)

    def _audio(self, q: dict) -> dict:
        raw = self._body()
        name = Path((q.get("filename") or ["upload"])[0]).name or "upload"
        suffix = Path(name).suffix.lower() or ".bin"
        qe = (q.get("question_end") or [""])[0]
        question_end = float(qe) if qe.strip() else None
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"input{suffix}"
            src.write_bytes(raw)
            wav = audio.ensure_wav(src, Path(tmp))
            transcript = None
            words = None
            word_count = None
            if (q.get("transcribe") or ["0"])[0] == "1":
                t = audio.try_transcribe(wav)
                if t:
                    transcript, words = t["text"], t["words"]
                    word_count = len(words)
            res = audio.analyze(wav, question_end=question_end, word_count=word_count, words=words)
            res["transcript"] = transcript
            if (q.get("transcribe") or ["0"])[0] == "1" and transcript is None:
                res["warnings"].append("Transcription skipped: faster-whisper is not installed. Paste the transcript instead.")
            return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Demo running at http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
