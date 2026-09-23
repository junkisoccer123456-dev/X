"""アカウント・構文・プリセットの定義を config/ 配下の YAML から読み込む."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@dataclass(frozen=True)
class Account:
    id: str
    display_name: str
    persona: str
    audience: str
    voice: dict
    cta: str
    rules: list[str] = field(default_factory=list)
    max_weighted_length: int | None = None


@dataclass(frozen=True)
class Structure:
    id: str
    name: str
    parts: list[str]
    description: str
    rules: list[str] = field(default_factory=list)
    example: list[dict] = field(default_factory=list)


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_accounts(config_dir: Path = DEFAULT_CONFIG_DIR) -> dict[str, Account]:
    accounts = {}
    for path in sorted((config_dir / "accounts").glob("*.yaml")):
        data = _load_yaml(path)
        accounts[data["id"]] = Account(**data)
    return accounts


def load_structures(config_dir: Path = DEFAULT_CONFIG_DIR) -> dict[str, Structure]:
    structures = {}
    for path in sorted((config_dir / "structures").glob("*.yaml")):
        data = _load_yaml(path)
        structures[data["id"]] = Structure(**data)
    return structures


def load_presets(config_dir: Path = DEFAULT_CONFIG_DIR) -> dict[str, list[str]]:
    path = config_dir / "presets.yaml"
    return _load_yaml(path) if path.exists() else {}


def resolve_structures(
    spec: str, structures: dict[str, Structure], presets: dict[str, list[str]]
) -> list[Structure]:
    """'ng_ok' / 'ng_ok,abc3' / プリセット名 / 構文の日本語名 を Structure のリストに解決する."""
    if spec in presets:
        ids = presets[spec]
    else:
        ids = [s.strip() for s in spec.split(",") if s.strip()]
    by_name = {s.name: s for s in structures.values()}
    resolved = []
    for sid in ids:
        if sid in structures:
            resolved.append(structures[sid])
        elif sid in by_name:
            resolved.append(by_name[sid])
        else:
            known = ", ".join(sorted(structures) + sorted(presets))
            raise ValueError(f"未知の構文です: {sid}（指定可能: {known}）")
    return resolved
