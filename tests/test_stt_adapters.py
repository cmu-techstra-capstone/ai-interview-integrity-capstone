"""STT adapters, registry and benchmark, tested with fake modules (no packages or models downloaded)."""

import json
import sys
import types
from pathlib import Path

import pytest

from interview_integrity.transcription.adapters.base import (
    ExternalUploadNotApproved,
    MissingOptionalDependency,
    ModelNotAvailable,
)
from interview_integrity.transcription.base import Segment, Transcriber, Transcript, Word
from interview_integrity.transcription.benchmark import Candidate, Clip, run_benchmark
from interview_integrity.transcription.registry import create_transcriber, parse_options

from .conftest import requires_ffmpeg, write_tone_wav


# ---------------------------------------------------------------- fake third-party modules

def _fake_faster_whisper(fail_load=False):
    mod = types.ModuleType("faster_whisper")
    calls = {}

    class WhisperModel:
        def __init__(self, size, **kw):
            calls["init"] = (size, kw)
            if fail_load:
                raise RuntimeError("model not in cache")

        def transcribe(self, path, **kw):
            calls["transcribe"] = (path, kw)
            W = types.SimpleNamespace
            seg = W(start=0.5, end=1.5, text=" Um, I think so.", words=[
                W(word=" Um,", start=0.5, end=0.6, probability=0.9),
                W(word=" I", start=0.7, end=0.8, probability=0.95),
                W(word=" think", start=0.8, end=1.0, probability=0.99),
                W(word=" so.", start=1.0, end=1.5, probability=0.97)])
            return iter([seg]), W(language="en")

    mod.WhisperModel = WhisperModel
    return mod, calls


def test_faster_whisper_adapter_maps_output(monkeypatch):
    mod, calls = _fake_faster_whisper()
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    t = create_transcriber("faster-whisper", model_size="small", initial_prompt="Umm")
    tr = t.transcribe("a.wav")
    assert tr.text == "Um, I think so." and tr.language == "en" and tr.provider == "faster-whisper:small"
    assert tr.has_word_timestamps and [w.text for w in tr.words] == ["Um,", "I", "think", "so."]
    assert calls["init"][1]["local_files_only"] is True  # downloads disabled by default
    assert calls["transcribe"][1]["word_timestamps"] is True and calls["transcribe"][1]["initial_prompt"] == "Umm"


def test_faster_whisper_refuses_download_by_default(monkeypatch):
    mod, _ = _fake_faster_whisper(fail_load=True)
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    with pytest.raises(ModelNotAvailable, match="downloads disabled"):
        create_transcriber("faster-whisper")


def test_missing_package_gives_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import fails
    with pytest.raises(MissingOptionalDependency, match="stt-faster-whisper"):
        create_transcriber("faster-whisper")


def test_whisperx_adapter_with_alignment_and_diarization(monkeypatch):
    wx = types.ModuleType("whisperx")
    seen = {}

    class Model:
        def transcribe(self, audio, batch_size):
            return {"language": "en", "segments": [{"start": 0.0, "end": 1.0, "text": "hello there"}]}

    wx.load_model = lambda size, device, **kw: Model()
    wx.load_audio = lambda p: "AUDIO"
    def load_align(language_code, device):
        seen["align_loads"] = seen.get("align_loads", 0) + 1
        return "ALIGN", {"lang": language_code}
    wx.load_align_model = load_align
    wx.align = lambda segs, m, meta, audio, device, return_char_alignments: {"segments": [
        {"start": 0.0, "end": 1.0, "text": "hello there",
         "words": [{"word": "hello", "start": 0.0, "end": 0.4, "score": 0.9},
                   {"word": "there", "start": 0.5, "end": 1.0, "score": 0.8}]}]}

    class Diar:
        def __init__(self, use_auth_token, device):
            seen["token"] = use_auth_token

        def __call__(self, audio):
            return "DIAR"

    wx.DiarizationPipeline = Diar

    def assign(diar, result):
        for s in result["segments"]:
            s["speaker"] = "SPEAKER_00"
        return result

    wx.assign_word_speakers = assign
    monkeypatch.setitem(sys.modules, "whisperx", wx)
    transcriber = create_transcriber("whisperx", diarize=True, hf_token="hf_x")
    tr = transcriber.transcribe("a.wav")
    transcriber.transcribe("b.wav")
    assert seen["align_loads"] == 1
    assert tr.has_word_timestamps and tr.segments[0].speaker == "SPEAKER_00" and seen["token"] == "hf_x"


def test_hosted_requires_explicit_approval():
    with pytest.raises(ExternalUploadNotApproved):
        create_transcriber("hosted")
    t = create_transcriber("hosted", vendor="x", approved_for_external_upload=True)
    with pytest.raises(NotImplementedError):
        t.transcribe("a.wav")


def test_unknown_transcriber_and_option_parsing(tmp_path):
    with pytest.raises(ValueError, match="available"):
        create_transcriber("nope")
    assert parse_options(["a=true", "b=3", "c=0.5", "d=none", "e=small"]) == \
        {"a": True, "b": 3, "c": 0.5, "d": None, "e": "small"}
    with pytest.raises(ValueError):
        parse_options(["novalue"])
    p = tmp_path / "t.txt"
    p.write_text("hi")
    assert create_transcriber("sidecar", transcript_path=str(p)).transcribe().text == "hi"


# ---------------------------------------------------------------- benchmark

class FakeSTT(Transcriber):
    def __init__(self, text, words=True, speaker=None, fail_on=None):
        self.text, self.words, self.speaker, self.fail_on = text, words, speaker, fail_on

    def transcribe(self, audio_path):
        if self.fail_on and self.fail_on in str(audio_path):
            raise RuntimeError("decode error")
        toks = self.text.split()
        ws = [Word(t, i * 0.3, i * 0.3 + 0.2) for i, t in enumerate(toks)] if self.words else []
        return Transcript([Segment(self.text, 0.0, len(toks) * 0.3, ws, speaker=self.speaker)])


def test_benchmark_compares_candidates(tmp_path):
    ref = Transcript.from_dict({"text": "Um I think so"})
    clips = [Clip("c1", tmp_path / "c1.wav", ref, 2.0), Clip("c2", tmp_path / "c2.wav", ref, 2.0)]
    systems = {"keeps": FakeSTT("um i think so", speaker="S0"), "drops": FakeSTT("i think so", words=False),
               "flaky": FakeSTT("um i think so", fail_on="c2")}

    def factory(name, **opts):
        if name == "broken":
            raise MissingOptionalDependency("not installed")
        return systems[name]

    cands = [Candidate("keeps", "keeps"), Candidate("drops", "drops"), Candidate("flaky", "flaky"),
             Candidate("broken", "broken"), Candidate("cloud", "keeps", sends_audio_externally=True)]
    report = {r["candidate"]["name"]: r for r in run_benchmark(cands, clips, factory)["results"]}
    assert report["keeps"]["corpus_wer"] == 0 and report["keeps"]["filler_recall"] == 1.0
    assert report["keeps"]["speaker_label_coverage"] == 1.0 and report["keeps"]["word_timestamp_coverage"] == 1.0
    assert report["drops"]["filler_recall"] == 0.0 and report["drops"]["word_timestamp_coverage"] == 0.0
    assert report["flaky"]["clips"] == 1 and "c2" in report["flaky"]["failures"]
    assert report["flaky"]["status"] == "partial"
    assert report["flaky"]["attempted_clips"] == 2 and report["flaky"]["failed_clips"] == 1
    assert report["broken"]["status"] == "unavailable"
    assert report["cloud"]["status"] == "skipped"  # external upload not approved
    assert report["keeps"]["real_time_factor"] is not None


def test_benchmark_all_decode_failures_are_failed(tmp_path):
    ref = Transcript.from_dict({"text": "hello"})
    clips = [Clip("bad", tmp_path / "bad.wav", ref, 1.0)]
    report = run_benchmark([Candidate("broken", "fake")], clips,
                           lambda name, **opts: FakeSTT("hello", fail_on="bad"))
    result = report["results"][0]
    assert result["status"] == "failed"
    assert result["clips"] == 0 and result["failed_clips"] == 1
    assert result["real_time_factor"] is None


@requires_ffmpeg
def test_run_stt_benchmark_from_local_dirs(tmp_path, monkeypatch):
    from interview_integrity import services
    from interview_integrity.transcription import registry

    audio, refs = tmp_path / "audio", tmp_path / "refs"
    audio.mkdir(); refs.mkdir()
    write_tone_wav(audio / "clip1.wav", [(0.2, 0.8)], duration=1.0)
    (refs / "clip1.txt").write_text("hello world")
    cands = tmp_path / "c.json"
    cands.write_text(json.dumps({"candidates": [{"name": "fake", "transcriber": "fake"}]}))
    monkeypatch.setitem(registry.TRANSCRIBERS, "fake", (lambda **o: FakeSTT("hello world"), "test"))
    report = services.run_stt_benchmark(cands, audio_dir=audio, reference_dir=refs, cache_dir=tmp_path / "cache",
                                        report_path=tmp_path / "r.json")
    assert report["results"][0]["corpus_wer"] == 0
    assert json.loads((tmp_path / "r.json").read_text())["clips"] == ["clip1"]
    assert list((tmp_path / "cache").iterdir()) == []


def test_example_candidate_config_is_valid():
    from interview_integrity.transcription.benchmark import load_candidates
    from interview_integrity.transcription.registry import TRANSCRIBERS

    cands = load_candidates(Path(__file__).resolve().parents[1] / "config" / "stt_candidates.example.json")
    assert cands and all(c.transcriber in TRANSCRIBERS for c in cands)
    assert all(c.sends_audio_externally == (c.transcriber == "hosted") for c in cands)
