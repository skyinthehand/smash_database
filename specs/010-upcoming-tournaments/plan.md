# Implementation Plan: 未開催トーナメントの管理

**Branch**: `010-upcoming-tournaments` | **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-upcoming-tournaments/spec.md`

## Summary

start.gg上でまだ開始されていないJPのスマッシュブラザーズSP大会を、既存の
(開催済み大会の)履歴データとは独立した単一のJSONL索引ファイル
(`data/startgg/upcoming_tournaments.jsonl`)に、日次で全件洗い替えする形で
記録する。各種目には参加登録人数と、既存のイベントラベリング機構による
ラベル判定結果も含める。取得は新規スクリプト
(`scripts/fetch/download_upcoming_tournaments.py`)として独立させ、既存の
`update_tournament.yml`に失敗許容ステップとして追加する。

## Technical Context

**Language/Version**: Python 3.11(既存の`scripts/fetch/`と同一)

**Primary Dependencies**: `requests`(既存と同一。新規の外部依存追加なし)

**Storage**: `data/startgg/upcoming_tournaments.jsonl`(単一のJSONLファイル。
per-tournament/per-eventディレクトリは作らない)

**Testing**: `unittest`(`scripts/test/`、`python -m unittest discover`)

**Target Platform**: GitHub Actions(`ubuntu-latest`、`update_tournament.yml`)
およびローカルCLI実行

**Project Type**: 既存のデータ取得パイプラインへの追加スクリプト
(`scripts/fetch/`)

**Performance Goals**: 特になし(日次バッチ、JP圏の開催前大会は数十〜
百件程度の小規模データを想定)

**Constraints**: 憲法Principle Vにより、start.gg APIアクセスは
`scripts/utils.py`の`fetch_data_with_retries`/`fetch_all_nodes`を経由
しなければならない。既存の(開催済み大会の)履歴データ・ファイルは
本機能によって一切変更してはならない(FR-007)。

**Scale/Scope**: JP圏・対象ゲーム1種目の開催前大会一覧(将来的に
`country_code`を変えて他地域にも適用できる構造にする)。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I(データスキーマの整合性とバージョニング)**: 新規ファイル
  `data/startgg/upcoming_tournaments.jsonl`のスキーマを`docs/data_model.md`
  に追記し、各レコードは`version`フィールドを持つ。**PASS**(対応予定、
  Phase 1のdata-model.mdで詳細化)。
- **Principle II(冪等でインクリメンタルな収集)**: 本機能は意図的にこの
  原則の対象外とする。spec.mdで確定した通り、未開催データは「完了」概念を
  持たず(いつまでも変わりうる)、`done.csv`的な重複回避の対象にならない
  ため、既存の`scripts/fetch/*`とは異なり**全件を毎回取得し直して完全
  洗い替えする**設計を意図的に採用する。**Complexity Trackingで正当化**
  (下記参照)。
- **Principle III(マージ前の検証ゲート)**: 新規スクリプトに対応する
  テストを`scripts/test/`に追加し、`scripts.test.test_validate_data`を
  含む既存テスト一式が引き続きpassすることを確認する。**PASS**。
- **Principle IV(ブランチとオートメーションの規律)**: 既存の
  `update_tournament.yml`(`main`への直接commit、`main-data-commits`
  concurrency group)に、新規ステップとして追加するのみで、新たな
  ブランチ・ワークフローは作らない。**PASS**。
- **Principle V(外部APIへの耐障害アクセス)**: 新規クエリ・取得関数は
  既存の`fetch_data_with_retries`/`fetch_all_nodes`をそのまま利用し、
  独自のリトライ・バックオフは実装しない。**PASS**。

## Project Structure

### Documentation (this feature)

```text
specs/010-upcoming-tournaments/
├── plan.md              # このファイル
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output(/speckit-tasksで作成、本コマンドでは作らない)
```

### Source Code (repository root)

```text
scripts/
├── queries.py                              # 既存。未開催大会一覧クエリを追加
├── labeling.py                             # 既存。変更なし、そのまま再利用
├── utils.py                                # 既存。write_jsonl等をそのまま再利用
└── fetch/
    ├── download.py                         # 既存。変更なし(履歴データ用)
    └── download_upcoming_tournaments.py    # 新規。本機能のエントリポイント

scripts/test/
└── test_download_upcoming_tournaments.py   # 新規

data/startgg/
└── upcoming_tournaments.jsonl              # 新規。本機能が出力する唯一のデータファイル

.github/workflows/
└── update_tournament.yml                   # 既存。新規ステップを1つ追加

docs/
└── data_model.md                           # 既存。新規セクションを追加
```

**Structure Decision**: 既存の`scripts/fetch/`パターンを踏襲した独立
スクリプト1本 + 新規クエリ関数1〜2個 + 新規データファイル1本、という
最小構成。既存の`download.py`(履歴データ用、冪等incremental収集)には
一切手を加えず、ライフサイクルの異なる新機能を完全に分離する。

### Post-Design Re-check(Phase 1完了後)

`research.md`・`data-model.md`・`contracts/`・`quickstart.md`作成後も、
上記5原則の判定に変化なし。新規ファイル(`upcoming_tournaments.jsonl`)・
新規スクリプト・新規クエリ関数はいずれも既存の共通基盤
(`fetch_data_with_retries`/`write_jsonl`/`compute_event_labels`)を
再利用するのみで、独自実装を追加していない。**GATE: PASS**。

## Complexity Tracking

> Principle II(冪等でインクリメンタルな収集)からの逸脱について

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| `done.csv`的な重複回避を行わず、`upcoming_tournaments.jsonl`を毎回全件で洗い替える | 未開催データは開催日変更・エントリー増減・中止等により恒常的に変化し、「取得済みだから再取得不要」という前提(Principle IIの趣旨)がそもそも成立しない。既存の履歴データのような「一度確定したら基本不変」という性質を持たない | 既存の`done.csv`/`done_events.csv`方式を流用して差分更新にする案は、`docs/fix.md`にある「開催延期時にtournaments.jsonlの記録が古いままだと重複ディレクトリが発生する」のと同種の不整合(日程変更・中止の検知漏れ)を新たに生みやすく、単一ファイルの全件洗い替えの方が実装・検証コストの両面で単純で安全なため採用しない |
