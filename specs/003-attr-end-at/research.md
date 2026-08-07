# Phase 0 Research: イベント記録への大会終了日時(end_at)の保存

Technical Context に `NEEDS CLARIFICATION` は残っていない。以下は実装前提として
コードベース調査で確定した事実と、それに基づく設計判断。

## 1. 3つの取得経路それぞれでの `endAt` の入手可否

**調査結果**:

| 取得経路 | エントリポイント | 使用クエリ | `tournament.endAt` |
|---|---|---|---|
| 大会一覧の一括スキャン | `download_all_tournaments()`(`download.py`) | `get_tournaments_by_game_query` | 取得済み(`end_timestamp` 変数に代入されるが未保存) |
| 大会ID指定の個別取得 | `download_by_ids()`(`download.py`) | `get_tournament_by_id_query` | 取得済み(同上、`end_timestamp` 未保存) |
| イベント再取得(バックフィル) | `backfill_one_event()`(`backfill_schema_version.py`) | `get_event_details_by_id_query` | 取得済み(`tournament.get("endAt")` として応答に含まれるが未使用) |
| トーナメント/イベントslug指定の個別取得 | `download_specific_event()`(`download_specific_event.py`) | `get_event_details_by_tournament_query` | **未取得**(クエリの `tournament` ブロックに `endAt` が無い) |

**Decision**: 4経路中3経路は既にAPIレスポンスに `endAt` を含んでおり、クエリ変更は
不要(保存処理を追加するだけでよい)。`get_event_details_by_tournament_query` のみ、
`tournament` ブロックに `endAt` を追加する。

**Rationale**: 既存のリトライ・ページング実装(Constitution V)に触れずに済む、
最小差分の変更で済む。

**Alternatives considered**: 4経路すべてで同一のクエリ生成関数に統一する大規模
リファクタリングも考えられたが、本機能のスコープ(`end_at` の保存)を超えるため
不採用。既存の「経路ごとに独立したクエリ関数を持つ」構造(`queries.py` の設計)を
踏襲する。

## 2. `write_event_attributes()` が2箇所に独立定義されている点への対応

**調査結果**: `download.py` と `download_specific_event.py` に、ほぼ同一内容の
`write_event_attributes()` がそれぞれ個別に定義されている(共通化されていない)。

**Decision**: 両方に同じ変更(`end_at` 引数の追加と `json_data` への格納)を加える。
共通化(片方を削除してimportで共有する等のリファクタリング)は行わない。

**Rationale**: 既存の重複は本機能が生んだものではなく、今回のスコープ外。
リファクタリングを混ぜると差分が肥大化し、レビュー・検証の対象が本来の目的
(`end_at` の保存)から逸れる。

**Alternatives considered**: 共通化してから変更する案は、影響範囲(両ファイルの
既存呼び出し全て)を広げてしまい、本機能に必要な変更量に対して不釣り合いに大きい
ため見送り。将来的な技術的負債として認識するに留める。

## 3. 値が存在しない場合の扱い

**調査結果**: `download_all_tournaments()` は `end_timestamp is None` の場合、既に
その大会全体をダウンロード対象から除外している(「まだ終了していない大会」として
スキップ)。したがって、この経路経由で保存されるイベントの `end_at` が `None` に
なることは実質的に無い。一方、`download_by_ids()` や `download_specific_event()`
にはこの事前フィルタが無く、`endAt` が `None` の大会(進行中/日程未確定)を
明示的に処理しようとすると `None` を渡すことになる。

**Decision**: `end_at` は `None`(JSON上は `null`)を許容するフィールドとして扱い、
値が無い場合でも取得処理自体は失敗させない(spec.md FR-003 のとおり)。

**Rationale**: 既存の `timestamp` フィールド運用(大会開始日時は必須情報として
早い段階で取得される)と異なり、終了日時は取得タイミングによって未確定でありうる。
必須値化すると `download_by_ids` / `download_specific_event` 経由の取得を不必要に
失敗させてしまう。

## 4. 既存イベントへの反映方法

**Decision**: 新しいバックフィル専用スクリプトは作らず、`scripts/utils.py` の
`EVENT_DATA_VERSION` を `2` から `3` に上げる。既存の
`scripts/fetch/backfill_schema_version.py` は `event_data_version` が現在の
`EVENT_DATA_VERSION` より古いイベントを自動的に再取得対象とするため、この変更
だけで `002-incremental-schema-backfill` の既存サイクル(`schema_backfill.yml`)が
既存イベントへ `end_at` を段階的に反映する。

**Rationale**: spec.md の Assumptions で明記した前提(既存の段階的バックフィル
機構の再利用)そのもの。Constitution I の「既存データへの影響がある場合は
MUST 移行する」を、既存の汎用移行手段を再利用することで満たす(新規移行スクリプト
は不要)。

**Alternatives considered**: 専用のワンショット移行スクリプトを新規に書く案は、
`002-incremental-schema-backfill` が既に解決した問題(全件一括再取得はAPIレート
制限・実行時間制約に収まらない)を再発明することになるため不採用。

## 5. `ATTR_REQUIRED_FIELDS` への追加要否

**Decision**: `scripts/fix/validate_data.py` の `ATTR_REQUIRED_FIELDS` には
`end_at` を追加しない。

**Rationale**: `event_data_version` や `guest_entrant_count` を追加した際と同じ
後方互換方針。`end_at` はバックフィルが完了するまで既存イベントの大多数に存在
しないため、必須フィールド化すると `test_validate_data` およびCI上の
`data_monthly_check.yml`(Constitution III)がバックフィル完了まで恒常的に
失敗し続けることになる。
