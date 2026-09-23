"""xpost コマンドラインインターフェース.

例:
  xpost list
  xpost generate --account haru --structure ng_ok --count 10
  xpost generate --account haru --structure 7構文 --count 10
  xpost generate --account tamura --structure list_reply --themes "職務経歴書,逆質問"
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from .config import DEFAULT_CONFIG_DIR, load_accounts, load_presets, load_structures, resolve_structures
from .export import read_past_themes, sheet_title, to_rows, upload_to_sheets, write_csv
from .generator import DEFAULT_EFFORT, DEFAULT_MODEL, GenerationError, Generator


def cmd_list(args: argparse.Namespace) -> int:
    config_dir = Path(args.config_dir)
    print("■ アカウント")
    for a in load_accounts(config_dir).values():
        print(f"  {a.id:10} {a.persona.strip().splitlines()[0]}")
    print("\n■ 構文")
    for s in load_structures(config_dir).values():
        print(f"  {s.id:22} {s.name}（{' → '.join(s.parts)}）")
    print("\n■ プリセット")
    for name, ids in load_presets(config_dir).items():
        print(f"  {name:10} {', '.join(ids)}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    config_dir = Path(args.config_dir)
    accounts = load_accounts(config_dir)
    if args.account not in accounts:
        print(f"未知のアカウントです: {args.account}（指定可能: {', '.join(accounts)}）", file=sys.stderr)
        return 2
    account = accounts[args.account]
    try:
        structures = resolve_structures(args.structure, load_structures(config_dir), load_presets(config_dir))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2

    themes = [t.strip() for t in args.themes.split(",") if t.strip()] if args.themes else None
    count = len(themes) if themes else args.count
    output_dir = Path(args.output_dir)
    avoid = [] if args.allow_repeat else read_past_themes(output_dir, account.id)
    day = date.fromisoformat(args.date) if args.date else date.today()

    generator = Generator(model=args.model, effort=args.effort)

    def run(structure):
        print(f"生成中: {structure.name} × {count}本 ...", file=sys.stderr)
        return generator.generate(account, structure, count, themes, avoid, args.instructions)

    # 構文ごとの生成は独立しているので並列に投げる（結果の並びは指定順を保つ）
    try:
        with ThreadPoolExecutor(max_workers=min(4, len(structures))) as pool:
            results = list(pool.map(run, structures))
    except GenerationError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    posts = [p for batch in results for p in batch]
    rows = to_rows(posts, account.id, day)
    title = sheet_title(account.id, day, [s.name for s in structures], len(posts))
    path = write_csv(rows, output_dir / f"{title}.csv")
    print(f"CSVを書き出しました: {path}（{len(posts)}本 / {len(rows)}行）")

    warned = [p for p in posts if p.warnings]
    for p in warned:
        print(f"  ⚠ [{p.structure.name}] {p.theme}: {' / '.join(p.warnings)}", file=sys.stderr)

    if args.sheets:
        creds = args.credentials or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds:
            print("--sheets には --credentials か GOOGLE_APPLICATION_CREDENTIALS が必要です", file=sys.stderr)
            return 2
        url = upload_to_sheets(rows, title, creds, args.folder_id or os.environ.get("XPOST_DRIVE_FOLDER_ID"))
        print(f"スプレッドシートを作成しました: {url}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xpost", description="X投稿生成システム")
    parser.add_argument("--config-dir", default=str(DEFAULT_CONFIG_DIR), help="設定ディレクトリ")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="アカウント・構文・プリセットの一覧")
    p_list.set_defaults(func=cmd_list)

    p_gen = sub.add_parser("generate", help="投稿案を生成してCSV（任意でスプレッドシート）に出力")
    p_gen.add_argument("--account", "-a", required=True, help="アカウントID（例: haru）")
    p_gen.add_argument(
        "--structure", "-s", required=True,
        help="構文ID / 構文名 / カンマ区切り / プリセット名（例: ng_ok, 7構文）",
    )  # fmt: skip
    p_gen.add_argument("--count", "-n", type=int, default=10, help="構文ごとの本数（既定: 10）")
    p_gen.add_argument("--themes", help="テーマをカンマ区切りで指定（指定時は本数=テーマ数）")
    p_gen.add_argument("--instructions", help="追加の指示（例: 今回は20代向けに寄せる）")
    p_gen.add_argument("--date", help="date列に入れる日付 YYYY-MM-DD（既定: 今日）")
    p_gen.add_argument("--output-dir", "-o", default="output", help="CSVの出力先（既定: output）")
    p_gen.add_argument("--allow-repeat", action="store_true", help="過去CSVのテーマとの重複回避をしない")
    p_gen.add_argument("--model", default=DEFAULT_MODEL, help=f"Claudeのモデル（既定: {DEFAULT_MODEL}）")
    p_gen.add_argument("--effort", default=DEFAULT_EFFORT, choices=["low", "medium", "high", "xhigh", "max"])
    p_gen.add_argument("--sheets", action="store_true", help="Google スプレッドシートにも出力する")
    p_gen.add_argument("--credentials", help="Google サービスアカウントのJSONキー")
    p_gen.add_argument("--folder-id", help="スプレッドシートを作るDriveフォルダID")
    p_gen.set_defaults(func=cmd_generate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
