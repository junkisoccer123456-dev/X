"""投稿案を管理シート形式（CSV / Google スプレッドシート）で出力する.

列構成は運用中の管理シートと同じ:
No, テーマ, 種別, テキスト, date, account, structure, status,
post_url, impressions, likes, bookmarks, reposts, profile_visits, note
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .generator import Post

COLUMNS = [
    "No", "テーマ", "種別", "テキスト", "date", "account", "structure", "status",
    "post_url", "impressions", "likes", "bookmarks", "reposts", "profile_visits", "note",
]  # fmt: skip
METRIC_COLUMNS = COLUMNS[8:]


def to_rows(posts: list[Post], account_id: str, day: date, status: str = "draft") -> list[list]:
    """1パーツ=1行（行分割形式）。No は構文ごとに1から振り直す（既存シートと同じ運用）."""
    rows = []
    counters: dict[str, int] = {}
    for post in posts:
        sid = post.structure.id
        counters[sid] = counters.get(sid, 0) + 1
        note = " / ".join(post.warnings)
        for i, part in enumerate(post.parts):
            rows.append(
                [
                    counters[sid], post.theme, part.kind, part.text, day.isoformat(),
                    account_id, post.structure.name, status,
                    *([""] * (len(METRIC_COLUMNS) - 1)),
                    note if i == 0 else "",
                ]
            )  # fmt: skip
    return rows


def sheet_title(account_id: str, day: date, structure_names: list[str], total: int) -> str:
    if len(structure_names) == 1:
        label = structure_names[0]
    else:
        label = f"{len(structure_names)}構文{total}本"
    return f"X投稿_{account_id}_{day.isoformat()}_{label}"


def write_csv(rows: list[list], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Excel / Google スプレッドシートで文字化けしないよう BOM 付き UTF-8
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    return path


def read_past_themes(output_dir: Path, account_id: str) -> list[str]:
    """過去に出力したCSVから、同じアカウントで使ったテーマ一覧を集める（重複回避用）."""
    themes: list[str] = []
    for path in sorted(output_dir.glob(f"X投稿_{account_id}_*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                theme = (row.get("テーマ") or "").strip()
                if theme and theme not in themes:
                    themes.append(theme)
    return themes


def upload_to_sheets(
    rows: list[list], title: str, credentials_path: str, folder_id: str | None = None
) -> str:
    """サービスアカウントで Google スプレッドシートを新規作成して書き込み、URLを返す."""
    try:
        import gspread
    except ImportError as e:
        raise RuntimeError("Google スプレッドシート出力には `pip install xpost[sheets]` が必要です") from e
    gc = gspread.service_account(filename=credentials_path)
    sh = gc.create(title, folder_id=folder_id)
    sh.sheet1.update([COLUMNS, *rows], "A1")
    return sh.url
