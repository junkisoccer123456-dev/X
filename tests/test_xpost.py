import csv
import json
from datetime import date

import anthropic
import httpx2 as httpx
import pytest

from xpost.cli import main
from xpost.config import load_accounts, load_presets, load_structures, resolve_structures
from xpost.export import COLUMNS, read_past_themes, sheet_title, to_rows, write_csv
from xpost.generator import GenerationError, Generator, Part, Post, parse_response_json, validate_post
from xpost.prompt import build_output_schema, build_system_prompt, build_user_prompt
from xpost.textlen import weighted_length

ACCOUNTS = load_accounts()
STRUCTURES = load_structures()
PRESETS = load_presets()


def sample_output(structure, n=2):
    return {
        "posts": [
            {"theme": f"テーマ{i}", "parts": [{"kind": k, "text": f"{k}の本文{i}"} for k in structure.parts]}
            for i in range(1, n + 1)
        ]
    }


def sse_response(text: str, stop_reason: str = "end_turn") -> httpx.Response:
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5",
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta",
                           "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                           "usage": {"output_tokens": 5}}),
        ("message_stop", {"type": "message_stop"}),
    ]  # fmt: skip
    body = "".join(f"event: {e}\ndata: {json.dumps(d, ensure_ascii=False)}\n\n" for e, d in events)
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())


def mock_client(handler) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))


# --- config -----------------------------------------------------------------


def test_all_structures_have_examples_matching_parts():
    assert {"haru", "tamura"} <= set(ACCOUNTS)
    assert len(STRUCTURES) == 9
    for s in STRUCTURES.values():
        assert [p["kind"] for p in s.example] == s.parts, s.id


def test_presets_resolve():
    assert len(resolve_structures("7構文", STRUCTURES, PRESETS)) == 7
    assert [s.id for s in resolve_structures("ng_ok,abc3", STRUCTURES, PRESETS)] == ["ng_ok", "abc3"]
    assert resolve_structures("NG連打→OK提示型", STRUCTURES, PRESETS)[0].id == "ng_ok"
    with pytest.raises(ValueError):
        resolve_structures("nope", STRUCTURES, PRESETS)


# --- text length ------------------------------------------------------------


def test_weighted_length():
    assert weighted_length("abc") == 3
    assert weighted_length("あいう") == 6
    assert weighted_length("→・①") == 6
    assert weighted_length("見て https://example.com/very/long/path") == 4 + 1 + 23


# --- prompt -----------------------------------------------------------------


def test_prompts_contain_persona_and_structure():
    haru, s = ACCOUNTS["haru"], STRUCTURES["ng_ok"]
    system = build_system_prompt(haru)
    assert "面接官" in system and "ぼくのアカウントをフォロー" in system
    user = build_user_prompt(s, 3, themes=["志望動機"], avoid_themes=["逆質問"], extra="20代向け")
    assert "NG連打→OK提示型" in user and "本文 → リプ1 → リプ2" in user
    assert "- 志望動機" in user and "- 逆質問" in user and "20代向け" in user
    schema = build_output_schema(s)
    assert schema["properties"]["posts"]["items"]["properties"]["parts"]["items"]["properties"]["kind"][
        "enum"
    ] == ["本文", "リプ1", "リプ2"]


# --- generator --------------------------------------------------------------


def test_generate_sends_expected_request_and_parses():
    s = STRUCTURES["ng_ok"]
    captured = {}

    def handler(request: httpx.Request):
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return sse_response(json.dumps(sample_output(s), ensure_ascii=False))

    posts = Generator(client=mock_client(handler)).generate(ACCOUNTS["haru"], s, 2)
    body = captured["body"]
    assert body["model"] == "claude-opus-5"
    assert body["stream"] is True
    assert body["thinking"] == {"type": "adaptive"}
    assert body["fallbacks"] == "default"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "server-side-fallback-2026-07-01" in captured["headers"]["anthropic-beta"]
    assert [p.theme for p in posts] == ["テーマ1", "テーマ2"]
    assert [x.kind for x in posts[0].parts] == ["本文", "リプ1", "リプ2"]
    assert not posts[0].warnings


def test_generate_refusal_raises():
    s = STRUCTURES["arrow_list"]
    client = mock_client(lambda r: sse_response("", stop_reason="refusal"))
    with pytest.raises(GenerationError):
        Generator(client=client).generate(ACCOUNTS["haru"], s, 1)


def test_validate_post_flags_wrong_parts_and_length():
    import dataclasses

    acct = dataclasses.replace(ACCOUNTS["haru"], max_weighted_length=10)
    post = Post(theme="t", structure=STRUCTURES["ng_ok"], parts=[Part("本文", "あ" * 6), Part("リプ1", "")])
    validate_post(post, acct)
    assert len(post.warnings) == 3  # 並び違い / 空 / 文字数超過


def test_parse_bad_json():
    with pytest.raises(GenerationError):
        parse_response_json("not json", STRUCTURES["ng_ok"])


# --- export -----------------------------------------------------------------


def test_rows_csv_and_past_themes(tmp_path):
    s1, s2 = STRUCTURES["ng_ok"], STRUCTURES["arrow_list"]
    posts = parse_response_json(json.dumps(sample_output(s1)), s1) + parse_response_json(
        json.dumps(sample_output(s2)), s2
    )
    posts[0].warnings.append("注意")
    rows = to_rows(posts, "haru", date(2026, 9, 23))
    assert len(rows) == 2 * 3 + 2 * 1
    assert all(len(r) == len(COLUMNS) for r in rows)
    assert rows[0][:8] == [1, "テーマ1", "本文", "本文の本文1", "2026-09-23", "haru", "NG連打→OK提示型", "draft"]
    assert rows[0][-1] == "注意" and rows[1][-1] == ""
    assert rows[6][0] == 1  # 構文が変わると No は1から

    title = sheet_title("haru", date(2026, 9, 23), [s1.name, s2.name], 4)
    assert title == "X投稿_haru_2026-09-23_2構文4本"
    assert sheet_title("haru", date(2026, 9, 23), [s1.name], 2) == "X投稿_haru_2026-09-23_NG連打→OK提示型"

    path = write_csv(rows, tmp_path / f"{title}.csv")
    with path.open(encoding="utf-8-sig") as f:
        assert next(csv.reader(f)) == COLUMNS
    assert read_past_themes(tmp_path, "haru") == ["テーマ1", "テーマ2"]
    assert read_past_themes(tmp_path, "tamura") == []


def test_cli_generate_end_to_end(tmp_path, monkeypatch, capsys):
    def fake_generate(self, account, structure, count, themes, avoid, extra):
        assert themes == ["A", "B"] and count == 2
        return parse_response_json(json.dumps(sample_output(structure)), structure)

    monkeypatch.setattr(Generator, "__init__", lambda self, **kw: None)
    monkeypatch.setattr(Generator, "generate", fake_generate)
    rc = main(["generate", "-a", "tamura", "-s", "5構文", "--themes", "A,B", "-o", str(tmp_path), "--date", "2026-09-22"])
    assert rc == 0
    out = tmp_path / "X投稿_tamura_2026-09-22_5構文10本.csv"
    assert out.exists()
    assert "10本" in capsys.readouterr().out


def test_cli_unknown_account(capsys):
    assert main(["generate", "-a", "nobody", "-s", "ng_ok"]) == 2
