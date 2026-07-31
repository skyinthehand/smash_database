# Quickstart: 既存イベントへのスキーマ追加フィールドの段階的バックフィル

実装後、以下の手順でこの機能がエンドツーエンドで動作することを確認できる。

## 前提

- `scripts/utils.py` に `EVENT_DATA_VERSION` が定義済み。
- `scripts/fetch/backfill_schema_version.py` が実装済み。
- start.gg API トークンが環境変数等で利用可能(`$STARTGG_TOKEN`)。

## 1. 単体テストを実行する

```bash
python -m unittest scripts.test.test_backfill_schema_version
python -m unittest scripts.test.test_validate_data   # 既存テストが壊れていないことも確認
```

期待結果: 全てパスする。特に以下がカバーされていること([data-model.md](./data-model.md) 参照):

- `event_data_version` が無い/低いイベントが対象として検出される。
- 目標バージョンに達したイベントはスキップされ、API 呼び出しが発生しない
  (モックした fetch 関数の呼び出し回数で検証)。
- カーソルが正しく更新され、次回実行が続きから再開される。
- 一周した場合にカーソルが先頭へ戻る。
- 対象0件のとき、API 呼び出しをせず正常終了する(終了コード0)。

## 2. ローカルでドライ的に少数だけ動かす

一時ディレクトリにテスト用イベントを1〜2件用意し、小さい `--max_events` で
実行して挙動を確認する:

```bash
python3 scripts/fetch/backfill_schema_version.py \
  --token "$STARTGG_TOKEN" \
  --events_root /tmp/sample_events \
  --cursor_path /tmp/sample_cursor.txt \
  --max_events 1
```

確認ポイント:

- 対象イベントの `attr.json` に `event_data_version` が現在の `EVENT_DATA_VERSION`
  値で書き込まれること。
- `/tmp/sample_cursor.txt` が更新されること。
- 同じコマンドをもう一度実行すると、前回処理した1件はスキップされ、
  次のイベントが処理されること(または対象がなければ0件で正常終了)。

## 3. ワークフローを手動実行して確認する

```bash
gh workflow run schema_backfill.yml
gh run watch
```

確認ポイント:

- `chore-update` ブランチにコミットが積まれる(`main` に直接pushされない)。
- 既存の `update_tournament.yml` 等が同時に走っていた場合、
  `chore-update-branch` concurrency グループにより衝突しないこと。
- `chore-update` → `main` のPRが(無ければ)作成される、または既存PRに
  変更が積み重なること。

## 4. 収束の確認(長期観測)

`data/startgg/schema_backfill_cursor.txt` の内容と、
`find data/startgg/events -name attr.json | xargs grep -L event_data_version | wc -l`
のようなカウントを日次で観測し、未処理件数が時間とともに減少し、
最終的に0に収束することを確認する。
