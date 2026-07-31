# Phase 1 Data Model: 既存イベントへのスキーマ追加フィールドの段階的バックフィル

## エンティティ

### EVENT_DATA_VERSION(コード内定数)

- **場所**: `scripts/utils.py`(既存の `JSON_VERSION` の隣)
- **型**: `int`
- **意味**: 「イベントごとに取得されるべきデータの内容」の現在の目標バージョン。
  取得対象フィールドを追加・変更するたびに 1 増やす。
- **初期値**: `1`(本機能導入時点の基準値。`phase_order` 追加・`guest_entrant_count`
  追加が完了した時点でこの値を導入するため、導入時に `2` からスタートしてもよいが、
  「1から始めて、対応する取得ロジックの実装と同時にバージョンを上げる」運用とする)。
- **変更ルール**: このファイル内の値を書き換えるコミットは、必ず対応する
  取得・保存ロジックの変更(例: `write_matches()` への新フィールド追加)と
  同一 PR に含める。`docs/data_model.md` の更新も同一 PR に含める
  (Constitution I)。

### `attr.json.event_data_version`(永続化データ)

- **型**: `int`(省略可 — 本機能導入前に取得された既存イベントには存在しない)
- **書き込みタイミング**: `write_event_attributes()` が呼ばれるたび、その時点の
  `EVENT_DATA_VERSION` の値を書き込む。呼び出し元: `download.py`,
  `download_specific_event.py`, `scripts/fix/redownload_event.py`,
  `scripts/fix/backfill_events.py`, 本機能の `backfill_schema_version.py`。
- **読み取り時のフォールバック**: フィールドが存在しない場合は `0` として扱う
  (「最も古い」= 常にバックフィル対象)。
- **`validate_data.py` との関係**: `ATTR_REQUIRED_FIELDS` には追加しない
  (必須フィールドにすると、本機能でまだ処理されていない既存イベント全件が
  即座にバリデーションエラーになってしまうため)。

### Backfill Cursor(`data/startgg/schema_backfill_cursor.txt`)

- **形式**: プレーンテキスト1行。直近のスキャンで最後に確認した
  イベントディレクトリの相対パス(例: `data/startgg/events/Japan/2024/01/01/Foo/Bar`)。
- **存在しない場合**: スキャン開始位置は「ソート順で最初のディレクトリ」。
- **更新タイミング**: 1回の実行の終了時に、最後に確認した(処理有無を問わない)
  ディレクトリのパスへ上書きする。
- **一周した場合**: ソート順で最後のディレクトリまで確認したら、次回は
  最初のディレクトリから再開する(循環)。

## 処理フロー(状態遷移)

```text
[開始]
  → カーソル位置を読み込む(無ければ先頭)
  → イベントディレクトリを安定ソート順(パス文字列昇順)で列挙
  → カーソル位置から順に走査:
      各ディレクトリについて:
        attr.json の event_data_version を読む(無ければ 0)
        if version >= EVENT_DATA_VERSION:
          スキップ(API呼び出しなし)
        else:
          再取得を実行(download_standings / download_seeds / download_all_set)
          write_event_attributes() で event_data_version を更新
          処理件数 += 1
      if 処理件数 >= --max_events:
        break
      if 一周した(先頭に戻ってきた):
        break
  → 最後に確認したディレクトリのパスをカーソルファイルへ保存
  → 変更があれば chore-update ブランチへコミット・push(既存ワークフローと同様)
  → 処理件数が 0 件だった場合はその旨を出力して正常終了(FR-010)
[終了]
```

## `docs/data_model.md` への追記内容(実装タスク)

`attr.json` のサンプルに `event_data_version` を追記する:

```json
{
  "version": "1.0",
  "event_id": 999,
  "...": "...",
  "event_data_version": 1,
  "status": "completed"
}
```

および「注意点」セクションに以下を追記する:

> `event_data_version` は取得ロジックのスキーマ世代を表す整数値であり、
> ファイル形式全体を表す `version` とは別物。存在しない場合は `0` 相当として扱う。
