# Implementation Plan: 同日同名トーナメントの保存先パス衝突の解消

**Branch**: `008-tournament-path-collision` | **Date**: 2026-08-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-tournament-path-collision/spec.md`

## Summary

同じ地域・開催日・大会名を持つが、tournament_idが異なる別々の大会が
存在する場合、現在の保存先ディレクトリ計算(`get_event_directory()`、
地域/開催日/大会名/イベント名の文字列のみに基づく)では両者が同じ
パスに解決され、データが混在・上書きされてしまう。通常のクロール
(`download_all_tournaments`/`download_by_ids`)に、メモリ上の
`tournaments`辞書を用いたO(1)の衝突検出を追加し、衝突時は参加者数
(`num_entrants`)が多い方の保存先名を維持し、少ない方だけを
`大会名_(tournament_id)`という決定的な形式にリネームする。参加者数が
新規イベント側でまだ判明していない場合は、standings取得(既存フロー内で
いずれ実行されるステップ)が完了するまで最終確定を遅延させる。個別
イベント再取得(`redownload_event.py`)にも、同じ命名形式を使った、
より単純な片方向の衝突回避(常に自分自身をずらし、参加者数比較は
行わない)を追加する。また、過去に発生した未検出の衝突を洗い出す監査
ツールと、人間の確認・実行指示のもとで衝突を分離する専用の修復ツールを
新設する。

## Technical Context

**Language/Version**: Python 3.11(既存コードベースと同一)

**Primary Dependencies**: 標準ライブラリのみ(`os`/`shutil`/`json`)。
新規の外部依存は追加しない。既存の`scripts/utils.py`の`read_json`/
`write_json`、`scripts/fetch/download.py`の既存のディレクトリ移動
パターン(`cleanup_relocated_directory`)を再利用する。

**Storage**: ファイルベース。新規のデータファイルは追加しない
(`tournaments.jsonl`の既存の`path`フィールドの値のみが変わり得る)。

**Testing**: `unittest`(`scripts/test/`配下、既存パターン踏襲)。

**Target Platform**: Linux(ローカル実行 / GitHub Actions `ubuntu-latest`)。

**Project Type**: 既存のデータ収集パイプライン(CLIスクリプト群)への
機能追加。

**Performance Goals**: 衝突が無い通常時のクロールについて、追加の
API呼び出し・追加のディスクI/Oを発生させない(`research.md` Decision 1)。
衝突検出はメモリ上の辞書参照のみで行う。

**Constraints**: 参加者数の比較には、新規イベント側は既存フロー内で
いずれ実行される`download_standings()`の戻り値を、既存イベント側は
その`attr.json`の`num_entrants`を用いる(新規の専用APIクエリは追加
しない。`research.md` Decision 2参照、将来的な軽量クエリへの切り替えは
Alternatives参照)。

**Scale/Scope**: 実際に衝突するケースは稀(既知1件+監査で見つかる
未知の件数)。監査・修復ツールは手動運用の小規模ツールとして設計する。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 判定 | 根拠 |
|---|---|---|
| I. データスキーマの整合性とバージョニング | PASS | `tournaments.jsonl`のスキーマ自体(フィールド構成)は変更しない。`path`フィールドの値の計算ロジックが変わるのみ。`attr.json`等のイベントデータファイルのスキーマも変更しない。 |
| II. 冪等でインクリメンタルな収集 | PASS(実装時に要注意) | 衝突解決によるディレクトリリネームは、実行が途中で中断されても次回実行時に安全に再開・収束できなければならない(既存の`cleanup_relocated_directory`の「新配置の完全性を確認してから旧を消す」安全パターンを踏襲することで担保する)。`tasks.md`でこの観点のテストを明記する。 |
| III. マージ前の検証ゲート(NON-NEGOTIABLE) | PASS(実装時に要対応) | 衝突検出・命名調整・監査・修復の各ロジックについて`scripts/test`に対応テストを新設する。 |
| IV. ブランチとオートメーションの規律 | PASS | 通常のクロールのGitHub Actions自動化(commit/push方式・concurrency)には変更を加えない。衝突解決によるリネームは個々のイベント単位の小規模な操作であり、`docs/*.md`の更新が必要な大規模な破壊的移行には該当しない。 |
| V. 外部APIへの耐障害アクセス | PASS | 新規のAPI呼び出しパターンを追加しない(既存の`download_standings`等をそのまま利用)。`fetch_data_with_retries`を経由しない独自リトライは実装しない。 |
| データ保存規約 | PASS | 新規ファイルは追加しない。既存のディレクトリレイアウト規約(`docs/directory.md`)を維持する(パスの構成要素自体は変わらず、大会名部分の文字列だけが調整される)。 |
| 開発ワークフロー | PASS | 新規ツール(`find_path_collisions.py`/`fix_path_collision.py`)は`scripts/fix/`に配置し、既存の1ツール=1責務の方針を踏襲する(`redownload_event.py`は拡張しない。`research.md` Decision 6)。`docs/directory.md`等への追記が必要かは実装時に確認する。 |

違反なし。Complexity Trackingへの記載事項は無い。

## Project Structure

### Documentation (this feature)

```text
specs/008-tournament-path-collision/
├── plan.md              # このファイル(/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output(/speckit-tasks command — 本コマンドでは作成しない)
```

`contracts/`は作成しない: 本フィーチャーは外部に公開するAPI/CLIインター
フェースの新設を伴わない(新設する2ツールのCLI引数は`quickstart.md`に
記載済みで、既存の`redownload_event.py`等と同じ引数命名規則を踏襲する)。

### Source Code (repository root)

既存レイアウトへの追加のみ。

```text
scripts/
├── fetch/
│   └── download.py          # build_path_index() / resolve_path_collision() /
│                             #   disambiguate_event_name() を新設。
│                             #   download_all_tournaments() / download_by_ids()
│                             #   の event_dir 確定直後(既存の除外チェックと
│                             #   同じ挿入点)に衝突検出・解決を追加
├── fix/
│   ├── redownload_event.py      # event_dir 確定後、自分自身の衝突回避
│   │                             #   チェックを追加(US5, FR-012)。
│   │                             #   disambiguate_event_name() をimportして再利用
│   ├── find_path_collisions.py  # 新規: US3 監査ツール(read-only)
│   └── fix_path_collision.py    # 新規: US4 修復ツール
│       # (redownload_event.py と同じ低レベル取得関数群を再利用する)
└── test/
    ├── test_download.py             # build_path_index/resolve_path_collision/
    │                                 #   disambiguate_event_name の単体テスト、
    │                                 #   download_all_tournaments/download_by_ids
    │                                 #   への統合テストを追加
    ├── test_redownload_event.py     # 既存(spec 007由来)にUS5の衝突回避
    │                                 #   テストを追加
    ├── test_find_path_collisions.py # 新規
    └── test_fix_path_collision.py   # 新規
```

**Structure Decision**: 衝突検出・解決ロジックの中核
(`build_path_index`/`resolve_path_collision`/`disambiguate_event_name`)
は、同種のロジック(`update_event_registration`/`cleanup_relocated_directory`/
`load_excluded_event_ids`)と同じ`scripts/fetch/download.py`に置き、
`scripts/fix/`側の新規ツールはそこからimportして再利用する(既存の
依存方向と一貫させる)。監査・修復は既存の`scripts/fix/`の1ツール=1責務
の方針に従い、それぞれ独立した新規スクリプトとする。

## Complexity Tracking

*本フィーチャーはConstitution Checkの全項目をPASSしており、記載事項は
無い。Principle IIの「実装時に要注意」は、既存の安全なリロケーション
パターンの再利用で対応可能と判断しており、新たな複雑さの追加ではない。*
