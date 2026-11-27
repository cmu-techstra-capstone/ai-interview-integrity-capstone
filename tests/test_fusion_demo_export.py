import importlib.util
import json
from pathlib import Path

from interview_integrity.fusion.demo_export import answer_fragment, recording_payload, result_from_dict
from interview_integrity.fusion.followup import evaluate_interview
from interview_integrity.llm import LLMClient, LLMResponse

from .test_fusion_followup import GAZE_EVENT, interview, track
from .test_fusion_llm_brief import GOOD


def results():
    return evaluate_interview("P1", interview(), track([GAZE_EVENT]))


def test_round_trip_through_dict():
    for r in results():
        back = result_from_dict(json.loads(json.dumps(r.to_dict(include_text=True))))
        assert back == r


def test_fragment_matches_analysis_v1_signal_shape_and_hides_text():
    r = results()[0]
    frag = answer_fragment(r)
    keys = {"signal_name", "modality", "value", "confidence", "quality_status", "supporting_timestamps",
            "supporting_transcript_span", "explanation", "source_features", "sample_key"}
    assert all(set(s) == keys for s in frag["evidence_signals"])
    fp = frag["followup_pattern"]
    assert fp["status"] == "suggest_followup" and fp["ai_assistance_probability"] is None
    assert fp["reviewer_brief_status"] == "not_requested" and "question_text" not in frag
    assert answer_fragment(r, include_text=True)["question_text"] == r.question_text


def test_rejected_brief_is_never_exposed():
    r = results()[0]
    ok = answer_fragment(r, {"brief": GOOD, "violations": [], "accepted": True})
    assert ok["followup_pattern"]["reviewer_brief"] == GOOD
    bad = answer_fragment(r, {"brief": {"summary": "cheating"}, "violations": ["banned wording"], "accepted": False})
    assert bad["followup_pattern"]["reviewer_brief"] is None
    assert bad["followup_pattern"]["reviewer_brief_status"] == "rejected"


def test_recording_payload_counts():
    frags = [answer_fragment(r) for r in results()]
    p = recording_payload("P1", frags)
    assert sum(p["status_counts"].values()) == len(frags) and p["status_counts"]["suggest_followup"] == 1


class FakeLLM(LLMClient):
    provider = "fake"

    def generate(self, prompt, *, model, system=None, temperature=0.7, max_tokens=None, **kw):
        return LLMResponse(json.dumps(GOOD), model, "fake")


def test_brief_script_end_to_end(tmp_path):
    path = Path(__file__).resolve().parents[1] / "experiments/fusion/brief_mit.py"
    spec = importlib.util.spec_from_file_location("brief_mit", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / "results").mkdir()
    with open(tmp_path / "results/P1.jsonl", "w") as f:
        for r in results():
            f.write(json.dumps(r.to_dict(include_text=True)) + "\n")
    (tmp_path / "results/P2.jsonl").write_text(json.dumps(results()[1].to_dict()) + "\n")  # nothing flagged
    mod.main(["--fusion-dir", str(tmp_path)], make_client=FakeLLM)
    briefs = [json.loads(x) for x in (tmp_path / "briefs.jsonl").read_text().splitlines()]
    assert len(briefs) == 1 and briefs[0]["accepted"]
    demo = json.loads((tmp_path / "demo/P1.json").read_text())
    assert len(demo["answers"]) == 4 and not (tmp_path / "demo/P2.json").exists()
    assert "question_text" not in demo["answers"][0]
