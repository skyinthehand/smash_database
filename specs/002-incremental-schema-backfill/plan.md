# Implementation Plan: 既存イベントへのスキーマ追加フィールドの段階的バックフィル

**Branch**: `002-incremental-schema-backfill` | **Date**: 2026-08-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-incremental-schema-backfill/spec.md`

## Summary

`matches.json` の `phase_order` や `attr.json` の `guest_entrant_count` のように、
スキーマへフィールドを追加するたびに既存の約26,736件のイベントディレクトリが
「古いスキーマのまま」取り残される問題を解決する。整数の一元管理された
`EVENT_DATA_VERSION` を定義し、各イベントの `attr.json` に取得時点のバージョン
(`event_data_version`)を記録する。新規スケジュールワークフローが、バージョンが
古いイベントディレクトリを安定ソート順で巡回スキャンし、1回の実行につき
設定可能な上限件数だけ再取得・バージョン更新する。カーソルをファイルに永続化し、
次回実行時に続きから再開することで、API レート制限や1回のワークフロー実行時間の
制約内で、最終的に全イベントを最新バージョンへ収束させる。

## Technical Context

**Language/Version**: Python 3.11(既存の `.github/workflows/*.yml` の `setup-python` と統一)

**Primary Dependencies**: 標準ライブラリのみ(`json`, `argparse`, `pathlib`)+ 既存の
`scripts.utils`(`fetch_data_with_retries`, `fetch_all_nodes`, `read_json`, `write_json`,
`set_api_parameters`, `set_retry_parameters` 等)、`scripts.fetch.download`
(`download_standings`, `download_seeds`, `download_all_set`, `write_event_attributes`,
`extend_user_info`)、`scripts.queries`(`get_event_details_by_id_query`)。新規の
サードパーティ依存は追加しない。

**Storage**: `data/startgg/events/**/attr.json` に新規フィールド `event_data_version`
(int)を追加。進捗カーソルは `data/startgg/schema_backfill_cursor.txt`
(プレーンテキスト1行、直近にスキャンしたイベントディレクトリのパス)に保存。

**Testing**: `unittest`。新規 `scripts/test/test_backfill_schema_version.py` を追加し、
`python -m unittest scripts.test.test_backfill_schema_version` で実行。既存の
`python -m unittest scripts.test.test_validate_data` には影響を与えない
(`event_data_version` は `ATTR_REQUIRED_FIELDS` に追加しない — 存在しなくても
既存のバリデーションは壊れないことを保証する)。

**Target Platform**: GitHub Actions `ubuntu-latest`(新規ワークフロー
`.github/workflows/schema_backfill.yml`)+ ローカル CLI 実行。

**Project Type**: single project(CLI / データパイプラインスクリプト。
frontend/backend の分離なし)。

**Performance Goals**: イベントディレクトリの `attr.json` を読んで
`event_data_version` を確認するだけのスキャンは、`validate_data.py` の
実測(約26,736件・約20秒)と同等かそれ以下の時間で完了する想定
(読むフィールドが1つ少ないため同等以下)。1回の実行で実際に API 呼び出しを
伴う再取得件数は `--max_events` で上限を設定し、ワークフローのタイムアウト
予算内(参考値: `update_tournament.yml` 120分, `update_user.yml` 360分)に
収める。

**Constraints**: 新規の独自 API 実装を追加しない(Constitution V)。`main` へ
直接 push しない、必ず `chore-update` ブランチ経由(Constitution IV)。
`attr.json` へのフィールド追加は `docs/data_model.md` を同一 PR で更新する
(Constitution I)。

**Scale/Scope**: 既存イベントディレクトリ約26,736件。スキーマバージョンが
上がるたびに対象件数は増減する(新規追加分は最初から最新版で取得されるため
対象外、既存分のうち未処理のものが対象)。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | 判定 | 根拠 |
|---|---|---|
| I. データスキーマの整合性とバージョニング | PASS(実装タスクあり) | `attr.json` に `event_data_version` を追加するため、`docs/data_model.md` を同一PRで更新する(Phase 1 の data-model.md 参照)。既存データへの影響は本機能自体が担う移行手段(`scripts/fix/backfill_events.py` 相当の役割を本機能の新規スクリプトが果たす)。 |
| II. 冪等でインクリメンタルな収集 | PASS | バージョン比較により、既に目標バージョンに達したイベントは API 呼び出し自体を行わない(FR-005)。同じ入力に対する再実行は安全(既に最新なら何もしない)。 |
| III. マージ前の検証ゲート(NON-NEGOTIABLE) | PASS(実装タスクあり) | 新規ロジック(バージョン判定・循環カーソル)に対する新規テストを `scripts/test/` に追加する。既存の `test_validate_data` は変更しない(`event_data_version` は必須フィールドに加えないため後方互換)。 |
| IV. ブランチとオートメーションの規律 | PASS | 新規ワークフローは `chore-update` ブランチへコミットし、`chore-update-branch` concurrency グループを既存ワークフローと共有する。`main` への直接 push はしない。 |
| V. 外部APIへの耐障害アクセス | PASS | 新規スクリプトは `fetch_data_with_retries()` / 既存の `download_standings()` 等を再利用するのみで、独自のリトライ・ページネーション実装を行わない。 |

違反なし。Complexity Tracking への記載は不要。

## Project Structure

### Documentation (this feature)

```text
specs/002-incremental-schema-backfill/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── cli.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created here)
```

### Source Code (repository root)

```text
scripts/
├── utils.py                          # [MODIFY] EVENT_DATA_VERSION 定数を追加
├── fetch/
│   ├── download.py                   # [MODIFY] write_event_attributes() が
│   │                                  #   event_data_version を書き込むようにする
│   ├── download_specific_event.py    # [MODIFY] 同上
│   └── backfill_schema_version.py    # [NEW] 循環スキャン + カーソル + バックフィル本体
├── fix/
│   └── redownload_event.py           # [MODIFY] write_event_attributes() 経由で
│                                      #   event_data_version が自然に付与されることを確認
└── test/
    └── test_backfill_schema_version.py  # [NEW]

.github/workflows/
└── schema_backfill.yml               # [NEW] スケジュール実行 + workflow_dispatch

docs/
└── data_model.md                     # [MODIFY] attr.json に event_data_version を追記

data/startgg/
└── schema_backfill_cursor.txt        # [NEW, ランタイム生成] カーソル永続化ファイル
```

**Structure Decision**: 単一プロジェクト構成(既存の `scripts/fetch/` `scripts/fix/`
`scripts/test/` の役割分担をそのまま踏襲)。新規ファイルは
`scripts/fetch/backfill_schema_version.py`(取得ロジック)と対応するテスト、
新規ワークフロー1本のみ。既存の `scripts/fix/backfill_events.py` や
`data_force_refresh_backfill.yml` は変更しない(research.md #5 参照)。

## Complexity Tracking

> Constitution Check に違反がないため、このセクションは空欄。
