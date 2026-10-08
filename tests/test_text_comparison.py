"""Offline comparison mechanics, NOT AI-detection accuracy tests."""
import json
import importlib.util
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from interview_integrity.modeling.text_comparison import (
    BASE_REPO, Candidate, COMMON_MAX_TOKENS, MODEL_FILES, MODELS,
    _snapshot, _superannotate_model, compare, load_samples,
    validate_config, validated_scores,
)

TEXT = " ".join(f"word{i}" for i in range(60)) + "  um, I-I think.\nLike this."
SUPER_CONFIG = {"pretrain_checkpoint": BASE_REPO, "num_labels": 1,
                "id2label": {"0": "GENERATED"}, "classifier_dropout": 0.1}


class FakeDetector:
    def __init__(self, count=100, scores=None):
        self.count = count
        self.scores = scores if scores is not None else {"ai_text_score": 0.25, "human_score": 0.75}
        self.inputs = []

    def token_count(self, text):
        self.inputs.append(("token_count", text))
        return self.count

    def score(self, text):
        self.inputs.append(("score", text))
        return self.scores


def make_manifest(tmp_path, text=TEXT, language="en"):
    source = tmp_path / "AI_GENERATED.txt"
    source.write_text(text)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"candidate_only": True, "samples": [
        {"id": "sample", "path": source.name, "language": language,
         "provenance": {"assistance": "AI_GENERATED", "label_verified": True}}
    ]}))
    return manifest, source


def run_fake(tmp_path, detector, **kwargs):
    manifest, source = make_manifest(tmp_path, **kwargs)
    result = compare(manifest, tmp_path / "out", model_names=list(MODELS),
                     cache_root=tmp_path / "cache", factory=lambda name, cache: detector)
    return result, source


def test_official_semantics_are_not_hc3_order():
    assert MODELS["mage"]["ai_index"] == 0 and MODELS["hc3"]["ai_index"] == 1
    validate_config("mage", {"model_type": "longformer", "id2label": {"0": 0, "1": 1}})
    validate_config("superannotate", SUPER_CONFIG)


@pytest.mark.parametrize("name,config", [
    ("mage", {"model_type": "roberta", "id2label": {"0": 0, "1": 1}}),
    ("mage", {"model_type": "longformer", "id2label": {"0": 1, "1": 0}}),
    ("superannotate", {**SUPER_CONFIG, "num_labels": 2}),
    ("superannotate", {**SUPER_CONFIG, "id2label": {"0": "HUMAN"}}),
    ("superannotate", {**SUPER_CONFIG, "pretrain_checkpoint": "unknown"}),
])
def test_wrong_checkpoint_configs_rejected(name, config):
    with pytest.raises(ValueError, match="Unexpected"):
        validate_config(name, config)


@pytest.mark.parametrize("scores", [
    {}, None, {"ai_text_score": 0.2},
    {"ai_text_score": math.nan, "human_score": 0.5},
    {"ai_text_score": 0.2, "human_score": 0.2},
    {"ai_text_score": True, "human_score": 0},
    {"ai_text_score": 0.25, "human_score": 0.75, "raw_logits": ["bad"]},
    {"ai_text_score": 0.25, "human_score": 0.75, "raw_logits": [math.inf]},
])
def test_invalid_scores_rejected(scores):
    with pytest.raises(ValueError, match="scores|logits"):
        validated_scores(scores)


def test_identical_frozen_text_no_label_leakage_or_source_changes(tmp_path):
    detector = FakeDetector()
    result, source = run_fake(tmp_path, detector)
    assert detector.inputs == [("token_count", TEXT), ("score", TEXT)] * 3
    assert source.read_text() == TEXT
    assert len({r["text_sha256"] for r in result["rows"]}) == 1
    assert len({r["source_sha256"] for r in result["rows"]}) == 1
    assert all(r["status"] == "scored_exploratory" and not r["text_truncated"] for r in result["rows"])
    assert result["integrity_status"] == "verified"
    assert result["accuracy_estimated"] is False and result["selected_model"] is None
    assert result["verdict"] is None and result["confidence"] is None
    assert result["asr_rerun"] is False and result["retrained"] is False
    assert result["threshold_selected"] is False and result["sends_content_externally"] is False
    assert (tmp_path / "out/inputs/sample.txt").read_text() == TEXT + "\n"
    assert "No winner or threshold selected" in (tmp_path / "out/report.md").read_text()


@pytest.mark.parametrize("text,language,count,status", [
    ("too short", "en", 100, "insufficient_text"),
    (TEXT, None, 100, "unsupported_or_unknown_language"),
    (TEXT, "zh", 100, "unsupported_or_unknown_language"),
    (TEXT, "en", COMMON_MAX_TOKENS + 1, "answer_exceeds_common_capacity"),
])
def test_abstention_never_calls_score(tmp_path, text, language, count, status):
    detector = FakeDetector(count=count)
    result, _ = run_fake(tmp_path, detector, text=text, language=language)
    assert all(r["status"] == status and r["ai_text_score"] is None for r in result["rows"])
    assert not any(operation == "score" for operation, _ in detector.inputs)


@pytest.mark.parametrize("count", [0, True, -1, 2.5])
def test_invalid_token_counts_are_not_scored(tmp_path, count):
    detector = FakeDetector(count=count)
    result, _ = run_fake(tmp_path, detector)
    assert all(r["status"] == "inference_error" and r["ai_text_score"] is None for r in result["rows"])
    assert not any(operation == "score" for operation, _ in detector.inputs)


def test_model_failure_is_null_and_other_models_continue(tmp_path):
    manifest, _ = make_manifest(tmp_path)
    def factory(name, cache):
        if name == "mage":
            raise RuntimeError("missing local weights")
        return FakeDetector()
    result = compare(manifest, tmp_path / "out", model_names=list(MODELS),
                     cache_root=tmp_path, factory=factory)
    assert result["model_errors"] == {"mage": "missing local weights"}
    assert [r["status"] for r in result["rows"]] == ["scored_exploratory", "model_error", "scored_exploratory"]
    assert result["rows"][1]["ai_text_score"] is None


def test_bad_inference_scores_are_null_not_zero(tmp_path):
    result, _ = run_fake(tmp_path, FakeDetector(scores={"ai_text_score": math.nan, "human_score": 1}))
    assert all(r["status"] == "inference_error" and r["ai_text_score"] is None for r in result["rows"])


@pytest.mark.parametrize("data", [
    [], {}, {"candidate_only": False, "samples": []},
    {"candidate_only": True, "samples": [None]},
    {"candidate_only": True, "samples": [{"id": "../../bad", "path": "x.txt"}]},
    {"candidate_only": True, "samples": [{"id": "sample", "path": "x.txt", "provenance": []}]},
])
def test_invalid_manifest(tmp_path, data):
    manifest = tmp_path / "bad.json"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_samples(manifest)


def test_duplicate_ids_and_models_rejected(tmp_path):
    manifest, _ = make_manifest(tmp_path)
    data = json.loads(manifest.read_text())
    data["samples"].append(data["samples"][0])
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="duplicate sample"):
        load_samples(manifest)
    with pytest.raises(ValueError, match="duplicate model"):
        compare(manifest, tmp_path / "out", model_names=["mage", "mage"], cache_root=tmp_path)
    assert not (tmp_path / "out").exists()


def test_existing_output_never_overwritten(tmp_path):
    manifest, _ = make_manifest(tmp_path)
    with pytest.raises(ValueError, match="already exists"):
        compare(manifest, tmp_path, model_names=["hc3"], cache_root=tmp_path)


def test_source_mutation_marks_saved_run_invalid(tmp_path):
    manifest, source = make_manifest(tmp_path)
    def factory(name, cache):
        source.write_text("changed")
        return FakeDetector()
    with pytest.raises(ValueError, match="changed during comparison"):
        compare(manifest, tmp_path / "out", model_names=["hc3"], cache_root=tmp_path, factory=factory)
    saved = json.loads((tmp_path / "out/comparison.json").read_text())
    assert saved["integrity_status"] == "failed"
    assert not (tmp_path / "out/report.md").exists()


def test_cached_snapshot_only_requires_downloaded_files(monkeypatch, tmp_path):
    calls = []
    def snapshot(repo, **kwargs):
        calls.append((repo, kwargs))
        return str(tmp_path)
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=snapshot))
    assert _snapshot("mage", tmp_path) == tmp_path
    repo, args = calls[0]
    assert repo == MODELS["mage"]["repo"] and args["revision"] == MODELS["mage"]["revision"]
    assert args["local_files_only"] is True and args["token"] is False
    assert args["allow_patterns"] == MODEL_FILES + ["pytorch_model.bin"]


@pytest.mark.parametrize("name,expected", [("mage", 0.75), ("superannotate", 0.75)])
def test_tensor_class_order_and_custom_sigmoid(name, expected):
    torch = pytest.importorskip("torch")
    candidate = Candidate.__new__(Candidate)
    candidate.name, candidate.hc3 = name, None
    candidate.tokenizer = lambda *a, **kw: {}
    candidate.token_count = lambda text: 2
    if name == "mage":
        candidate.model = lambda **kw: SimpleNamespace(logits=torch.tensor([[math.log(3), 0.]]))
    else:
        candidate.model = lambda **kw: torch.tensor([[math.log(3)]])
    scores = candidate.score(TEXT)
    assert scores["ai_text_score"] == pytest.approx(expected)
    assert scores["human_score"] == pytest.approx(1 - expected)
    assert len(scores["raw_logits"]) == (2 if name == "mage" else 1)


def test_custom_encoder_head_strict_loading_and_eval_parity(tmp_path):
    # Keep Transformers' native runtimes separate from optional audio libraries.
    # Still execute every parity/strict-loading assertion in the child; no skip
    # or forced process exit hides a failure or a native teardown exception.
    if os.environ.get("TECHSTRA_HEAD_PARITY_CHILD") != "1":
        if any(importlib.util.find_spec(name) is None for name in ("torch", "transformers", "safetensors")):
            pytest.skip("optional text-research dependencies not installed")
        child = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", f"{__file__}::test_custom_encoder_head_strict_loading_and_eval_parity"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "TECHSTRA_HEAD_PARITY_CHILD": "1"},
        )
        assert child.returncode == 0, child.stdout + child.stderr
        return
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    safetensors = pytest.importorskip("safetensors.torch")
    config = transformers.RobertaConfig(vocab_size=16, hidden_size=8, num_hidden_layers=1,
                                        num_attention_heads=2, intermediate_size=12,
                                        max_position_embeddings=32)
    encoder = transformers.RobertaModel(config, add_pooling_layer=False).eval()
    dense = torch.nn.Linear(8, 1).eval()
    state = {"roberta." + k: v.contiguous() for k, v in encoder.state_dict().items()}
    state.update({"dense." + k: v.contiguous() for k, v in dense.state_dict().items()})
    weights = tmp_path / "tiny.safetensors"
    safetensors.save_file(state, str(weights))
    loaded = _superannotate_model(SUPER_CONFIG, config.to_dict(), weights)
    inputs = {"input_ids": torch.tensor([[0, 5, 2]]), "attention_mask": torch.ones(1, 3, dtype=torch.long)}
    with torch.inference_mode():
        expected = dense(encoder(**inputs).last_hidden_state[:, 0, :])
        actual = loaded(**inputs)
    assert loaded.training is False and actual.shape == (1, 1)
    torch.testing.assert_close(actual, expected)
    state.pop("dense.weight")
    safetensors.save_file(state, str(weights))
    with pytest.raises(RuntimeError, match="dense.weight"):
        _superannotate_model(SUPER_CONFIG, config.to_dict(), weights)


def test_cli_imports_without_optional_ml_packages():
    code = "from interview_integrity.modeling import text_comparison; import sys; assert not {'torch', 'transformers', 'huggingface_hub'} & set(sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_cli_rejects_public_outputs_before_model_loading(tmp_path):
    result = subprocess.run([sys.executable, "-m", "interview_integrity.modeling.text_comparison", "run",
                             "--manifest", "missing.json", "--out-dir", str(tmp_path / "out")],
                            text=True, capture_output=True)
    assert result.returncode == 2 and "Private output" in result.stderr
