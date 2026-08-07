# Phase 1 Data Model: イベント記録への大会終了日時(end_at)の保存

## エンティティ: イベント記録(`attr.json`)

既存エンティティ(`docs/data_model.md` 定義)への1フィールド追加。新規エンティティは
無い。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `end_at`(新規) | `int \| null` | No(既存イベントは移行完了までフィールド自体が存在しない) | 大会(トーナメント)全体の終了日時、UNIXタイムスタンプ(秒)。`timestamp`(開始日時)と同じ形式・タイムゾーン基準(UTCエポック秒)。start.gg 側で終了日時が未確定の場合は `null`。 |

既存フィールドとの関係:
- `timestamp`: 既存の大会開始日時。`end_at` はこれと対になる値であり、`end_at >= timestamp`
  が成立する(start.gg のデータ上、通常は成立するはずだが、取得側でのバリデーションは
  行わない — 外部データをそのまま格納する既存方針を踏襲)。
- `event_data_version`: 本機能により `EVENT_DATA_VERSION` が `2` → `3` に上がる。
  `end_at` を含む属性情報は `event_data_version: 3` 以降に対応する。`3` 未満の既存
  レコードは `end_at` フィールド自体を持たない(欠落ではなく「未移行」として扱う)。

## 状態遷移

新規の状態やライフサイクルは追加しない。既存の「イベント記録は取得時に1度だけ書き込まれ、
以降は再取得(バックフィル含む)によってのみ上書きされる」という既存モデルをそのまま
踏襲する。

## バリデーション規則

- `end_at` は `scripts/fix/validate_data.py` の `ATTR_REQUIRED_FIELDS` に **追加しない**
  (research.md #5 参照)。存在してもしなくても `validate_data.py` は現状どおり成功する。
- `end_at` が存在する場合、型は `int` または `null` のいずれかであることを新規テストで
  検証する(存在チェックのみで、値の妥当性検証 — 例えば `timestamp` との前後関係の
  検証 — は本機能のスコープ外)。

## 影響を受ける生成元

| フィールド生成元 | 変更内容 |
|---|---|
| `download.py::write_event_attributes()` | 引数 `end_at` を追加し `json_data["end_at"]` として格納 |
| `download.py::download_all_tournaments()` | 既存の `end_timestamp` 変数を `write_event_attributes()` 呼び出しへ渡す |
| `download.py::download_by_ids()` | 同上 |
| `download_specific_event.py::write_event_attributes()` | 同様の引数追加・格納 |
| `download_specific_event.py::fetch_event_details_by_slug()` | 統合辞書の `tournament` に `endAt` を追加 |
| `download_specific_event.py::download_specific_event()` | `tournament_info.get("endAt")` を `write_event_attributes()` へ渡す |
| `backfill_schema_version.py::backfill_one_event()` | `tournament.get("endAt")` を `write_event_attributes()` へ渡す |
