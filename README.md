# 【★】X投稿生成システム

アカウント（発信者）と構文を選ぶと、Claude がX（旧Twitter）の投稿案をまとめて書き、
いま使っている管理シートと同じ形式（`X投稿_{account}_{date}_{構文}`）のCSVで書き出します。
Google スプレッドシートに直接出すこともできます。

```
アカウント定義 (config/accounts/*.yaml)  ─┐
構文定義     (config/structures/*.yaml) ─┼─▶ Claude API ─▶ 検証（構成・文字数） ─▶ CSV / スプレッドシート
過去のCSV（テーマの重複を避ける）        ─┘
```

## セットアップ

```bash
pip install -e .            # スプレッドシートにも出す場合は: pip install -e ".[sheets]"
export ANTHROPIC_API_KEY=sk-ant-...
```

## 使い方

```bash
# アカウント・構文・プリセットの一覧を表示
python -m xpost list

# haru の「NG連打→OK提示型」を10本
python -m xpost generate -a haru -s ng_ok -n 10

# 7構文 × 10本 = 70本をまとめて（1つのCSV「X投稿_haru_YYYY-MM-DD_7構文70本.csv」になる）
python -m xpost generate -a haru -s 7構文 -n 10

# テーマを指定する（指定したテーマの数だけ作る）
python -m xpost generate -a tamura -s list_reply --themes "職務経歴書のNG表現,求人票の読み方"

# 追加の指示を入れる
python -m xpost generate -a haru -s abc3 -n 5 --instructions "今回は20代の第二新卒向けに寄せる"

# Google スプレッドシートにも出す（サービスアカウントを使う）
python -m xpost generate -a haru -s honne_series -n 10 --sheets \
  --credentials service_account.json --folder-id <DriveフォルダID>
```

`-s` に指定できるもの: 構文ID（`ng_ok`）、構文名（`NG連打→OK提示型`）、カンマ区切り（`ng_ok,abc3`）、プリセット名（`7構文`）。

主なオプション:

| オプション | 内容 |
|---|---|
| `-n / --count` | 1構文あたりの本数（初期値 10） |
| `--themes` | テーマをカンマ区切りで指定 |
| `--instructions` | 今回だけ追加する指示 |
| `--date` | `date` 列に入れる日付（初期値は今日） |
| `-o / --output-dir` | CSVの出力先（初期値 `output/`） |
| `--allow-repeat` | 過去のCSVにあるテーマとかぶってもよい場合に付ける |
| `--model` / `--effort` | 使うモデル（初期値 `claude-opus-5`）と思考の深さ。環境変数 `XPOST_MODEL` / `XPOST_EFFORT` でも指定できる |

## 出力の形式

1パーツを1行にした「行分割版」です。列は運用中のシートと同じにしています。

| No | テーマ | 種別 | テキスト | date | account | structure | status | post_url | impressions | likes | bookmarks | reposts | profile_visits | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

- `No` は構文ごとに1から振り直します。1本の投稿（本文とリプ）は同じ `No` になります。
- `status` の初期値は `draft` です。`post_url` から `profile_visits` は、投稿したあとに手で記入します。
- 構成の抜けや文字数オーバーなど、自動チェックで見つかった問題は `note` 列に書き込みます。
- `output/` に出力済みのCSVを読み込み、同じアカウントで使ったテーマは避けるように指示します。

## 構文

| ID | 構文名 | 構成 |
|---|---|---|
| `list_reply` | リスト提示→リプ回収型 | 本文 → リプ1 → リプ2 |
| `ng_ok` | NG連打→OK提示型 | 本文 → リプ1 → リプ2 |
| `honne_series` | 本音提起→リプ連載解説型 | 本文 → リプ1〜4 |
| `arrow_list` | 網羅リスト（↓連結）型 | 本文 |
| `hidden_reveal` | 正体伏せ→リプ公開型 | 本文 → リプ |
| `symptom_prescription` | 症状連打→一言処方型 | 本文 |
| `three_tier` | 3段階格付け→本命公開型 | 本文 → リプ1 → リプ2 |
| `abc3` | ABC3パターン | パターンA / B / C |
| `bara_tsunagari` | バラバラ→つながり提示型 | 本文 |

プリセットは `7構文`、`5構文`、`all` の3つです（`config/presets.yaml`）。

## カスタマイズ

- **アカウントを追加する**: `config/accounts/haru.yaml` をコピーして、`persona`（経歴）、`audience`（読者）、`voice`（一人称・語尾）、`cta`、`rules` を書き換えます。
  無料アカウントで投稿する場合は `max_weighted_length: 280` にすると、Xの文字数（全角は2として数える）で上限を超えたものを `note` 列で知らせます。
- **構文を追加する**: `config/structures/` に YAML を1つ追加します。`parts`（種別の並び）、`rules`、`example`（お手本の1セット）を書きます。
- **プリセットを追加する**: `config/presets.yaml` に `名前: [構文ID, ...]` の形で追加します。

## 開発

```bash
pip install -e ".[dev]"
python -m pytest
```
