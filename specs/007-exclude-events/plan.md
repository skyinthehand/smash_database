# Implementation Plan: 取得対象からのイベント除外

**Branch**: `007-exclude-events` | **Date**: 2026-08-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-exclude-events/spec.md`

## Summary

特定のevent_idを、以後の自動取得・`tournaments.jsonl`登録の対象から
除外できるようにする。除外対象は、既存の`data/startgg/excluded_phases.json`
(phase_id単位の除外)を`data/startgg/excluded_events.json`へリネーム・
拡張した単一のファイルで管理する。同じファイル内で、event_id配下の
値が配列なら従来通りphase単位の除外、`reason`を直下に持つオブジェクト
ならイベント全体の除外、という形で2種類の除外を区別する(`type`
フィールドは追加しない。`research.md` Decision 1参照)。既存の
`load_excluded_phase_ids()`と同じ「呼び出し側が明示的にファイルを
読んでチェックする」スタイルを踏襲し、通常のクロール
(`download_all_tournaments`/`download_by_ids`)、個別イベント再取得
(`redownload_event.py`)、`tournaments.jsonl`の抜け補完・検証系ツール
(`backfill_tournament_index.py`/`check_events_in_tournaments.py`/
`fix_missing_tournaments.py`)の各エントリポイントで、イベント
ディレクトリパスまたはevent_idが判明した直後にイベント全体除外の
チェックを追加する(`check_events_in_tournaments.py`/
`fix_missing_tournaments.py`は`/speckit-analyze`によるレビューで
対象に追加)。

## Technical Context

**Language/Version**: Python 3.11(既存コードベースと同一。
`.github/workflows/schema_backfill.yml`等で使用中のバージョンに合わせる)

**Primary Dependencies**: 標準ライブラリのみ(`json`/`os`)。新規の外部
依存は追加しない。既存の`scripts/utils.py`の`read_json`/`write_json`を
再利用する。

**Storage**: ファイルベース、git管理(`data/startgg/excluded_phases.json`
を`data/startgg/excluded_events.json`へリネームして拡張。`git mv`で
リネームし、既存のphase単位除外エントリは無変換で引き継ぐ)。DBMSは
使用しない(`tournaments.jsonl`等と同じ運用)。

**Testing**: `unittest`(`scripts/test/`配下、既存パターン踏襲)。

**Target Platform**: Linux(ローカル実行 / GitHub Actions `ubuntu-latest`)。

**Project Type**: 既存のデータ収集パイプライン(CLIスクリプト群)への
機能追加。新規プロジェクト・新規サービスの追加ではない。

**Performance Goals**: 非該当。除外チェックはローカルの小規模JSON
ファイル1回読み込み+辞書ルックアップのみで、既存のstart.gg APIリクエスト
回数を増加させない(SC-003の前提でもある)。

**Constraints**: 既存のAPIリクエストパターン・retryポリシー
(`fetch_data_with_retries`等)には一切変更を加えない。除外チェックの
追加によって、除外対象でない既存イベントの取得挙動・APIコストが変化
しないこと(spec.md FR-005)。

**Scale/Scope**: 除外エントリ数は数件〜数十件程度を想定した、手動運用の
小規模な設定ファイル(大量データの一括除外は想定しない)。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 判定 | 根拠 |
|---|---|---|
| I. データスキーマの整合性とバージョニング | PASS | `excluded_events.json`(リネーム後)は`docs/data_model.md`が`version`必須と定めるイベントデータファイル群(attr/matches/standings/seeds/tournaments.jsonl/users.jsonl)には該当しない、既存の`excluded_phases.json`と同種の設定ファイル。リネーム・スキーマ拡張は`docs/data_model.md`(または`docs/startgg_design.md`)へ同一PRで記載する。 |
| II. 冪等でインクリメンタルな収集 | PASS | 除外チェックは既存の`done.csv`/`should_skip_tournament`等の判定に並行する追加ガードであり、既存の冪等性・再実行安全性を変更しない。 |
| III. マージ前の検証ゲート(NON-NEGOTIABLE) | PASS(実装時に要対応) | 新しいデータ形状(event全体除外エントリ)を追加し、既存`load_excluded_phase_ids()`の挙動も変更するため、`scripts/test`に両方の対応テストを新設する(`tasks.md`で明記)。 |
| IV. ブランチとオートメーションの規律 | PASS | GitHub Actions自動化のcommit/push方式・concurrency設計には変更を加えない。除外リストの追加・削除は手動のファイル編集+通常のコミットを前提とする。 |
| V. 外部APIへの耐障害アクセス | PASS | 除外チェックはローカルファイル読み込みのみで、start.gg APIへの新規呼び出しを一切発生させない。既存のリトライ・ページングロジックには触れない。 |
| データ保存規約 | PASS | 新ファイルは`data/startgg/`配下に置く。シークレットは扱わない。 |
| 開発ワークフロー | PASS | `scripts/fetch/`(取得)・`scripts/fix/`(補完・修復)それぞれの既存責務の範囲内での変更に留める。spec-kit生成物は日本語で記述済み。 |

違反なし。Complexity Trackingへの記載事項は無い。

## Project Structure

### Documentation (this feature)

```text
specs/007-exclude-events/
├── plan.md              # このファイル(/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output(/speckit-tasks command — 本コマンドでは作成しない)
```

`contracts/`は作成しない: 本フィーチャーは外部に公開するAPI/CLIインター
フェースの新設を伴わない(既存のCLIスクリプトの内部挙動変更のみ)。
ファイル形状の契約は`data-model.md`に記載済み。

### Source Code (repository root)

既存レイアウトへの追加のみで、新しいトップレベルディレクトリは作らない。

```text
data/startgg/
└── excluded_events.json     # excluded_phases.json からリネーム。
                              #   event単位・phase単位の除外を1ファイルで扱う

scripts/
├── fetch/
│   └── download.py          # EXCLUDED_PHASES_PATH → EXCLUDED_EVENTS_PATH に
                              #   リネーム。load_excluded_phase_ids() を
                              #   配列形状エントリのみ対象に修正。
                              #   load_excluded_event_ids() を新設し、
                              #   download_all_tournaments() / download_by_ids()
                              #   の該当箇所に除外チェックを追加
├── fix/
│   ├── redownload_event.py             # 除外チェックを追加
│   ├── backfill_tournament_index.py    # 除外チェックを追加
│   ├── check_events_in_tournaments.py  # 除外チェックを追加(/speckit-analyze指摘)
│   └── fix_missing_tournaments.py      # 除外チェックを追加(/speckit-analyze指摘)
└── test/
    ├── test_download.py                    # load_excluded_event_ids()・修正後の
                                             #   load_excluded_phase_ids()・
                                             #   download_all_tournaments()/
                                             #   download_by_ids()のスキップ挙動テスト
    ├── test_backfill_tournament_index.py   # 除外挙動テストを追加
    ├── test_check_events_in_tournaments.py # 新規作成、除外挙動テスト
    └── test_fix_missing_tournaments.py     # 新規作成、除外挙動テスト

docs/
├── data_model.md          # 「管理ファイル」節に excluded_events.json の
│                           #   スキーマ(2種類のエントリ形状)を新規追記
├── fix.md                 # excluded_phases.json への言及を
│                           #   excluded_events.json に更新
└── startgg_design.md      # 同上
```

**Structure Decision**: 新規プロジェクト/新規ディレクトリは作らず、
既存の`scripts/fetch/`(取得)・`scripts/fix/`(補完・修復)・
`scripts/test/`という既存の責務分割(憲法「開発ワークフロー」節)に
そのまま追加する。除外リストの読み込みロジック(`load_excluded_event_ids()`、
および修正後の`load_excluded_phase_ids()`)は、既存と同じく
`scripts/fetch/download.py`に置き、`scripts/fix/`側の各ツールからは
それをimportして利用する(既存の`download.py`から`scripts/fix/`側が
importする既存の依存方向と一貫させる)。

## Complexity Tracking

*本フィーチャーはConstitution Checkの全項目をPASSしており、記載事項は無い。*
