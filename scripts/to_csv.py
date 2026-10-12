#!/usr/bin/env python3
"""生成した投稿（JSON）を管理シート形式のCSVに変換する。/x-post スキルから使う。

使い方:
  python3 scripts/to_csv.py posts.json [--out-dir output] [--limit 280]

入力JSON:
  {
    "account": "tamura",
    "date": "2026-09-23",            # 省略時は今日
    "title_label": "7構文70本",       # 省略時は構文名（複数なら「N構文M本」）
    "posts": [
      {"structure": "NG連打→OK提示型", "theme": "志望動機",
       "parts": [{"kind": "本文", "text": "..."}, {"kind": "リプ1", "text": "..."}]}
    ]
  }

出力: <out-dir>/X投稿_{account}_{date}_{label}.csv（BOM付きUTF-8）
標準出力の1行目にシート名、2行目にCSVのパスを出す。--limit を付けると、
Xの文字数（全角=2）で上限を超えたパーツを note 列と標準エラーに出す。

出力したテーマは --history（既定: history/themes.tsv）に追記する。同じ構文で
過去に出したテーマと重なるものがあれば、標準エラーに警告を出す。
テーマの確認だけしたいときは --check-only（CSVも履歴も書かない）。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

DEFAULT_HISTORY = Path(__file__).resolve().parent.parent / "history" / "themes.tsv"
HISTORY_COLUMNS = ["date", "account", "structure", "theme"]

COLUMNS = [
    "No", "テーマ", "種別", "テキスト", "date", "account", "structure", "status",
    "post_url", "impressions", "likes", "bookmarks", "reposts", "profile_visits", "note",
]  # fmt: skip

URL_RE = re.compile(r"https?://\S+")
# twitter-text v3 で重み1になる範囲。それ以外（日本語など）は2
_LIGHT_RANGES = ((0x0000, 0x10FF), (0x2000, 0x200D), (0x2010, 0x201F), (0x2032, 0x2037))


def weighted_length(text: str) -> int:
    def w(ch: str) -> int:
        cp = ord(ch)
        return 1 if any(lo <= cp <= hi for lo, hi in _LIGHT_RANGES) else 2

    total, pos = 0, 0
    for m in URL_RE.finditer(text):
        total += sum(w(c) for c in text[pos : m.start()]) + 23
        pos = m.end()
    return total + sum(w(c) for c in text[pos:])


def sheet_title(data: dict) -> str:
    label = data.get("title_label")
    if not label:
        names = list(dict.fromkeys(p["structure"] for p in data["posts"]))
        label = names[0] if len(names) == 1 else f"{len(names)}構文{len(data['posts'])}本"
    return f"X投稿_{data['account']}_{data['date']}_{label}"


def to_rows(data: dict, limit: int | None = None) -> tuple[list[list], list[str]]:
    rows, warnings, counters = [], [], {}
    for post in data["posts"]:
        s = post["structure"]
        counters[s] = counters.get(s, 0) + 1  # No は構文ごとに1から
        for i, part in enumerate(post["parts"]):
            note = post.get("note", "") if i == 0 else ""  # 投稿ごとのメモ（年収の出典など）は先頭行に
            if limit and (n := weighted_length(part["text"])) > limit:
                note = f"文字数超過 {n}/{limit}"
                warnings.append(f"[{s}] No.{counters[s]} {post['theme']} {part['kind']}: {note}")
            rows.append(
                [counters[s], post["theme"], part["kind"], part["text"].strip(), data["date"],
                 data["account"], s, "draft", "", "", "", "", "", "", note]
            )  # fmt: skip
    return rows, warnings


def read_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def duplicate_themes(data: dict, history: list[dict]) -> list[str]:
    """同じ構文で過去に出したテーマ（アカウントを問わない）と重なるものを返す。"""
    past = {}
    for h in history:
        past.setdefault((h["structure"], h["theme"]), h)
    dups = []
    for p in data["posts"]:
        h = past.get((p["structure"], p["theme"]))
        if h:
            dups.append(f"[{p['structure']}] {p['theme']}（{h['date']} {h['account']} で出力済み）")
    return dups


def append_history(path: Path, data: dict) -> None:
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        if new:
            writer.writerow(HISTORY_COLUMNS)
        for p in data["posts"]:
            writer.writerow([data["date"], data["account"], p["structure"], p["theme"]])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--limit", type=int, help="1パーツあたりの文字数上限（Xのカウント。無料アカウントは280）")
    ap.add_argument("--history", type=Path, default=DEFAULT_HISTORY, help="出力済みテーマの履歴（TSV）")
    ap.add_argument("--check-only", action="store_true", help="テーマの重複だけ確認する（CSVも履歴も書かない）")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    data.setdefault("date", date.today().isoformat())
    dups = duplicate_themes(data, read_history(args.history))
    for d in dups:
        print(f"⚠ 過去と同じテーマ: {d}", file=sys.stderr)
    if args.check_only:
        return 1 if dups else 0
    rows, warnings = to_rows(data, args.limit)
    title = sheet_title(data)
    path = Path(args.out_dir) / f"{title}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    append_history(args.history, data)
    print(title)
    print(path)
    for w in warnings:
        print(f"⚠ {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
