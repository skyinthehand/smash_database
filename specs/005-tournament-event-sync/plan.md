# Implementation Plan: トーナメント単位でのイベント作り直し検知と空イベントの整理

**Branch**: `005-tournament-event-sync` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-tournament-event-sync/spec.md`

## Summary

`004-fix-duplicate-events` の実データ検証で、第7回チバスマ交流会(tournament_id=811466)が
「延期」ではなく「event_idの作り直し」(1423946 → 1533881)であったことが判明した。
既存の全ての自動取得経路は `fetch_event_ids_from_tournament(tournament_id, game_id)` で
「今まさに有効なイベント一覧」を取得するだけで、過去に記録した event_id との差分検知を
行っていないため、作り直された新しいイベントは自動的には一切発見されない。

本機能では、ユーザーの明示的な指示に基づき、「置き換え」の対応関係を判定する複雑なロジックは
持たず、代わりに2つの独立した仕組みを追加する: (1) `tournaments.jsonl` に記録済みの各
トーナメントについて、start.gg側の現在のイベント一覧を定期的に再取得し、記録に無い新しい
event_id を通常の取得と同じ手順で保存する(`scripts/fetch/` に新規スクリプト)。(2)
`standings.json` と `matches.json` が両方とも空のイベントディレクトリを検出し削除する
(`scripts/fix/` に新規スクリプト)。両者を組み合わせることで、置き換え判定なしに最終的な
データセットが整理された状態に収束する。

## Technical Context

**Language/Version**: Python 3.11(既存コードベースと統一)

**Primary Dependencies**: 標準ライブラリのみ。既存の `scripts.fetch.download`
(`fetch_event_ids_from_tournament`, `download_standings`, `download_seeds`,
`download_all_set`, `write_event_attributes`, `get_date_parts`, `get_event_directory`,
`count_guest_entrants`, `extend_user_info`)、`scripts.utils`
(`fetch_data_with_retries`, `read_json`, `read_tournaments_jsonl`, `write_jsonl`,
`read_users_jsonl`)を再利用する。新規サードパーティ依存は追加しない。

**Storage**: `data/startgg/events/**`(既存ファイルベース)、`data/startgg/tournaments.jsonl`
(既存)。新規カーソルファイル `data/startgg/tournament_event_sync_cursor.txt`
(User Story 1 の循環スキャン用、既存の `schema_backfill_cursor.txt` と同じ仕組み)を追加。

**Testing**: `unittest`。新規モジュール `scripts/fetch/backfill_tournament_events.py` /
`scripts/fix/prune_empty_events.py` それぞれに対応するテストファイルを新設する。

**Target Platform**: GitHub Actions `ubuntu-latest`(新規ワークフロー)+ ローカル CLI 実行。

**Project Type**: single project(CLI / データパイプラインスクリプト)。

**Performance Goals**: User Story 1(API呼び出しを伴う)は既存の段階的バックフィルと同様、
循環スキャン・カーソル永続化・1回あたりの処理件数上限により、一度に大量のAPI呼び出しが
発生しないようにする。User Story 2(ローカルファイルの削除のみ、API呼び出し無し)は
毎回全件スキャンしても実行コストが小さいため、循環スキャンは不要とする。

**Constraints**: 新規の独自リトライ・ページネーション実装は追加しない(Constitution V、
既存の `fetch_data_with_retries` / `fetch_event_ids_from_tournament` を再利用)。
ディレクトリ削除(User Story 2)は git 管理下で行われるため、誤って削除しても
`git log` / `git checkout` で復元可能(004 の `record_event_path()` と同じ考え方)。
スクリプトの役割分離規約(Constitution 開発ワークフロー節: `scripts/fetch/` は取得、
`scripts/fix/` は補完・検証・修復)に従い、API呼び出しを伴う新規イベント発見は
`scripts/fetch/`、ローカル削除のみの空イベント整理は `scripts/fix/` に配置する。

**Scale/Scope**: 新規ファイル2つ(`scripts/fetch/backfill_tournament_events.py`,
`scripts/fix/prune_empty_events.py`)、対応するテストファイル2つ、新規ワークフロー1つ
(`.github/workflows/tournament_event_sync.yml`)。既存ファイルへの変更は無し(004とは
異なり、`download.py` や `backfill_schema_version.py` 自体は変更しない)。第7回チバスマ
交流会1件のみ、本機能の検証ケースとして実際の解消を確認する。全トーナメントへの初回適用
(未知数の既存の空ディレクトリの整理・未発見イベントの発見)は、新設する循環スキャンの
通常サイクルに委ねる。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | 判定 | 根拠 |
|---|---|---|
| I. データスキーマの整合性とバージョニング | PASS | `attr.json` 等のスキーマ(フィールド)は変更しない。既存の取得・保存ロジック(`write_event_attributes` 等)をそのまま再利用するのみ。`EVENT_DATA_VERSION` のバンプは不要。 |
| II. 冪等でインクリメンタルな収集 | PASS(実装タスクあり) | User Story 1 は同じ event_id を二重に取得しない(記録済み event_id 集合との差分のみ取得)。User Story 2 は既に削除済みのディレクトリに対して再実行しても no-op。 |
| III. マージ前の検証ゲート(NON-NEGOTIABLE) | PASS(実装タスクあり) | 新規スクリプトそれぞれにテストを追加し、既存の `test_validate_data` 等が無変更で通ることを確認する。 |
| IV. ブランチとオートメーションの規律 | PASS | 新規ワークフローも既存の `data_backfill.yml`/`schema_backfill.yml` と同じパターンで `chore-update` ブランチへのみ commit/push する。`main` への反映は既存のPR経由フローを踏襲。 |
| V. 外部APIへの耐障害アクセス | PASS | 新規の独自リトライ・ページネーション実装は追加しない。`fetch_event_ids_from_tournament` 等、既存の `fetch_data_with_retries` 経由の関数をそのまま再利用する。 |

「大量の re-fetch や再構成を伴う破壊的なデータ移行を行う前に、対象範囲と想定される影響を
PR 説明に明記する」(開発ワークフロー節): User Story 2(空ディレクトリ削除)は既存データに
対する削除操作を伴う。初回ロールアウト時にどの程度の件数が削除対象になるか未知数のため、
PR 説明に「初回実行時の対象件数は事前に把握できていない」旨と、削除は git 管理下で
可逆的である旨を明記する。想定影響(新規ワークフローの追加、既存ワークフローへの変更は無し)
も明記する。

違反なし。Complexity Tracking への記載は不要。

## Project Structure

### Documentation (this feature)

```text
specs/005-tournament-event-sync/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── tournament-event-discovery.md
│   └── empty-event-cleanup.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created here)
```

### Source Code (repository root)

```text
scripts/
├── fetch/
│   └── backfill_tournament_events.py  # [NEW] tournaments.jsonl に記録済みの各
│                                       #   トーナメントを循環スキャンし、
│                                       #   fetch_event_ids_from_tournament() で
│                                       #   現在のイベント一覧を再取得。記録済み
│                                       #   event_id 集合に無い新しい event_id を
│                                       #   検出し、既存の取得関数
│                                       #   (download_standings 等)で新規保存する
├── fix/
│   └── prune_empty_events.py          # [NEW] events_root を全件スキャンし、
│                                       #   standings.json と matches.json が
│                                       #   両方とも空のディレクトリを削除。
│                                       #   tournaments.jsonl から対応する
│                                       #   イベント記録も取り除き書き戻す
└── test/
    ├── test_backfill_tournament_events.py  # [NEW]
    └── test_prune_empty_events.py          # [NEW]

.github/workflows/
└── tournament_event_sync.yml          # [NEW] chore-update ブランチへの定期実行
                                        #   (schema_backfill.yml と同じパターン)

data/startgg/
├── tournament_event_sync_cursor.txt   # [NEW] User Story 1 の循環スキャン用カーソル
├── events/Japan/2025/08/16/第7回チバスマ交流会/  # [検証対象、コード修正の
│                                       #   実行結果として削除されることを確認する]
└── events/Japan/2026/02/07/第7回チバスマ交流会/  # [検証対象、event_id=1533881が
                                        #   新規取得されることを確認する]
```

**Structure Decision**: 単一プロジェクト構成。Constitution の役割分離規約(`scripts/fetch/`
= 取得、`scripts/fix/` = 補完・検証・修復)に従い、User Story 1(API呼び出しを伴う新規発見)
と User Story 2(ローカル削除のみ)を別ファイルとして新設する。既存ファイル(`download.py`,
`backfill_schema_version.py`)への変更は行わない。

## Complexity Tracking

> Constitution Check に違反がないため、このセクションは空欄。
