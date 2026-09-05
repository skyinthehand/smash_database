# Implementation Plan: 汎用イベントラベリング機構(大会名・イベント名ルールベース判定)

**Branch**: `009-eligibility-restricted-labeling` | **Date**: 2026-09-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-eligibility-restricted-labeling/spec.md`

## Summary

外部消費者が独自に行っていた「トーナメント名/イベント名に特定の文字列が
含まれるかどうか」に基づく大会属性判定を、smash_database 内部の汎用ルール
エンジンに移動する。判定ルールは `data/startgg/label_rules.json` に
宣言的なJSONとしてgit管理し、判定結果は `attr.json.labels` の任意個数の
真偽値キー、適用したルールセットのバージョンは新規フィールド
`attr.json.label_version`(`event_data_version`とは独立)として、新規取得
イベントには自動で(`scripts/fetch/download.py`/
`scripts/fetch/download_specific_event.py` の `write_event_attributes()`
経由で)、既存イベントには専用の一括適用ツール
(`scripts/fix/apply_label_rules.py`、start.gg再アクセス不要・デフォルト
dry-run)で反映する。判定ロジック本体は新規モジュール `scripts/labeling.py`
に切り出し、両経路から再利用する。

## Technical Context

**Language/Version**: Python 3.11(既存スクリプト群と統一)

**Primary Dependencies**: 標準ライブラリのみ(`json`, `re`, `argparse`,
`pathlib`, `functools`)。新規のサードパーティ依存は追加しない。

**Storage**: 新規データファイル `data/startgg/label_rules.json`(ルール
定義、人間が編集しgit管理)。既存 `data/startgg/events/**/attr.json` の
`labels` フィールド(既存キーを非破壊で拡張)と、新規トップレベル
フィールド `label_version` を追加・更新する。

**Testing**: `unittest`。`scripts/test/test_labeling.py`(判定エンジン
単体: ルール読み込み・検証・マッチング・非破壊マージ・バージョンゲート)、
`scripts/test/test_apply_label_rules.py`(一括適用ツール: dry-run/--yes・
壊れたattr.jsonのスキップ・label_version一致スキップ・冪等性、
`scripts/test/test_fix_path_collision.py` と同様のパターンで作成)を
新規追加する。既存の `scripts/test/test_download.py`・
`scripts/test/test_download_specific_event.py` に、`write_event_attributes()`
が `labels`/`label_version` を正しく書き込むことを確認するケースを追加する。

**Target Platform**: ローカル CLI 実行のみ。一括適用ツールは
GitHub Actions等によるスケジュール実行を必要としない(FR-008)。新規取得
経路への組み込みは、既存の `download.py` 等の実行(ローカル・GitHub Actions
問わず)にそのまま乗る。

**Project Type**: single project(CLI / データパイプラインスクリプト)。

**Performance Goals**: 一括適用ツールは `data/startgg/events` 全件
(現状約26,700件超)を、API通信なしのローカルファイル読み書きのみで処理
する。ルールセットの読み込み・正規表現コンパイルはプロセス内で1回のみ
(research.md #3)。`label_version` が既に一致するイベントは判定の
再計算自体を行わないため(FR-010)、ルール未変更時の再実行はごく短時間で
完了する。

**Constraints**: 一括適用ツールは start.gg への新規APIアクセスを一切
追加しない(Constitution V の対象外)。新規取得経路
(`write_event_attributes()`)は既存の取得フロー内で完結し、追加のAPI呼び出しを
発生させない。`attr.json.labels` 内の、ルール定義ファイルが管理しない
既存プロパティ(OpenAI推定による`registration_type`等)を破壊しない
(FR-006)。スキーマ変更(`labels`の拡張・`label_version`追加)は
`docs/data_model.md` を同一PRで更新する(Constitution I)。

**Scale/Scope**: 既存イベントディレクトリ約26,700件超が一括適用ツールの
対象。新規取得分は今後すべて自動対象になる。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | 判定 | 根拠 |
|---|---|---|
| I. データスキーマの整合性とバージョニング | PASS(実装タスクあり) | `attr.json.labels` の拡張・新規`label_version`フィールドの追加に伴い、`docs/data_model.md`を同一PRで更新する。既存データへの移行手段は本機能自体が提供する一括適用ツール(`scripts/fix/apply_label_rules.py`)。 |
| II. 冪等でインクリメンタルな収集 | PASS(対象外) | 本機能はstart.ggからの取得処理そのもの(何を取得するか)を変更しない。一括適用ツールは同じルール定義・同じ入力に対して常に同じ結果になる(冪等、FR-010の再実行安全性要件どおり)。 |
| III. マージ前の検証ゲート(NON-NEGOTIABLE) | PASS(実装タスクあり) | `scripts/labeling.py`・`scripts/fix/apply_label_rules.py`に新規テストを追加する。既存の`write_event_attributes()`系テストへの回帰確認も行う。 |
| IV. ブランチとオートメーションの規律 | PASS(対象外) | 一括適用ツールはスケジュール実行のワークフローを持たない手動実行のローカルコマンド(FR-008)。新規取得経路は既存の取得ワークフローにそのまま乗るため、本機能による新規のブランチ・push規律への影響はない。 |
| V. 外部APIへの耐障害アクセス | PASS(対象外) | 一括適用ツール(`scripts/fix/apply_label_rules.py`)はstart.gg APIを一切呼び出さない。新規取得経路への組み込みは既存の`fetch_data_with_retries()`等の呼び出し箇所を変更せず、その結果(`tournament_name`/`event_name`等)を利用するのみ。 |

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
data/startgg/
└── label_rules.json                                # [NEW] ラベル判定ルール定義
                                                      #   (label_version, min_event_data_version, matches)

scripts/
├── labeling.py                                      # [NEW] ルール読み込み・検証・
│                                                     #   コンパイル・判定・非破壊マージの
│                                                     #   共通エンジン(research.md #3)
├── fetch/
│   ├── download.py                                  # [MODIFY] write_event_attributes() が
│   │                                                 #   scripts.labeling.compute_event_labels()
│   │                                                 #   を呼び出し labels/label_version を設定
│   ├── download_specific_event.py                   # [MODIFY] 同上(独自実装への反映)
│   └── backfill_schema_version.py                   # [変更不要] download.py の
│                                                     #   write_event_attributes を import しており
│                                                     #   自動的に新挙動を継承
├── fix/
│   ├── apply_label_rules.py                         # [NEW] 既存データへの一括適用ツール
│   │                                                 #   (dry-runデフォルト、--yesで実書き込み)
│   ├── redownload_event.py                           # [変更不要] 同上
│   ├── backfill_events.py                            # [変更不要] 同上
│   └── fix_path_collision.py                         # [変更不要] 同上
└── test/
    ├── test_labeling.py                              # [NEW]
    ├── test_apply_label_rules.py                     # [NEW]
    ├── test_download.py                              # [MODIFY] labels/label_version の
    │                                                 #   回帰テストを追加
    └── test_download_specific_event.py                # [MODIFY] 同上

docs/
└── data_model.md                                    # [MODIFY] labels の例・label_version
                                                      #   フィールド・label_rules.json の説明を追記
```

**Structure Decision**: 単一プロジェクト構成。既存の `scripts/fetch/`
(取得)・`scripts/fix/`(補完・検証・修復)の役割分担をそのまま踏襲し、
判定ロジック本体は両者から参照される独立モジュール `scripts/labeling.py`
に切り出す(research.md #3〜#4 参照)。`write_event_attributes()`は
物理的に2実装(`download.py`/`download_specific_event.py`)のみ存在し、
他4経路(`redownload_event.py`/`backfill_schema_version.py`/
`backfill_events.py`/`fix_path_collision.py`)はいずれかをimportしている
だけのため、コード変更は不要(research.md #0, #4 参照)。

## Complexity Tracking

> Constitution Check に違反がないため、このセクションは空欄。
