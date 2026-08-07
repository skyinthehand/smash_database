# Quickstart: イベント記録への大会終了日時(end_at)の保存

実装後、以下の手順でこの機能がエンドツーエンドで動作することを確認できる。

## 前提

- `scripts/utils.py` の `EVENT_DATA_VERSION` が `3` に更新済み。
- `write_event_attributes()`(`download.py` / `download_specific_event.py`)が
  `end_at` を受け取り `attr.json` に書き込むよう更新済み。
- `get_event_details_by_tournament_query()` が `tournament.endAt` を含むよう
  更新済み。
- start.gg API トークンが環境変数等で利用可能(`$STARTGG_TOKEN`)。

## 1. 単体テストを実行する

```bash
python -m unittest scripts.test.test_download
python -m unittest scripts.test.test_backfill_schema_version
python -m unittest scripts.test.test_validate_data   # 既存テストが壊れていないことも確認
```

期待結果: 全てパスする。特に以下がカバーされていること([data-model.md](./data-model.md) /
[contracts/attr-json.md](./contracts/attr-json.md) 参照):

- `write_event_attributes()` に `end_at` を渡すと `attr.json` の `end_at` に
  その値がそのまま書き込まれる。
- `end_at` を渡さない/`None` を渡した場合、`attr.json` の `end_at` は `null` になり、
  例外は発生しない。
- `end_at` は `ATTR_REQUIRED_FIELDS` に含まれないため、`end_at` を持たない既存形式の
  `attr.json` でも `validate_data.py` は既存どおり成功する。
- `backfill_schema_version.py::backfill_one_event()` が、start.gg から取得した
  `tournament.endAt` を `end_at` として書き込む。

## 2. 新規取得で `end_at` が入ることを確認する

大会一覧の一括スキャン経路を、既に終了している大会1件に絞って小規模実行し、生成された
`attr.json` を確認する:

```bash
python3 scripts/fetch/download.py --token "$STARTGG_TOKEN" \
  --game_id <game_id> --country_code JP \
  --start_date <既に終了している直近の日付> --finish_date <同日>
cat data/startgg/events/.../attr.json | python3 -m json.tool | grep -A1 '"end_at"'
```

確認ポイント:

- `end_at` が `timestamp`(開始日時)以降のUNIXタイムスタンプになっていること。
- `event_data_version` が `3` になっていること。

## 3. 既存イベントへの段階的反映を確認する(バックフィル経路)

`end_at` を持たない(`event_data_version < 3` の)既存イベントディレクトリを対象に、
小さい `--max_events` でバックフィルを実行する:

```bash
python3 scripts/fetch/backfill_schema_version.py \
  --token "$STARTGG_TOKEN" \
  --max_events 1
```

確認ポイント:

- 処理されたイベントの `attr.json` に `end_at` と `event_data_version: 3` が
  追加されること。
- `002-incremental-schema-backfill` で確認済みの既存挙動(カーソル更新・スキップ
  判定)が本機能によって壊れていないこと。

## 4. ドキュメント整合性の確認

```bash
grep -n "end_at" docs/data_model.md
```

`attr.json` のスキーマ例に `end_at` が含まれていること(Constitution I)。
