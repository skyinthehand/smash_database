# Data Model: トーナメント単位でのイベント作り直し検知と空イベントの整理

本機能は新しいデータフィールド・`attr.json`スキーマ変更を追加しない。既存の2つの
エンティティに対する「発見」「削除」ロジックを新規スクリプトとして追加する。

## エンティティ

### `tournaments.jsonl` のトーナメント記録

既存フィールド(`tournament_id`, `name`, `events[]`)は変更しない。

- **振る舞いの変更(User Story 1)**: 記録済みの `events[]` に含まれない event_id が
  start.gg側の現在のイベント一覧に見つかった場合、新しいイベントとして `events[]` に
  追加される(記録イベント数が0件のトーナメントも対象、Clarifications参照)。
- **振る舞いの変更(User Story 2)**: 対応するイベントディレクトリが削除された場合、
  `events[]` から該当エントリが取り除かれる。

### イベントディレクトリ

既存ファイル構成(`attr.json` / `standings.json` / `seeds.json` / `matches.json`)は
変更しない。

- **振る舞いの変更(User Story 2)**: `standings.json` と `matches.json` の両方が
  空(`data` 配列が0件)のディレクトリは削除される。

## 状態遷移: トーナメントのイベント集合

```
[event_id: {A} を記録済み]
   │
   │ start.gg側でイベントAが削除され、イベントBが新規作成される
   ▼
[start.gg側のライブ一覧: {B}] ≠ [記録済み: {A}]
   │
   │ User Story 1 の定期チェックが実行される
   ▼
[記録済み: {A, B}](Bを新規取得・保存。Aとの対応関係は判定しない)
   │
   │ User Story 2 の定期チェックが実行される
   │ (Aのディレクトリのstandings.json/matches.jsonが両方空と判定)
   ▼
[記録済み: {B}](Aのディレクトリ・記録を削除)
```

2つのユーザーストーリーは独立して(どちらが先でも、同じサイクル内でなくても)動作し、
最終的にこの状態(空でない最新のイベントのみが残る)に収束する。

## 発見・削除ロジックの入出力

### `backfill_tournament_events.py`(User Story 1)

| 項目 | 内容 |
|---|---|
| 走査対象 | `tournaments.jsonl` に記録済みの全トーナメント(記録イベント数0件を含む) |
| 走査順序 | カーソルファイルによる循環スキャン(`002-incremental-schema-backfill` と同様) |
| 1トーナメントあたりの判定 | `fetch_event_ids_from_tournament()` の結果 と 記録済み `event_id` 集合の差分(新規のみ) |
| 出力 | 新しい event_id ごとに新規イベントディレクトリを作成し、`tournaments.jsonl` を更新 |

### `prune_empty_events.py`(User Story 2)

| 項目 | 内容 |
|---|---|
| 走査対象 | `events_root` 以下の全イベントディレクトリ(`standings.json` または `matches.json` を持つもの) |
| 走査順序 | カーソルなし、毎回全件 |
| 削除判定 | `standings.json` の `data` 件数 == 0 かつ `matches.json` の `data` 件数 == 0 |
| 出力 | 削除したディレクトリの一覧を報告し、`tournaments.jsonl` から対応するエントリを取り除いて書き戻す |
