# Implementation Plan: 大会属性判定ロジックの内製化(参加資格制限大会ラベル)

**Branch**: `009-eligibility-restricted-labeling` | **Date**: 2026-08-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-eligibility-restricted-labeling/spec.md`

## Summary

外部消費者が独自に行っていた「トーナメント名/イベント名に特定の文字列が含まれるかどうか」に
基づく参加資格制限大会の判定を、smash_database 内部に移動する。判定文字列リストは
`scripts/label_rules.py` にプレーンな Python リストとして git 管理し、判定結果は
`attr.json` の `labels.registration_restricted`(真偽値)として、新規取得時に
自動付与する。既存の全イベントデータには、start.gg への再アクセスを伴わない
単純な一括適用ツール(`scripts/fix/apply_registration_restricted_label.py`)を
新規に提供し、手動実行で `labels` を更新する。

## Technical Context

**Language/Version**: Python 3.11(既存スクリプト群と統一)

**Primary Dependencies**: 標準ライブラリのみ(`json`, `argparse`, `pathlib`)。
新規のサードパーティ依存は追加しない。

**Storage**: `data/startgg/events/**/attr.json` の `labels.registration_restricted`
フィールド(真偽値)を追加・更新する。新規ファイルは判定ロジック用の
`scripts/label_rules.py`(コードの一部、データストアではない)のみ。

**Testing**: `unittest`。`scripts/test/test_label_rules.py`(判定ロジック単体)と
`scripts/test/test_apply_registration_restricted_label.py`(一括適用ツール)を
新規追加する。既存の `write_event_attributes` 系テストへの影響も確認する。

**Target Platform**: ローカル CLI 実行のみ(GitHub Actions によるスケジュール実行は
本機能のスコープ外、spec の FR-006 のとおり)。

**Project Type**: single project(CLI / データパイプラインスクリプト)。

**Performance Goals**: 一括適用ツールは `data/startgg/events` 全件
(現状約26,700件超)を、API通信なしのローカルファイル読み書きのみで処理する。
`validate_data.py` の実測(全件スキャンで約20秒)と同等かそれ以下の時間で
完了する想定。

**Constraints**: start.gg への新規APIアクセスを一切追加しない
(Constitution V の対象外、そもそもAPIを呼ばない)。`attr.json` の
`labels` 内の既存プロパティ(OpenAI推定分等)を破壊しない。スキーマ変更
(`labels.registration_restricted` の追加)は `docs/data_model.md` を同一PRで
更新する(Constitution I)。

**Scale/Scope**: 既存イベントディレクトリ約26,700件超が一括適用ツールの対象。
新規取得分は今後すべて自動対象になる。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | 判定 | 根拠 |
|---|---|---|
| I. データスキーマの整合性とバージョニング | PASS(実装タスクあり) | `attr.json.labels` に `registration_restricted` を追加するため、`docs/data_model.md` を同一PRで更新する。既存データへの移行手段は本機能自体が提供する一括適用ツール。 |
| II. 冪等でインクリメンタルな収集 | PASS(対象外) | 本機能は start.gg からの取得処理そのものを変更しない(取得済みデータのローカル導出のみ)。一括適用ツールは同じ入力に対して常に同じ結果になる(冪等)。 |
| III. マージ前の検証ゲート(NON-NEGOTIABLE) | PASS(実装タスクあり) | 判定ロジック・一括適用ツールに新規テストを追加する。 |
| IV. ブランチとオートメーションの規律 | PASS(対象外) | 本機能はスケジュール実行のワークフローを持たない(FR-006)。一括適用ツールは手動実行のローカルコマンドであり、`chore-update` ブランチへのコミットは通常の手動コミットフローに従う。 |
| V. 外部APIへの耐障害アクセス | PASS(対象外) | 本機能はいかなる箇所でも start.gg API を呼び出さない。 |

違反なし。Complexity Tracking への記載は不要。

## Project Structure

### Documentation (this feature)

```text
specs/009-eligibility-restricted-labeling/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── cli.md
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
scripts/
├── label_rules.py                                 # [NEW] REGISTRATION_RESTRICTED_KEYWORDS
│                                                   #   と is_registration_restricted()
├── fetch/
│   ├── download.py                                # [MODIFY] write_event_attributes() が
│   │                                               #   labels.registration_restricted を
│   │                                               #   非破壊マージするようにする
│   └── download_specific_event.py                 # [MODIFY] 同上(別実装への反映)
├── fix/
│   └── apply_registration_restricted_label.py     # [NEW] 既存データへの一括適用ツール
└── test/
    ├── test_label_rules.py                         # [NEW]
    └── test_apply_registration_restricted_label.py # [NEW]

docs/
└── data_model.md                                  # [MODIFY] labels.registration_restricted を追記
```

**Structure Decision**: 単一プロジェクト構成。既存の `scripts/fetch/`(取得)・
`scripts/fix/`(補完・検証・修復)の役割分担をそのまま踏襲し、判定ロジック本体は
両者から参照される独立モジュール `scripts/label_rules.py` に切り出す
(research.md #1〜#3 参照)。

## Complexity Tracking

> Constitution Check に違反がないため、このセクションは空欄。
