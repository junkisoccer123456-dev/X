"""Claude API で投稿案を生成する."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import anthropic

from .config import Account, Structure
from .prompt import build_output_schema, build_system_prompt, build_user_prompt
from .textlen import weighted_length

DEFAULT_MODEL = os.environ.get("XPOST_MODEL", "claude-opus-5")
DEFAULT_EFFORT = os.environ.get("XPOST_EFFORT", "high")


class GenerationError(RuntimeError):
    pass


@dataclass
class Part:
    kind: str
    text: str


@dataclass
class Post:
    theme: str
    structure: Structure
    parts: list[Part]
    warnings: list[str] = field(default_factory=list)


def validate_post(post: Post, account: Account) -> None:
    """構成（種別の並び）と文字数をチェックし、問題を post.warnings に積む."""
    kinds = [p.kind for p in post.parts]
    if kinds != list(post.structure.parts):
        post.warnings.append(
            f"種別の並びが構文定義と異なります: {kinds}（期待: {post.structure.parts}）"
        )
    for part in post.parts:
        if not part.text.strip():
            post.warnings.append(f"{part.kind} が空です")
        if account.max_weighted_length:
            n = weighted_length(part.text)
            if n > account.max_weighted_length:
                post.warnings.append(
                    f"{part.kind} が文字数上限を超えています（{n}/{account.max_weighted_length}）"
                )


def parse_response_json(raw: str, structure: Structure) -> list[Post]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise GenerationError(f"モデル出力をJSONとして読めませんでした: {e}") from e
    posts = []
    for item in data.get("posts", []):
        parts = [Part(kind=p["kind"], text=p["text"].strip()) for p in item.get("parts", [])]
        posts.append(Post(theme=item["theme"].strip(), structure=structure, parts=parts))
    return posts


class Generator:
    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
    ):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort

    def generate(
        self,
        account: Account,
        structure: Structure,
        count: int,
        themes: list[str] | None = None,
        avoid_themes: list[str] | None = None,
        extra: str | None = None,
    ) -> list[Post]:
        system = build_system_prompt(account)
        user = build_user_prompt(structure, count, themes, avoid_themes, extra)
        # 出力が長くなるので streaming で受け、最後にまとめて取得する。
        # fallbacks="default": 安全分類器で拒否された場合にサーバ側で別モデルに自動退避する。
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=64000,
            system=system,
            messages=[{"role": "user", "content": user}],
            thinking={"type": "adaptive"},
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": build_output_schema(structure)},
            },
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            message = stream.get_final_message()

        if message.stop_reason == "refusal":
            raise GenerationError(f"生成が拒否されました（{structure.name}）: {message.stop_details}")
        if message.stop_reason == "max_tokens":
            raise GenerationError(f"出力が上限で途切れました（{structure.name}）。本数を減らしてください")

        raw = "".join(b.text for b in message.content if b.type == "text")
        posts = parse_response_json(raw, structure)
        for post in posts:
            validate_post(post, account)
        return posts
