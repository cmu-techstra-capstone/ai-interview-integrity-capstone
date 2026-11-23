"""Hosted STT placeholder (Deepgram / AssemblyAI / OpenAI, etc.). Not implemented.

Sending interview audio to a third party requires explicit project approval (consent,
privacy, licence). This class refuses to run unless that approval is passed in
explicitly, and even then only raises NotImplementedError until a vendor is approved.
"""

from __future__ import annotations

from pathlib import Path

from ..base import Transcriber, Transcript
from .base import ExternalUploadNotApproved


class HostedTranscriberPlaceholder(Transcriber):
    name = "hosted"

    def __init__(self, vendor: str = "unspecified", *, approved_for_external_upload: bool = False):
        if not approved_for_external_upload:
            raise ExternalUploadNotApproved(
                "Hosted STT would send audio to a third party. This has not been approved; "
                "see docs/stt-decision.md."
            )
        self.vendor = vendor

    def transcribe(self, audio_path: str | Path) -> Transcript:
        raise NotImplementedError(f"Hosted STT adapter for {self.vendor!r} is not implemented (pending approval).")
