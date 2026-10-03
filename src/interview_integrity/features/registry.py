"""Registry of every feature the pipeline emits: modality, kind, unit and requirements.

``kind`` keeps recording quality separate from behaviour:

* ``behavioral``: a measurement of how the answer was delivered/phrased (may become evidence later)
* ``quality``: recording/processing quality (noise, clipping, silence). **Never evidence of AI
  assistance**; it only qualifies how much other signals can be trusted
* ``provenance``: how a value was produced (sources, versions)

Plug-in features are resolved by prefix: ``visual_*`` → visual/behavioral,
``quality_*`` → quality. A test checks that every core feature is registered.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any


class Modality(str, enum.Enum):
    AUDIO = "audio"
    TRANSCRIPT = "transcript"
    VISUAL = "visual"
    RECORDING = "recording"
    PROCESSING = "processing"


class FeatureKind(str, enum.Enum):
    BEHAVIORAL = "behavioral"
    QUALITY = "quality"
    PROVENANCE = "provenance"


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    modality: Modality
    kind: FeatureKind
    unit: str
    description: str
    requires: tuple[str, ...] = ()


A, T, R, P = Modality.AUDIO, Modality.TRANSCRIPT, Modality.RECORDING, Modality.PROCESSING
B, Q, V = FeatureKind.BEHAVIORAL, FeatureKind.QUALITY, FeatureKind.PROVENANCE
SI = ("speech intervals",)

_SPECS = [
    # transcript (linguistic)
    FeatureSpec("word_count", T, B, "words", "Number of words in the answer", ("transcript",)),
    FeatureSpec("sentence_count", T, B, "sentences", "Sentences (needs punctuation)", ("transcript",)),
    FeatureSpec("avg_sentence_length", T, B, "words", "Mean words per sentence", ("transcript",)),
    FeatureSpec("type_token_ratio", T, B, "ratio", "Unique words / words", ("transcript",)),
    FeatureSpec("mattr", T, B, "ratio", "Moving-average type-token ratio (window 50)", ("transcript",)),
    FeatureSpec("filler_word_count", T, B, "count", "Filled pauses (um, uh…) + 'you know', 'I mean'", ("transcript",)),
    FeatureSpec("filler_rate_per_100_words", T, B, "per 100 words", "Fillers per 100 words", ("transcript",)),
    FeatureSpec("discourse_marker_count", T, B, "count", "Ambiguous markers (like, so, actually…)", ("transcript",)),
    FeatureSpec("repetition_count", T, B, "count", "Immediate word / word-pair repeats", ("transcript",)),
    FeatureSpec("self_correction_count", T, B, "count", "Repeats + repair phrases (heuristic)", ("transcript",)),
    FeatureSpec("qa_content_word_overlap", T, B, "ratio", "Share of question content words used in the answer",
                ("transcript", "question_text")),
    FeatureSpec("qa_semantic_similarity", T, B, "score", "Placeholder; null until a model is approved",
                ("similarity model",)),
    # audio timing
    FeatureSpec("speech_duration", A, B, "s", "Detected speech time in the answer window", SI),
    FeatureSpec("silence_duration", A, B, "s", "Answer duration minus speech duration", SI),
    FeatureSpec("pause_count", A, B, "count", "Gaps ≥ 0.3 s between speech", SI),
    FeatureSpec("long_pause_count", A, B, "count", "Pauses ≥ 1.0 s", SI),
    FeatureSpec("mean_pause_duration", A, B, "s", "Mean pause length", SI),
    FeatureSpec("max_pause_duration", A, B, "s", "Longest pause", SI),
    FeatureSpec("pause_duration_std", A, B, "s", "Std of pause lengths (≥ 2 pauses)", SI),
    FeatureSpec("total_pause_duration", A, B, "s", "Sum of pauses", SI),
    FeatureSpec("pause_ratio", A, B, "ratio", "Total pause / answer duration", SI),
    FeatureSpec("speech_segment_count", A, B, "count", "Continuous speech runs", SI),
    FeatureSpec("mean_speech_segment_duration", A, B, "s", "Mean speech-run length", SI),
    FeatureSpec("speech_segment_duration_std", A, B, "s", "Std of speech-run lengths", SI),
    FeatureSpec("speech_rate_wpm", A, B, "words/min", "Words / answer duration", ("transcript",) + SI),
    FeatureSpec("articulation_rate_wpm", A, B, "words/min", "Words / speech duration", ("transcript",) + SI),
    FeatureSpec("speech_rate_cv", A, B, "ratio", "Variation of words/s across segments", ("word timestamps",)),
    FeatureSpec("speech_level_mean_dbfs", A, B, "dBFS", "Mean speech loudness (gain-dependent)", SI),
    FeatureSpec("speech_level_std_db", A, B, "dB", "Loudness variation during speech", SI),
    FeatureSpec("speech_level_range_db", A, B, "dB", "p90 − p10 speech loudness", SI),
    # recording quality: never evidence
    FeatureSpec("audio_duration", R, Q, "s", "Length of the extracted audio"),
    FeatureSpec("audio_peak_dbfs", R, Q, "dBFS", "Peak sample level"),
    FeatureSpec("audio_noise_floor_dbfs", R, Q, "dBFS", "10th-percentile frame level"),
    FeatureSpec("audio_speech_level_dbfs", R, Q, "dBFS", "95th-percentile frame level"),
    FeatureSpec("audio_snr_db", R, Q, "dB", "Rough energy SNR (speech level − noise floor)"),
    FeatureSpec("audio_clipping_ratio", R, Q, "ratio", "Share of full-scale samples"),
    FeatureSpec("audio_is_silent", R, Q, "flag", "Peak below −60 dBFS"),
    FeatureSpec("audio_is_noisy", R, Q, "flag", "SNR below 15 dB"),
    FeatureSpec("audio_is_clipped", R, Q, "flag", "Clipping above 1%"),
    # provenance
    FeatureSpec("timing_source", P, V, "label", "word_timestamps or energy_vad"),
    FeatureSpec("transcript_source", P, V, "label", "Transcriber/provider that produced the transcript"),
]

FEATURES: dict[str, FeatureSpec] = {s.name: s for s in _SPECS}
PLUGIN_PREFIXES: dict[str, tuple[Modality, FeatureKind]] = {
    "visual_": (Modality.VISUAL, FeatureKind.BEHAVIORAL),
    "quality_": (Modality.PROCESSING, FeatureKind.QUALITY),
}


def spec_for(name: str) -> FeatureSpec | None:
    if name in FEATURES:
        return FEATURES[name]
    for prefix, (modality, kind) in PLUGIN_PREFIXES.items():
        if name.startswith(prefix):
            return FeatureSpec(name, modality, kind, "", "plug-in feature")
    return None


def split_by_kind(features: dict[str, Any]) -> dict[FeatureKind | None, dict[str, Any]]:
    """Group a row's features by kind (``None`` = unregistered)."""
    out: dict[FeatureKind | None, dict[str, Any]] = {}
    for name, value in features.items():
        spec = spec_for(name)
        out.setdefault(spec.kind if spec else None, {})[name] = value
    return out
