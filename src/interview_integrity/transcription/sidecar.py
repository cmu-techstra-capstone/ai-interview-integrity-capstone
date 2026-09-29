"""Load an existing transcript file instead of running speech-to-text.

Useful for (a) manual/corrected transcripts of staged interviews, (b) public
datasets that ship transcripts, and (c) running the pipeline before an ASR
provider has been chosen.

Supported formats: ``.json`` (see ``Transcript.from_dict``) and ``.txt`` (plain
text, no timestamps).
"""

from __future__ import annotations

import json
from pathlib import Path

from .base import Transcriber, Transcript, TranscriptionError


class SidecarTranscriber(Transcriber):
    name = "sidecar"

    def __init__(self, transcript_path: str | Path):
        self.transcript_path = Path(transcript_path)

    def transcribe(self, audio_path: str | Path | None = None) -> Transcript:
        path = self.transcript_path
        if not path.is_file():
            raise FileNotFoundError(f"Transcript file not found: {path}")
        suffix = path.suffix.lower()
        if suffix == ".json":
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                raise TranscriptionError(f"Transcript {path} is not valid JSON: {exc}") from exc
            transcript = Transcript.from_dict(data)
        elif suffix == ".txt":
            transcript = Transcript.from_dict({"text": path.read_text()})
        else:
            raise TranscriptionError(f"Unsupported transcript format '{suffix}' (use .json or .txt)")
        transcript.provider = transcript.provider or f"sidecar:{path.name}"
        return transcript
