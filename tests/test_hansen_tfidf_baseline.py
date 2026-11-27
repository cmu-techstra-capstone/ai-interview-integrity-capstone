import csv
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from interview_integrity.modeling import hansen_tfidf_baseline
from interview_integrity.modeling.hansen_tfidf_baseline import evaluate


def _write_csv(rows):
    from io import StringIO

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["label", "text"])
    writer.writerows(rows)
    return buffer.getvalue()


def test_baseline_removes_exact_train_test_overlap_and_returns_aggregate_only(tmp_path: Path):
    archive = tmp_path / "hansen.zip"
    with ZipFile(archive, "w") as zf:
        for generator in ("ChatGPT", "PALM", "Vicuna13B"):
            for domain in ("CEO", "SEC", "Spotify", "TED", "Tennis"):
                group = f"TT_{generator}_{domain}"
                zf.writestr(
                    f"HANSEN-TT/{group}/train.csv",
                    _write_csv([
                        (0, "human unique words response about task " + group),
                        (0, "human extra training words about another topic " + group),
                        (1, "generated polished words response about task " + group),
                        (1, "generated extra training phrase about another topic " + group),
                    ]),
                )
                zf.writestr(
                    f"HANSEN-TT/{group}/test.csv",
                    _write_csv([
                        (0, "human unique words response about task " + group),
                        (0, "human test sample words response about topic " + group),
                        (1, "generated test polished words response about topic " + group),
                    ]),
                )

    result = evaluate(archive)

    assert result["train_test_overlap_removed"] == 15
    assert result["test_unique_by_normalized_text"] == 45
    assert result["test_coverage"] == 1.0
    assert 0 <= result["overall_auroc"] <= 1
    assert set(result["leave_one_generator_out"]) == {"ChatGPT", "PALM", "Vicuna13B"}
    assert result["raw_text_saved"] is False
    assert result["row_level_scores_saved"] is False


def test_cli_writes_aggregate_json_only_under_ignored_output_root(tmp_path: Path, monkeypatch):
    archive = tmp_path / "hansen.zip"
    with ZipFile(archive, "w") as zf:
        for generator in ("ChatGPT", "PALM", "Vicuna13B"):
            for domain in ("CEO", "SEC", "Spotify", "TED", "Tennis"):
                group = f"TT_{generator}_{domain}"
                zf.writestr(f"HANSEN-TT/{group}/train.csv",
                            _write_csv([(0, f"human training {group}"),
                                        (1, f"generated training {group}")]))
                zf.writestr(f"HANSEN-TT/{group}/test.csv",
                            _write_csv([(0, f"human test {group}"),
                                        (1, f"generated test {group}")]))
    monkeypatch.setattr(hansen_tfidf_baseline, "ROOT", tmp_path)
    output = tmp_path / "data/processed/summary.json"
    monkeypatch.setattr(sys, "argv", ["hansen_tfidf_baseline", "--archive", str(archive),
                                      "--out", str(output)])

    hansen_tfidf_baseline.main()

    result = json.loads(output.read_text())
    assert result["raw_text_saved"] is False
    assert result["row_level_scores_saved"] is False
    assert "generated test" not in output.read_text()
