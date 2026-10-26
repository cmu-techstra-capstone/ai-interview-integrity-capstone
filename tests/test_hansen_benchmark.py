import csv
from io import StringIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from interview_integrity.modeling.hansen_benchmark import (
    EXPECTED_DOMAINS, EXPECTED_GENERATORS, load_test_rows, report_text, summarize,
)


def archive_fixture(path: Path, *, omit=None, bad_label=False):
    with ZipFile(path, "w") as zf:
        zf.writestr("HANSEN-TT/TT_ChatGPT_CEO/train.csv", "label,text\n0,train only\n")
        for model in EXPECTED_GENERATORS:
            for domain in EXPECTED_DOMAINS:
                group = f"TT_{model}_{domain}"
                if group == omit:
                    continue
                label = "9" if bad_label else "1"
                zf.writestr(f"HANSEN-TT/{group}/test.csv",
                            f"label,text\n0,human {group} response\n{label},generated {group} response\n")


def test_loader_reads_only_the_fifteen_test_groups(tmp_path):
    path = tmp_path / "hansen.zip"
    archive_fixture(path)
    rows = load_test_rows(path)
    assert len(rows) == 30
    assert {r["label"] for r in rows} == {0, 1}
    assert {r["group"] for r in rows} == {
        f"TT_{model}_{domain}" for model in EXPECTED_GENERATORS for domain in EXPECTED_DOMAINS
    }


def test_loader_rejects_missing_group_and_invalid_label(tmp_path):
    path = tmp_path / "missing.zip"
    archive_fixture(path, omit="TT_ChatGPT_CEO")
    with pytest.raises(ValueError, match="15 HANSEN test groups"):
        load_test_rows(path)
    archive_fixture(path, bad_label=True)
    with pytest.raises(ValueError, match="Invalid test row"):
        load_test_rows(path)


def test_summary_reports_threshold_free_metrics_and_coverage():
    rows = [
        {"group": "TT_ChatGPT_CEO", "generator": "ChatGPT", "domain": "CEO", "label": 0,
         "status": "scored", "ai_text_score": .1},
        {"group": "TT_ChatGPT_CEO", "generator": "ChatGPT", "domain": "CEO", "label": 1,
         "status": "scored", "ai_text_score": .9},
        {"group": "TT_ChatGPT_CEO", "generator": "ChatGPT", "domain": "CEO", "label": 1,
         "status": "over_token_limit"},
    ]
    result = summarize(rows, "desklib", "hash")
    assert result["overall_auroc"] == 1
    assert result["scored_rows"] == 2 and result["coverage"] == pytest.approx(2 / 3)
    assert result["abstentions"] == {"over_token_limit": 1}
    assert result["threshold_selected"] is False
    assert result["classification_accuracy_reported"] is False
    assert "| Spotify | 0 | 0 | n/a |" in report_text(result)
