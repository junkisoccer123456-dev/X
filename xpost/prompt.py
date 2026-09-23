"""生成用プロンプトと出力スキーマの組み立て."""

from __future__ import annotations

from .config import Account, Structure

GLOBAL_RULES = [
    "X（旧Twitter）で読まれることを前提に、スマホで読みやすい改行・空行を入れる。",
    "1行目で読み手が自分ごとだと感じるフックを置く。",
    "事実として確認できない数値・社名・実績は創作しない。必要なら【　】の空欄にする。",
    "同じバッチ内でテーマや言い回しを重複させない。",
    "絵文字・ハッシュタグは使わない。",
]


def build_system_prompt(account: Account) -> str:
    voice = account.voice or {}
    lines = [
        "あなたはX（旧Twitter）の転職系アカウントの投稿を書くプロのライターです。",
        "以下の発信者になりきって、その人が実際に投稿する文章を書いてください。",
        "",
        "# 発信者",
        account.persona.strip(),
        "",
        "# 読者",
        account.audience.strip(),
        "",
        "# 文体",
        f"- 一人称: {voice.get('first_person', '僕')}",
        f"- トーン: {voice.get('tone', '')}",
    ]
    if voice.get("endings"):
        lines.append(f"- よく使う語尾: {' / '.join(voice['endings'])}")
    if voice.get("spice_words"):
        lines.append(f"- たまに使う口語（多用しない）: {' / '.join(voice['spice_words'])}")
    lines += ["", "# フォロー導線（CTA）の基本文", account.cta.strip(), "", "# 守るルール"]
    lines += [f"- {r}" for r in [*GLOBAL_RULES, *account.rules]]
    if account.max_weighted_length:
        lines.append(
            f"- 各投稿（本文・各リプ）はXの文字数カウントで{account.max_weighted_length}以内"
            f"（全角{account.max_weighted_length // 2}字程度）に収める。"
        )
    return "\n".join(lines)


def build_user_prompt(
    structure: Structure,
    count: int,
    themes: list[str] | None = None,
    avoid_themes: list[str] | None = None,
    extra: str | None = None,
) -> str:
    lines = [
        f"「{structure.name}」の構文で、投稿セットを{count}本作ってください。",
        "",
        "# 構文の説明",
        structure.description.strip(),
        "",
        f"# 1セットの構成（種別）: {' → '.join(structure.parts)}",
        "各セットの parts は、この種別をこの順番で1つずつ含めてください。",
        "",
        "# 構文のルール",
        *[f"- {r}" for r in structure.rules],
    ]
    if structure.example:
        lines += ["", "# お手本（形式と温度感の参考。内容はコピーしない）"]
        for part in structure.example:
            lines += [f"## {part['kind']}", part["text"].rstrip()]
    if themes:
        lines += ["", "# テーマ（この順で1本ずつ書く）", *[f"- {t}" for t in themes]]
    else:
        lines += ["", "# テーマ", "読者の悩みに刺さるテーマを自分で選んでください。"]
    if avoid_themes:
        lines += ["", "# 過去に使ったテーマ（重複させない）", *[f"- {t}" for t in avoid_themes]]
    if extra:
        lines += ["", "# 追加の指示", extra.strip()]
    return "\n".join(lines)


def build_output_schema(structure: Structure) -> dict:
    return {
        "type": "object",
        "properties": {
            "posts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "theme": {"type": "string", "description": "短いテーマ名"},
                        "parts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "kind": {"type": "string", "enum": list(structure.parts)},
                                    "text": {"type": "string"},
                                },
                                "required": ["kind", "text"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["theme", "parts"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["posts"],
        "additionalProperties": False,
    }
