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
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

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
        for part in post["parts"]:
            note = ""
            if limit and (n := weighted_length(part["text"])) > limit:
                note = f"文字数超過 {n}/{limit}"
                warnings.append(f"[{s}] No.{counters[s]} {post['theme']} {part['kind']}: {note}")
            rows.append(
                [counters[s], post["theme"], part["kind"], part["text"].strip(), data["date"],
                 data["account"], s, "draft", "", "", "", "", "", "", note]
            )  # fmt: skip
    return rows, warnings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--limit", type=int, help="1パーツあたりの文字数上限（Xのカウント。無料アカウントは280）")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    data.setdefault("date", date.today().isoformat())
    rows, warnings = to_rows(data, args.limit)
    title = sheet_title(data)
    path = Path(args.out_dir) / f"{title}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    print(title)
    print(path)
    for w in warnings:
        print(f"⚠ {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
