# Implementation Plan: 大会延期による重複イベントディレクトリとattr.json欠落の解消

**Branch**: `004-fix-duplicate-events` | **Date**: 2026-08-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-fix-duplicate-events/spec.md`

## Summary

第7回チバスマ交流会(tournament_id=811466, event_id=1423946)が `Japan/2025/08/16/...`
(延期前、entrant数0件の空データ)と `Japan/2026/02/07/...`(延期後、attr.json欠落)の
2箇所に重複して存在する。原因は3つのバグの組み合わせ: (1) `download_all_tournaments()` が
保存先ディレクトリを取得時点の `startAt` から決め打ちで計算し、延期を検知・統合する仕組みが
無い、(2) 同じロジックが `tournaments.jsonl` のイベント記録パスを、既知の `event_id` に
対しては一切更新しないため、完了判定(`should_skip_tournament`)が実体と食い違う古いパスを
見続ける、(3) `backfill_schema_version.py` の対象発見が `attr.json` の存在を前提にした
`rglob("attr.json")` のため、`attr.json` が欠落しているイベント(大規模イベントの取得失敗で
発生)は永久に発見されない。

本機能では、この3つを `scripts/fetch/download.py` と `scripts/fetch/backfill_schema_version.py`
の局所的な修正で解消し、修正後のロジックを使って第7回チバスマ交流会の重複を実際に解消する。
新規ファイル・新規ワークフローは追加しない。

## Technical Context

**Language/Version**: Python 3.11(既存コードベースと統一)

**Primary Dependencies**: 標準ライブラリのみ(`os`, `shutil` を新規使用)。新規サードパーティ
依存は追加しない。

**Storage**: `data/startgg/events/**`(ファイルベース、`{Region}/{YYYY}/{MM}/{DD}/{Tournament}/{Event}`
レイアウト)、`data/startgg/tournaments.jsonl`。新規の永続化ファイルは追加しない。

**Testing**: `unittest`。`scripts/test/test_download.py` に延期検知・ディレクトリ統合・
`tournaments.jsonl` パス更新のテストを追加。`scripts/test/test_backfill_schema_version.py` に
`attr.json` 欠落ディレクトリの発見・`tournaments.jsonl` からの event_id 復元のテストを追加。

**Target Platform**: GitHub Actions `ubuntu-latest`(既存の `data_backfill.yml` /
`update_tournament.yml` / `schema_backfill.yml` 等)+ ローカル CLI 実行。新規ワークフローは
不要。

**Project Type**: single project(CLI / データパイプラインスクリプト)。

**Performance Goals**: 新規の常時実行コストは発生しない。延期検知は既存の
`fetch_latest_tournaments_by_game()` 呼び出しループ内で、既に取得済みの `startAt` を使った
文字列比較のみで行う(追加API呼び出しなし)。`attr.json` 欠落ディレクトリの発見も既存の
`rglob` 走査対象を変えるだけで、走査対象ディレクトリ数の増加は欠落分(661件規模)にとどまる。

**Constraints**: 大量の re-fetch や破壊的なデータ移行を PR で一括実行しない(Constitution
「開発ワークフロー」節)。古いディレクトリの削除は、対応する新しいディレクトリの必須ファイル
一式(`REQUIRED_EVENT_FILES`)が揃っていることを確認できた場合のみ行う(データを失わない)。
新規の独自リトライ・ページネーション実装は追加しない(Constitution V)。

**Scale/Scope**: 変更対象は `scripts/fetch/download.py`(`should_skip_tournament()`,
`download_all_tournaments()` のイベント記録更新ロジック)、
`scripts/fetch/backfill_schema_version.py`(`iter_event_dirs()`, `backfill_one_event()`)の
2ファイル。661件の `attr.json` 欠落・複数件の重複ディレクトリの実際の再取得・解消は、
本機能のコード修正を適用した上で既存の段階的バックフィル/日次更新の通常サイクルに委ねる
(実際の start.gg API アクセスを伴う一括処理はスコープ外)。第7回チバスマ交流会1件のみ、
本機能の検証ケースとして実際の解消を確認する。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | 判定 | 根拠 |
|---|---|---|
| I. データスキーマの整合性とバージョニング | PASS | `attr.json` 等のスキーマ自体(フィールド追加)は変更しない。保存先ディレクトリの決定ロジックと発見ロジックのみを修正するため、`docs/data_model.md` の更新は不要。ディレクトリレイアウト規約(`docs/directory.md`)自体も変更しない。 |
| II. 冪等でインクリメンタルな収集 | PASS(実装タスクあり) | 延期検知・ディレクトリ統合ロジックは、同じ入力(同一 event_id・同一 startAt)に対して複数回実行しても安全(2回目以降はパス一致のため no-op)であるよう設計する。`done.csv`/`tournaments.jsonl` の役割は維持し、内容の正確性を修正するのみ。 |
| III. マージ前の検証ゲート(NON-NEGOTIABLE) | PASS(実装タスクあり) | `test_download.py` / `test_backfill_schema_version.py` に新規ロジックのテストを追加し、既存の `test_validate_data` は無変更で通ることを確認する。 |
| IV. ブランチとオートメーションの規律 | PASS | 既存ワークフロー(`data_backfill.yml` 等)の変更なし。自動化は引き続き `chore-update` 経由。`tournaments.jsonl` の更新は既存の `write_jsonl`/`extend_tournament_info` 経由のまま(手動編集は行わない)。 |
| V. 外部APIへの耐障害アクセス | PASS | 新規の独自リトライ・ページネーション実装は追加しない。既存の `fetch_data_with_retries()` 経由の呼び出し構造は変更しない。 |

「大量の re-fetch や再構成を伴う破壊的なデータ移行を行う前に、対象範囲と想定される影響を
PR 説明に明記する」(開発ワークフロー節): 本PRでは、661件全件の一括再取得は実行せず(実行
手段が無いため)、コード修正のみを行う。想定影響(修正適用後、次回の `data_backfill.yml` /
`schema_backfill.yml` 実行サイクルで段階的に対象が処理されること、第7回チバスマ交流会1件は
本PR内で検証すること)をPR説明に明記する。

違反なし。Complexity Tracking への記載は不要。

## Project Structure

### Documentation (this feature)

```text
specs/004-fix-duplicate-events/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── tournament-relocation.md
│   └── backfill-discovery.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created here)
```

### Source Code (repository root)

```text
scripts/
├── fetch/
│   ├── download.py                   # [MODIFY] should_skip_tournament() に延期検知を
│   │                                  #   追加。download_all_tournaments() のイベント
│   │                                  #   記録更新ロジックを「追加のみ」から「パスが
│   │                                  #   変わっていれば更新+旧ディレクトリ削除」に変更
│   └── backfill_schema_version.py    # [MODIFY] iter_event_dirs() の発見対象を
│                                      #   attr.json存在ベースから standings.json
│                                      #   存在ベースに変更。backfill_one_event() に
│                                      #   attr.json欠落時のtournaments.jsonlからの
│                                      #   event_id復元フォールバックを追加
└── test/
    ├── test_download.py              # [MODIFY] 延期検知・ディレクトリ統合・
    │                                  #   tournaments.jsonl更新のテストを追加
    └── test_backfill_schema_version.py  # [MODIFY] attr.json欠落ディレクトリの発見・
                                       #   event_id復元のテストを追加

data/startgg/events/Japan/2025/08/16/第7回チバスマ交流会/  # [検証対象、コード修正の
                                       #   実行結果として解消されることを確認する]
```

**Structure Decision**: 単一プロジェクト構成(既存の `scripts/fetch/` `scripts/test/` の役割
分担をそのまま踏襲)。新規ファイル・新規ワークフローは作成せず、既存の2ファイルへの局所的な
修正のみで完結する。

## Complexity Tracking

> Constitution Check に違反がないため、このセクションは空欄。
