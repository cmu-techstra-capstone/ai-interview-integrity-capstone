"""Benchmark mechanics and metrics on synthetic fixtures, not detector quality."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from interview_integrity.modeling.beemo_benchmark import (
    DATASET, FIELDS, LABELS, REVISION, SEED, auroc, bootstrap_auc,
    load_manifest, prepare, report_text, run, select_groups, summarize,
)
from interview_integrity.modeling.text_comparison import MODELS


def toy_rows(n=8):
    return [{"id": i, "prompt_id": f"prompt-{i}", "category": "A" if i % 2 == 0 else "B",
             "model": "test-generator", "prompt": "PRIVATE PROMPT MUST NOT ENTER MODEL",
             "human_output": "human " + "word " * 60,
             "model_output": "machine " + "word " * 60,
             "human_edits": "edited " + "word " * 60} for i in range(n)]


class FakeCandidate:
    def __init__(self, count=100, fail=False):
        self.count, self.fail, self.inputs = count, fail, []

    def token_count(self, text):
        self.inputs.append(("tokens", text))
        return self.count

    def score(self, text):
        self.inputs.append(("score", text))
        if self.fail:
            raise RuntimeError("synthetic inference error")
        value = {"human": .1, "machine": .9, "edited": .4}[text.split()[0]]
        return {"ai_text_score": value, "human_score": 1 - value}


def protocol(tmp_path, rows=None, count=4):
    source = tmp_path / "source.parquet"
    source.write_bytes(b"synthetic fixture only, no public text")
    prepare(toy_rows() if rows is None else rows, source, tmp_path / "protocol", count=count)
    return tmp_path / "protocol/manifest.json", source


def test_selection_is_stable_stratified_and_prompt_unique():
    rows = toy_rows()
    selected = select_groups(rows, count=4)
    assert [r["id"] for r in selected] == [r["id"] for r in select_groups(list(reversed(rows)), count=4)]
    assert len({r["prompt_id"] for r in selected}) == 4
    assert sum(r["category"] == "A" for r in selected) == 2
    assert sum(r["category"] == "B" for r in selected) == 2
    short_rows = copy.deepcopy(rows)
    for row in short_rows:
        row["human_output"] = "short"
    assert [r["id"] for r in selected] == [r["id"] for r in select_groups(short_rows, count=4)]


def test_multiple_generator_rows_do_not_duplicate_a_prompt():
    rows = toy_rows()
    repeat = {**rows[0], "id": 100, "model": "another-generator"}
    selected = select_groups(rows + [repeat], count=8)
    assert len(selected) == 8 and len({r["prompt_id"] for r in selected}) == 8


@pytest.mark.parametrize("mutation", [
    "missing_text", "duplicate_id", "bad_prompt", "inconsistent_prompt", "bad_id",
])
def test_invalid_source_rows_are_not_silently_replaced(mutation):
    rows = toy_rows()
    if mutation == "missing_text":
        rows[0]["human_edits"] = ""
    elif mutation == "duplicate_id":
        rows[1]["id"] = rows[0]["id"]
    elif mutation == "bad_prompt":
        rows[0]["prompt_id"] = None
    elif mutation == "inconsistent_prompt":
        rows[1]["prompt_id"] = rows[0]["prompt_id"]
    else:
        rows[0]["id"] = True
    with pytest.raises(ValueError):
        select_groups(rows, count=4)


@pytest.mark.parametrize("count", [0, True, -1, 100])
def test_invalid_or_unavailable_quotas(count):
    with pytest.raises(ValueError):
        select_groups(toy_rows(), count=count)


def test_freeze_labels_and_inputs_no_prompt_leakage(tmp_path):
    manifest_path, source = protocol(tmp_path)
    d = load_manifest(manifest_path)
    assert d["dataset"] == DATASET and d["revision"] == REVISION and d["seed"] == SEED
    assert d["selected_groups"] == 4 and len(d["samples"]) == 12
    assert d["category_counts"] == {"A": 2, "B": 2}
    assert all(s["label"] == LABELS[s["variant"]] for s in d["samples"])
    assert LABELS["ai_expert_edited"] == 1 and LABELS["human"] == 0
    assert all("PRIVATE PROMPT" not in s["text"] for s in d["samples"])
    assert d["selection_independent_of_scores_and_length"] is True
    with pytest.raises(ValueError, match="already exists"):
        prepare(toy_rows(), source, manifest_path.parent, count=4)


@pytest.mark.parametrize("mutation", ["label", "hash", "missing_variant", "duplicate", "source"])
def test_bad_frozen_inputs_rejected(tmp_path, mutation):
    path, source = protocol(tmp_path)
    d = json.loads(path.read_text())
    if mutation == "label":
        d["samples"][0]["label"] = 1
    elif mutation == "hash":
        d["samples"][0]["text"] += "changed"
    elif mutation == "missing_variant":
        d["samples"].pop()
    elif mutation == "duplicate":
        d["samples"].append(d["samples"][0])
    else:
        source.write_bytes(b"changed")
    path.write_text(json.dumps(d))
    with pytest.raises(ValueError):
        load_manifest(path)


@pytest.mark.parametrize("neg,pos,expected", [
    ([.1, .2], [.8, .9], 1),
    ([.8, .9], [.1, .2], 0),
    ([.5, .5], [.5, .5], .5),
    ([.1, .4], [.2, .3], .5),
    ([.1, .5], [.5, .9], .875),
])
def test_auroc_direction_and_ties(neg, pos, expected):
    assert auroc(neg, pos) == pytest.approx(expected)


@pytest.mark.parametrize("neg,pos", [([], [.5]), ([math.nan], [.5]), ([.2], [True]), ([.2], [math.inf])])
def test_auroc_invalid_scores(neg, pos):
    with pytest.raises(ValueError):
        auroc(neg, pos)


def test_paired_bootstrap_reproducible_and_null_for_one_group():
    n, p = [.1, .2, .3], [.8, .9, .95]
    assert bootstrap_auc(n, p, SEED, draws=30) == [1, 1]
    assert bootstrap_auc(n, p, SEED, draws=30) == bootstrap_auc(n, p, SEED, draws=30)
    assert bootstrap_auc([.1], [.9], SEED) is None
    with pytest.raises(ValueError):
        bootstrap_auc(n, p[:1], SEED)


def test_run_same_text_no_labels_no_training_no_threshold(tmp_path):
    path, _ = protocol(tmp_path)
    candidates = {}
    def factory(name, cache):
        candidates[name] = FakeCandidate()
        return candidates[name]
    events = []
    summary = run(path, tmp_path / "run", tmp_path / "cache", factory=factory, progress=events.append)
    expected = [(action, s["text"]) for s in load_manifest(path)["samples"] for action in ("tokens", "score")]
    assert all(c.inputs == expected for c in candidates.values())
    assert summary["selected_groups"] == 4 and summary["common_complete_groups"] == 4
    assert summary["threshold_selected"] is False and summary["accuracy_estimated"] is False
    assert summary["model_selected"] is None
    for metrics in summary["models"].values():
        assert metrics["contrasts"]["ai_original"]["auroc"] == 1
        assert metrics["contrasts"]["ai_expert_edited"]["auroc"] == 1
        assert metrics["expert_edit_lowered_score_fraction"] == 1
        assert metrics["edited_minus_original_mean_score"] == pytest.approx(-.5)
    result = json.loads((tmp_path / "run/results.json").read_text())
    assert result["integrity_status"] == "verified" and result["run_status"] == "complete"
    assert result["training"] is False and result["asr_used"] is False
    assert result["sends_content_externally"] is False and len(events) == 3
    assert "NOT classification accuracy" in (tmp_path / "run/report.md").read_text()
    with pytest.raises(ValueError, match="already exists"):
        run(path, tmp_path / "run", tmp_path)


def test_all_models_use_common_complete_prompt_groups(tmp_path):
    rows = toy_rows()
    rows[0]["human_edits"] = "too short"
    path, _ = protocol(tmp_path, rows=rows, count=8)
    class LongForOneModel(FakeCandidate):
        def token_count(self, text):
            return 513 if text.startswith("machine") else 100
    def factory(name, cache):
        return LongForOneModel() if name == "mage" else FakeCandidate()
    summary = run(path, tmp_path / "run", tmp_path, factory=factory)
    assert summary["common_complete_groups"] == 0
    assert summary["models"]["hc3"]["coverage"]["ai_expert_edited"]["scored"] == 7
    assert summary["models"]["mage"]["coverage"]["ai_original"]["statuses"] == {"answer_exceeds_common_capacity": 8}
    assert all(not m["contrasts"] for m in summary["models"].values())


def test_model_errors_are_null_and_reported(tmp_path):
    path, _ = protocol(tmp_path)
    def factory(name, cache):
        if name == "mage":
            raise RuntimeError("synthetic missing model")
        return FakeCandidate()
    summary = run(path, tmp_path / "run", tmp_path, factory=factory)
    result = json.loads((tmp_path / "run/results.json").read_text())
    assert result["model_errors"] == {"mage": "synthetic missing model"}
    assert all(r["ai_text_score"] is None for r in result["rows"] if r["model"] == "mage")
    assert summary["common_complete_groups"] == 0
    assert summary["models"]["hc3"]["coverage"]["human"]["scored"] == 4


def test_inference_error_is_not_zero_score(tmp_path):
    path, _ = protocol(tmp_path)
    summary = run(path, tmp_path / "run", tmp_path, factory=lambda n, c: FakeCandidate(fail=True))
    result = json.loads((tmp_path / "run/results.json").read_text())
    assert all(r["status"] == "inference_error" and r["ai_text_score"] is None for r in result["rows"])
    assert summary["common_complete_groups"] == 0


def test_changed_source_invalidates_results(tmp_path):
    path, source = protocol(tmp_path)
    def factory(name, cache):
        source.write_bytes(b"changed during inference")
        return FakeCandidate()
    with pytest.raises(ValueError, match="Inputs changed"):
        run(path, tmp_path / "run", tmp_path, factory=factory)
    result = json.loads((tmp_path / "run/results.json").read_text())
    assert result["integrity_status"] == "failed"
    assert not (tmp_path / "run/summary.json").exists()


def test_summary_refuses_incomplete_runs():
    with pytest.raises(ValueError, match="unverified/incomplete"):
        summarize({"integrity_status": "pending", "run_status": "running"}, {})


def test_optional_imports_are_lazy():
    code = "from interview_integrity.modeling import beemo_benchmark; import sys; assert not {'pyarrow', 'torch', 'transformers', 'huggingface_hub'} & set(sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_cli_rejects_nonprivate_output_before_loading(tmp_path):
    result = subprocess.run([sys.executable, "-m", "interview_integrity.modeling.beemo_benchmark", "prepare",
                             "--out-dir", str(tmp_path / "out")], capture_output=True, text=True)
    assert result.returncode == 2 and "Private output" in result.stderr
