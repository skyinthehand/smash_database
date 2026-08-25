# データモデル: setごとの逐次取得によるマッチ取得とリカバリ

本機能は既存ファイルのスキーマ（`matches.json`）1つと、共有バージョン定数
（`EVENT_DATA_VERSION`）1つを変更する。新規ファイルは導入しない。永続化される
全ファイルのスキーマドキュメントは`docs/data_model.md`にある（実装の一環として
更新する。憲法Principle I）。本ドキュメントは、設計目的でエンティティとその
ライフサイクルを記述する。

## エンティティ: Match Record（マッチレコード）

`matches.json`の`data`配列内の1エントリ。イベントに属する1つのstart.gg setを
表す。常にどちらか一方の状態を取る。

### 状態: `placeholder`（プレースホルダー）

| フィールド | 型 | 備考 |
|---|---|---|
| `set_id` | integer | start.ggのset ID。唯一存在するフィールド。 |

プレースホルダーレコードには他のキーは一切存在しない（キー存在の有無で状態を
区別する理由についてはresearch.md §4を参照）。

### 状態: `complete`（完了済み）

| フィールド | 型 | 備考 |
|---|---|---|
| `set_id` | integer | **本機能で新規追加。** start.ggのset ID。置き換え元のプレースホルダーから値は変わらない。 |
| `winner_id` | integer \| null | 既存フィールド。参加者リンクの無いゲスト/未リンクエントラントでは`null`。 |
| `loser_id` | integer \| null | 既存フィールド。 |
| `winner_score` | integer | 既存フィールド。 |
| `loser_score` | integer | 既存フィールド。 |
| `round_text` | string \| null | 既存フィールド。 |
| `round` | integer \| null | 既存フィールド。 |
| `phase` | string \| null | 既存フィールド。 |
| `phase_order` | integer \| null | 既存フィールド。 |
| `wave` | string \| null | 既存フィールド。 |
| `dq` | boolean | 既存フィールド。 |
| `cancel` | boolean | 既存フィールド。 |
| `state` | integer | 既存フィールド（start.gg側のset state）。 |
| `details` | array | 既存フィールド。ゲーム単位の詳細（`game_id`、`order_num`、`winner_id`、スコア、`stage`、`selections`）。 |

### 状態遷移

```
（存在しない） --[イベントのset ID一覧を取得]--> placeholder
placeholder    --[setの詳細取得に成功]-----------> complete
placeholder    --[setの詳細取得に失敗]-----------> placeholder（変化なし、後で再取得）
complete       --[再取得。例: バージョンバックフィル]--> complete（その場で上書き。同じset_id）
```

レコードが`complete`から`placeholder`に戻ることは無い。状態遷移をまたいで
`set_id`が変わることも無い（FR-004, FR-008）。1つのイベント内で1つの`set_id`
につき常にちょうど1件のレコードが存在する（FR-008）——既にレコードが存在する
`set_id`（プレースホルダーであれ完了済みであれ）に対して、取得処理が2件目の
レコードを追記することは無い。

### バリデーションルール（spec.mdのFunctional Requirementsから導出）

- FR-002/FR-007: イベントについて（ID一覧取得により）判明している全ての
  `set_id`は、`matches.json`内に対応するレコード（プレースホルダーまたは
  完了済み）をちょうど1件持たなければならない。
- FR-008: 同じイベントの`matches.json`内で、2つのレコードが同じ`set_id`を
  共有することは無い。
- FR-009: イベントが「完了」（`archive_status: "completed"`付きの
  `attr.json`を書き込む資格がある）とみなされるのは、`matches.json`内の
  全レコードが`complete`状態である場合、またはそのレコードが既存の
  `excluded_phases.json`除外機構（本機能では変更なし）の対象として明示的に
  除外されている場合のみ。

## エンティティ: Event（イベント。既存。挙動のみ変更）

新規フィールドは無い。挙動の変更点: `attr.json`の存在が、FR-009に従い
「プレースホルダーのMatch Recordが1件も残っていないこと」（単一の取得試行の
成功/失敗ではなく、状態）によってゲートされるようになる。`attr.json`に関する
その他の事項（`docs/data_model.md`の既存スキーマ）は、`event_data_version`の
引き上げを除き、本機能によって変更されない。

## 共有定数: `EVENT_DATA_VERSION`

`scripts/utils.py`: `5 → 6`。このイベントスキーマ世代の`matches.json`レコードは
`set_id`を持ち、（完了前は一時的に）プレースホルダーレコードを含み得ることを
示す。`scripts/fetch/backfill_schema_version.py`の既存の巡回バックフィル
（research.md §5）を駆動する——そのスキャナ自体には特別な変更は不要で、既に
`attr.json`の`event_data_version`（無ければ`0`扱い）を現在の定数と汎用的に
比較しているため。

## 関連

```
Event（1） ── has ── Match Record（0..N）   [N = イベントの総set数]
Match Record ── belongs to exactly one ── start.gg Set（set_idで紐付け）
```

関連の変更は無い。`matches.json`は引き続きMatch Recordを保持する唯一の場所
であり、引き続き今日と同じパスに置かれる
（`data/startgg/events/{Region}/{YYYY}/{MM}/{DD}/{Tournament}/{Event}/matches.json`）。
