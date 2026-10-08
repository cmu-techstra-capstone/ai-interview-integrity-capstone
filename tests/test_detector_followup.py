"""Synthetic mechanics tests; no downloaded model/data required by core tests."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from interview_integrity.modeling.beemo_benchmark import prepare, run as baseline_run
from interview_integrity.modeling.detector_followup import (
    load_baseline, load_cleanup, report_followup, run_followup, summarize_followup,
)


class FakeBase:
    def token_count(self, text):
        return 100

    def score(self, text):
        x = {"human": .1, "machine": .9, "edited": .5}[text.split()[0]]
        return {"ai_text_score": x, "human_score": 1 - x, "raw_logits": [x, 1 - x]}


class FakeFollowup:
    def __init__(self, *, transform=lambda x: x, count=100, fail=False, value=None):
        self.transform, self.count, self.fail, self.value = transform, count, fail, value
        self.inputs = []

    def prepare_text(self, text):
        self.inputs.append(text)
        return self.transform(text)

    def token_count(self, text):
        return self.count

    def score(self, text):
        if self.fail:
            raise RuntimeError("synthetic error")
        x = {"human": -2, "machine": 3, "edited": 1}[text.split()[0]] if self.value is None else self.value
        return {"score": x}


def fixture(tmp_path):
    rows = [{"id": i, "prompt_id": f"p-{i}", "category": "A", "model": "fixture",
             "prompt": "SHOULD NEVER ENTER DETECTOR", "human_output": "human " + "word " * 60,
             "model_output": "machine " + "word " * 60, "human_edits": "edited " + "word " * 60}
            for i in range(4)]
    source = tmp_path / "source.parquet"
    source.write_bytes(b"synthetic bytes only")
    manifest = prepare(rows, source, tmp_path / "protocol", count=4)
    path = tmp_path / "protocol/manifest.json"
    baseline_run(path, tmp_path / "baseline", tmp_path, factory=lambda n, c: FakeBase())
    return path, tmp_path / "baseline/results.json", manifest


def test_reuses_fixed_inputs_negative_statistics_and_same_groups(tmp_path):
    manifest_path, base, _ = fixture(tmp_path)
    candidate = FakeFollowup()
    summary = run_followup(manifest_path, base, tmp_path / "new", {"test": {}}, lambda n: candidate)
    assert summary["matched_groups"] == summary["original_complete_groups"] == 4
    assert summary["arms"]["test"]["ai_expert_edited"]["auroc"] == 1
    assert all("SHOULD NEVER" not in x for x in candidate.inputs)
    result = json.loads((tmp_path / "new/results.json").read_text())
    assert len(result["rows"]) == 12
    assert result["integrity_status"] == "verified"
    assert any(r["score"] < 0 for r in result["rows"])
    assert result["confidence"] is result["verdict"] is None
    assert not result["training"] and not result["sends_content_externally"]
    assert "NOT accuracy" in report_followup(summary)


@pytest.mark.parametrize("kind", ["short", "long"])
def test_exclusions_do_not_improve_cohort_by_replacement(tmp_path, kind):
    manifest_path, base, _ = fixture(tmp_path)
    first = json.loads(manifest_path.read_text())["samples"][0]["text"]
    def transform(x):
        return "tiny" if x == first and kind == "short" else x
    class Excluded(FakeFollowup):
        def token_count(self, text):
            return 513 if text == first and kind == "long" else 100
    summary = run_followup(manifest_path, base, tmp_path / "new", {"test": {}},
                           lambda n: Excluded(transform=transform))
    # All synthetic human texts are identical, so all human variants are excluded.
    assert summary["matched_groups"] == 0
    assert len(summary["dropped_original_prompt_ids"]) == 4
    assert summary["arms"]["test"] == {}
    reason = "insufficient_text_after_preprocessing" if kind == "short" else "answer_exceeds_common_capacity"
    assert summary["coverage"]["test"]["human"] == {reason: 4}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "0.2"])
def test_bad_statistics_fail_run_not_silent_success(tmp_path, value):
    path, base, _ = fixture(tmp_path)
    with pytest.raises(RuntimeError, match="had errors"):
        run_followup(path, base, tmp_path / "new", {"test": {}}, lambda n: FakeFollowup(value=value))
    r = json.loads((tmp_path / "new/results.json").read_text())
    assert all(x["status"] == "inference_error" and x["score"] is None for x in r["rows"])


def test_model_loading_failure_is_not_a_zero_score(tmp_path):
    path, base, _ = fixture(tmp_path)
    def factory(n):
        raise RuntimeError("fixture model unavailable")
    with pytest.raises(RuntimeError, match="had errors"):
        run_followup(path, base, tmp_path / "new", {"test": {}}, factory)
    assert json.loads((tmp_path / "new/summary.json").read_text())["matched_groups"] == 0


@pytest.mark.parametrize("mutation", ["hash", "status", "model", "duplicate", "identity", "missing"])
def test_bad_original_benchmark_rejected(tmp_path, mutation):
    path, base, manifest = fixture(tmp_path)
    r = json.loads(base.read_text())
    if mutation == "hash":
        r["manifest_sha256"] = "wrong"
    elif mutation == "status":
        r["integrity_status"] = "failed"
    elif mutation == "model":
        r["models"]["mage"]["revision"] = "other"
    elif mutation == "duplicate":
        r["rows"].append(copy.deepcopy(r["rows"][0]))
    elif mutation == "identity":
        r["rows"][0]["text_sha256"] = "wrong"
    else:
        r["rows"].pop()
    base.write_text(json.dumps(r))
    with pytest.raises(ValueError):
        load_baseline(base, path, manifest)


def test_changed_inputs_invalidate_run(tmp_path):
    path, base, _ = fixture(tmp_path)
    def factory(n):
        base.write_text(base.read_text() + " ")
        return FakeFollowup()
    with pytest.raises(ValueError, match="Inputs changed"):
        run_followup(path, base, tmp_path / "new", {"test": {}}, factory)
    assert not (tmp_path / "new/summary.json").exists()


def test_existing_outputs_preserved(tmp_path):
    path, base, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match="Output exists"):
        run_followup(path, base, tmp_path / "baseline", {"test": {}}, lambda n: FakeFollowup())


def test_unverified_summary_rejected():
    with pytest.raises(ValueError, match="Refuse"):
        summarize_followup({"integrity_status": "pending"}, {}, {})


@pytest.mark.parametrize("name", ["mage", "superannotate"])
def test_modified_publisher_code_not_executed(tmp_path, name):
    (tmp_path / f"{name}.py").write_text("raise RuntimeError('arbitrary code')")
    with pytest.raises(ValueError, match="checksum"):
        load_cleanup(name, tmp_path)


def test_optional_imports_lazy():
    code = "from interview_integrity.modeling import detector_followup; import sys; assert not {'torch','transformers','cleantext','bs4','markdown','huggingface_hub'} & set(sys.modules)"
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_cli_refuses_public_output_before_model_loading(tmp_path):
    p = subprocess.run([sys.executable, "-m", "interview_integrity.modeling.detector_followup", "fast",
                        "--manifest", "missing", "--baseline", "missing", "--out-dir", str(tmp_path / "out")],
                       capture_output=True, text=True)
    assert p.returncode == 2 and "Private outputs" in p.stderr


def test_analytic_formula_parity_and_guard_in_isolated_process():
    if importlib.util.find_spec("torch") is None:
        pytest.skip("Optional torch not installed")
    code = r'''
import torch
from interview_integrity.modeling.detector_followup import analytic_discrepancy
torch.manual_seed(42)
ref, score = torch.randn(1, 5, 11, dtype=torch.float64), torch.randn(1, 5, 11, dtype=torch.float64)
labels = torch.tensor([[0, 3, 5, 6, 8]])
lprobs = torch.log_softmax(score, -1)
probs = torch.softmax(ref, -1)
mean = (probs * lprobs).sum(-1)
var = (probs * lprobs.square()).sum(-1) - mean.square()
expected = ((lprobs.gather(-1, labels.unsqueeze(-1)).sum() - mean.sum()) / var.sum().sqrt()).item()
assert abs(analytic_discrepancy(ref, score, labels) - expected) < 1e-12
for r, s, y in [(ref[:, :0], score[:, :0], labels[:, :0]), (ref, score[:, :, :10], labels),
                 (ref * float('nan'), score, labels), (ref * 0, score * 0, labels)]:
    try:
        analytic_discrepancy(r, s, y)
    except ValueError:
        pass
    else:
        raise AssertionError('Guard did not reject invalid formula input')
'''
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
