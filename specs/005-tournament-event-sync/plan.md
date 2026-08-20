# Implementation Plan: 空イベントディレクトリの整理

**Branch**: `005-tournament-event-sync` | **Date**: 2026-08-17(2026-08-18 に再スコープ) | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-tournament-event-sync/spec.md`

## Summary

当初は「トーナメント単位でのイベント一覧差分検知」(旧User Story 1)と「空イベント
ディレクトリの整理」(User Story 2)の2本立てで計画したが、第7回チバスマ交流会の
実データ検証により、旧User Story 1が前提としていた「同一tournament_id内でのevent_id
作り直し」という仮説が誤りだったことが判明した(実際は tournament_id=811466 →
867504 という**別のトーナメント**が作られていた)。真の原因は
`scripts/fetch/download.py` の `download_all_tournaments()`/`download_by_ids()` が
`tournaments.jsonl` への記録を取得パイプライン完了後まで遅延させていたことであり、
これは `004-fix-duplicate-events` の延長として直接修正した(本specの成果物ではない)。

この修正により旧User Story 1は不要と判断し撤回した。本機能は
**空イベントディレクトリの整理(`scripts/fix/prune_empty_events.py`)のみ**を対象とする。

## Technical Context

**Language/Version**: Python 3.11(既存コードベースと統一)

**Primary Dependencies**: 標準ライブラリのみ。既存の `scripts.utils`
(`read_json`, `read_tournaments_jsonl`, `write_jsonl`)を再利用する。新規サードパーティ
依存は追加しない。

**Storage**: `data/startgg/events/**`(既存ファイルベース)、`data/startgg/tournaments.jsonl`
(既存)。新規の永続化ファイルは追加しない(旧User Story 1用に計画していたカーソル
ファイルは、撤回に伴い不要)。

**Testing**: `unittest`。`scripts/fix/prune_empty_events.py` に対応するテストファイルを
新設する。

**Target Platform**: GitHub Actions `ubuntu-latest`(新規ワークフロー
`.github/workflows/prune_empty_events.yml`、`chore-update` へ直接コミットする既存の
`schema_backfill.yml` / `update_tournament.yml` / `update_user.yml` と同じ
`concurrency: group: chore-update-branch` に参加させる)+ ローカル CLI 実行。
API呼び出しを伴わないため `STARTGG_TOKEN` は不要。

**Project Type**: single project(CLI / データパイプラインスクリプト)。

**Performance Goals**: ローカルファイルの削除のみ(API呼び出し無し)のため、毎回全件
スキャンしても実行コストが小さく、循環スキャン・カーソル永続化は不要。

**Constraints**: ディレクトリ削除は git 管理下で行われるため、誤って削除しても
`git log` / `git checkout` で復元可能(`004` の `record_event_path()` と同じ考え方)。
Constitution の役割分離規約に従い `scripts/fix/` に配置する。

**Scale/Scope**: 新規ファイル1つ(`scripts/fix/prune_empty_events.py`)、対応する
テストファイル1つ、新規ワークフロー1つ(`.github/workflows/prune_empty_events.yml`)。
第7回チバスマ交流会の旧event_id(1423946)ディレクトリ1件のみ、本機能の検証ケースとして
実際の削除を確認する。

**関連する別修正(本specのスコープ外、`004-fix-duplicate-events` の延長)**:
`scripts/fetch/download.py` の `download_all_tournaments()` / `download_by_ids()` を、
`tournaments.jsonl` への記録(`record_event_path()` 呼び出し)が取得処理開始前
(event_idと保存先パスが判明した時点)に行われるよう修正した。これにより、取得が
途中で失敗しても event_id とパスの対応関係だけは記録され、後続のバックフィル
(`backfill_schema_version.py` 等)から復旧可能になる。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | 判定 | 根拠 |
|---|---|---|
| I. データスキーマの整合性とバージョニング | PASS | スキーマ変更なし。 |
| II. 冪等でインクリメンタルな収集 | PASS | 既に削除済みのディレクトリに対して再実行しても no-op。 |
| III. マージ前の検証ゲート(NON-NEGOTIABLE) | PASS(実装タスクあり) | `prune_empty_events.py` にテストを追加し、既存の `test_validate_data` 等が無変更で通ることを確認する。 |
| IV. ブランチとオートメーションの規律 | PASS | 新規ワークフローも既存パターンで `chore-update` ブランチへのみ commit/push する。 |
| V. 外部APIへの耐障害アクセス | PASS | API呼び出しを行わない。 |

「大量の re-fetch や再構成を伴う破壊的なデータ移行を行う前に、対象範囲と想定される影響を
PR 説明に明記する」(開発ワークフロー節): 空ディレクトリ削除は既存データに対する削除操作を
伴う。初回ロールアウト時の対象件数は未知数のため、PR 説明に明記し、削除は git 管理下で
可逆的である旨も明記する。

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
│   ├── tournament-event-discovery.md  # [撤回済み、旧User Story 1の記録として保持]
│   └── empty-event-cleanup.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created here)
```

### Source Code (repository root)

```text
scripts/
└── fix/
    └── prune_empty_events.py          # events_root を全件スキャンし、
                                        #   standings.json と matches.json が
                                        #   両方とも空のディレクトリを削除。
                                        #   tournaments.jsonl から対応する
                                        #   イベント記録も取り除き書き戻す

scripts/test/
└── test_prune_empty_events.py

.github/workflows/
└── prune_empty_events.yml             # chore-update ブランチへの定期実行
                                        #   (schema_backfill.yml と同じパターン、
                                        #   STARTGG_TOKEN不要)

data/startgg/events/Japan/2025/08/16/第7回チバスマ交流会/  # [検証対象、
                                        #   コード修正の実行結果として削除される
                                        #   ことを確認する]
```

**撤回された成果物**(旧User Story 1、2026-08-18時点で削除済み):
`scripts/fetch/backfill_tournament_events.py`、`scripts/test/test_backfill_tournament_events.py`、
`.github/workflows/tournament_event_sync.yml`。`contracts/tournament-event-discovery.md`
は撤回の経緯を残すため削除せずそのまま残す。

**Structure Decision**: 単一プロジェクト構成。Constitution の役割分離規約に従い
`scripts/fix/` に配置する。

## Complexity Tracking

> Constitution Check に違反がないため、このセクションは空欄。
