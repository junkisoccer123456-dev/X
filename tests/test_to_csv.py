import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from to_csv import COLUMNS, sheet_title, to_rows, weighted_length  # noqa: E402


def sample(structures=("NG連打→OK提示型",)):
    posts = []
    for s in structures:
        for i in (1, 2):
            posts.append({"structure": s, "theme": f"{s}テーマ{i}",
                          "parts": [{"kind": "本文", "text": f"本文{i}\n改行あり"}, {"kind": "リプ1", "text": "リプ"}]})
    return {"account": "tamura", "date": "2026-09-23", "posts": posts}


def test_weighted_length():
    assert weighted_length("abc") == 3
    assert weighted_length("あいう") == 6
    assert weighted_length("→・①") == 6
    assert weighted_length("見て https://example.com/long/path") == 2 * 2 + 1 + 23


def test_rows_numbering_and_columns():
    rows, warnings = to_rows(sample(("A型", "B型")))
    assert all(len(r) == len(COLUMNS) for r in rows)
    assert [r[0] for r in rows] == [1, 1, 2, 2, 1, 1, 2, 2]
    assert rows[0][:8] == [1, "A型テーマ1", "本文", "本文1\n改行あり", "2026-09-23", "tamura", "A型", "draft"]
    assert warnings == []


def test_limit_warning():
    rows, warnings = to_rows(sample(), limit=5)
    assert rows[0][-1].startswith("文字数超過")
    assert rows[1][-1] == ""  # 「リプ」は4なので上限5以内
    assert len(warnings) == 2


def test_titles():
    assert sheet_title(sample()) == "X投稿_tamura_2026-09-23_NG連打→OK提示型"
    assert sheet_title(sample(("A型", "B型"))) == "X投稿_tamura_2026-09-23_2構文4本"
    assert sheet_title({**sample(), "title_label": "7構文70本"}) == "X投稿_tamura_2026-09-23_7構文70本"


def test_cli_writes_csv(tmp_path):
    src = tmp_path / "posts.json"
    src.write_text(json.dumps(sample(), ensure_ascii=False), encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts/to_csv.py"), str(src), "--out-dir", str(tmp_path)],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    assert out[0] == "X投稿_tamura_2026-09-23_NG連打→OK提示型"
    with open(out[1], encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == COLUMNS and rows[1][3] == "本文1\n改行あり" and len(rows) == 5
