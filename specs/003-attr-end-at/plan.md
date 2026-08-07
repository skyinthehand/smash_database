# Implementation Plan: イベント記録への大会終了日時(end_at)の保存

**Branch**: `003-attr-end-at` | **Date**: 2026-08-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-attr-end-at/spec.md`

## Summary

`attr.json` に大会の開始日時(`timestamp`)は保存されているが、終了日時は保存されていない。
start.gg からは大会の終了日時(`endAt`)自体は3つの取得経路のうち2つで既に取得済みだが、
「まだ終了していない大会をスキップする」判定にのみ使われて捨てられている。残る1経路
(スラッグ指定の個別イベント取得)はクエリ自体に `endAt` が含まれていない。本機能では、
既存の `write_event_attributes()`(`download.py` / `download_specific_event.py` に
それぞれ独立定義)へ `end_at` 引数を追加して保存対象に加え、不足しているクエリには
`endAt` フィールドを追加し、`EVENT_DATA_VERSION` を1つ上げることで既存イベントへの反映を
既存の段階的バックフィル機構(`002-incremental-schema-backfill`)に委ねる。

## Technical Context

**Language/Version**: Python 3.11(既存コードベースと統一)

**Primary Dependencies**: 標準ライブラリのみ。新規サードパーティ依存は追加しない。
既存の `scripts.queries`(`get_event_details_by_tournament_query`)、
`scripts.utils`(`EVENT_DATA_VERSION`)を変更する。

**Storage**: `data/startgg/events/**/attr.json` に新規フィールド `end_at`(int、
UNIXタイムスタンプ、値なしの場合は `null`)を追加。新規の永続化ファイルは無い。

**Testing**: `unittest`。既存の `scripts/test/test_download.py` に
`write_event_attributes()` が `end_at` を書き込むことを検証するテストケースを追加。
`scripts/test/test_backfill_schema_version.py` に、バックフィル経路でも `end_at` が
反映されることを検証するケースを追加。既存の `scripts.test.test_validate_data` には
影響を与えない(`end_at` は `ATTR_REQUIRED_FIELDS` に追加しない — `event_data_version` /
`guest_entrant_count` 追加時と同じ後方互換方針)。

**Target Platform**: GitHub Actions `ubuntu-latest`(既存の `schema_backfill.yml` /
`update_tournament.yml` 等)+ ローカル CLI 実行。新規ワークフローは不要。

**Project Type**: single project(CLI / データパイプラインスクリプト)。

**Performance Goals**: 新規の API 呼び出しは発生しない(既存レスポンスに既に含まれる
フィールドを保存対象に加えるだけ、または既存クエリに1フィールド追加するのみ)。
既存の段階的バックフィルの1回あたりの処理件数・所要時間に本機能起因の増加はない。

**Constraints**: 新規の独自 API 実装を追加しない(Constitution V)。`attr.json` への
フィールド追加は `docs/data_model.md` を同一PRで更新する(Constitution I)。
`EVENT_DATA_VERSION` を上げることで、既存データへの反映は新規移行スクリプトを
書かずに既存のバックフィル機構に委ねる(Constitution I の「既存データへの影響がある
場合は...MUST 移行する」を、既存の汎用移行手段の再利用で満たす)。

**Scale/Scope**: 変更対象は `write_event_attributes()` の2つの独立定義、
呼び出し元3箇所(`download_all_tournaments`, `download_by_ids`,
`backfill_one_event`)+ `download_specific_event()`、クエリ定義2箇所
(新規追加1・既存確認1)。データ移行そのものは `002-incremental-schema-backfill` の
既存サイクルに委ねるため本機能のスコープ外。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | 判定 | 根拠 |
|---|---|---|
| I. データスキーマの整合性とバージョニング | PASS(実装タスクあり) | `attr.json` に `end_at` を追加し `docs/data_model.md` を同一PRで更新する(Phase 1 data-model.md 参照)。既存データへの影響は `EVENT_DATA_VERSION` を上げることで既存の段階的バックフィル機構(`002-incremental-schema-backfill`)による移行に委ねる。 |
| II. 冪等でインクリメンタルな収集 | PASS | 新規フィールド追加のみで、取得対象イベントの判定ロジック(`done.csv` 等)自体は変更しない。 |
| III. マージ前の検証ゲート(NON-NEGOTIABLE) | PASS(実装タスクあり) | `test_download.py` / `test_backfill_schema_version.py` に新規フィールドの検証を追加し、`test_validate_data` は後方互換のため無変更。 |
| IV. ブランチとオートメーションの規律 | PASS | 既存ワークフローの変更なし。データ移行は既存の `chore-update` 経由バックフローに委ねる。 |
| V. 外部APIへの耐障害アクセス | PASS | 新規の独自リトライ・ページネーション実装は追加しない。既存クエリへのフィールド追加(`get_event_details_by_tournament_query`)のみ。 |

違反なし。Complexity Tracking への記載は不要。

## Project Structure

### Documentation (this feature)

```text
specs/003-attr-end-at/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── attr-json.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created here)
```

### Source Code (repository root)

```text
scripts/
├── utils.py                          # [MODIFY] EVENT_DATA_VERSION を 2 → 3 に更新
├── queries.py                        # [MODIFY] get_event_details_by_tournament_query()
│                                      #   のtournamentブロックに endAt を追加
│                                      #   (get_tournaments_by_game_query /
│                                      #   get_tournament_by_id_query /
│                                      #   get_event_details_by_id_query は既に
│                                      #   endAt を含むため変更不要)
├── fetch/
│   ├── download.py                   # [MODIFY] write_event_attributes() に
│   │                                  #   end_at 引数を追加してattr.jsonへ保存。
│   │                                  #   download_all_tournaments() /
│   │                                  #   download_by_ids() の呼び出し箇所を
│   │                                  #   既存の end_timestamp 変数を渡すよう更新
│   ├── download_specific_event.py    # [MODIFY] 独立定義の write_event_attributes()
│   │                                  #   に同様の変更。fetch_event_details_by_slug()
│   │                                  #   のtournament統合辞書に endAt を追加し、
│   │                                  #   download_specific_event() から渡す
│   └── backfill_schema_version.py    # [MODIFY] fetch_event_details() が返す
│                                      #   tournament から endAt を取り出し
│                                      #   write_event_attributes() 呼び出しに渡す
└── test/
    ├── test_download.py              # [MODIFY] write_event_attributes() が
    │                                  #   end_at を書き込むことを検証
    └── test_backfill_schema_version.py  # [MODIFY] バックフィル経路でも end_at が
                                       #   反映されることを検証

docs/
└── data_model.md                     # [MODIFY] attr.json のスキーマ例に end_at を追記

data/startgg/events/**/attr.json      # [既存データ, 変更対象外]
                                       #   EVENT_DATA_VERSION バンプにより、既存の
                                       #   schema_backfill.yml サイクルが自然に
                                       #   end_at を反映する(本機能では個別対応しない)
```

**Structure Decision**: 単一プロジェクト構成(既存の `scripts/fetch/` `scripts/queries.py`
`scripts/test/` の役割分担をそのまま踏襲)。新規ファイル・新規ワークフローは作成せず、
既存の3つの取得経路(一括スキャン・ID指定・スラッグ指定)とバックフィル経路への
局所的な修正のみで完結する。

## Complexity Tracking

> Constitution Check に違反がないため、このセクションは空欄。
