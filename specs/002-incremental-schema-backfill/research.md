# Phase 0 Research: 既存イベントへのスキーマ追加フィールドの段階的バックフィル

## 1. イベントデータバージョンの管理場所

- **Decision**: `scripts/utils.py` に新しい定数 `EVENT_DATA_VERSION`(int)を追加する。
  既存の `JSON_VERSION = "1.0"`(文字列、全ファイル種別共通のフォーマットバージョン)
  とは名前・型を明確に分け、混同を避ける。
- **Rationale**: `scripts/utils.py` は既に `JSON_VERSION` や `read_json`/`write_json` 等
  データ入出力の一元管理場所として使われており、`fetch/` 配下の全モジュールから
  import される既存の依存関係を再利用できる。新規モジュールを作ると
  import 経路が増え、「どこを見ればバージョン定義が分かるか」が分散する。
- **Alternatives considered**: 専用モジュール `scripts/schema_version.py` を新設する案 —
  却下。既存の `JSON_VERSION` の隣に置く方が発見しやすく、既存の
  `set_indent_num` 等のグローバル設定パターンとも一貫する。

## 2. `attr.json` 側のフィールド名

- **Decision**: `attr.json` に整数フィールド `event_data_version` を追加する。
  `write_event_attributes()` が呼ばれるたびに、その時点の `EVENT_DATA_VERSION` の値を
  書き込む。
- **Rationale**: 既存の `version`(文字列 `"1.0"`)と紛らわしくないよう、
  スネークケースで意味の異なる名前を明示する。
- **Alternatives considered**: 既存の `version` フィールドを流用し `"2.0"` のように
  上げていく案 — 却下。`version` は `standings.json`/`matches.json`/`seeds.json`/
  `tournaments.jsonl`/`users.jsonl` など全ファイル種別で共有される
  「JSON ファイル形式全体」のバージョンであり、「このイベントの attr.json が
  どの取得ロジック時点のものか」という今回の関心事とは軸が違う。混在させると、
  将来ファイル形式自体を変える際に判別できなくなる。

## 3. バックフィル対象の走査アルゴリズム(カーソル方式)

- **Decision**: 「イベントディレクトリの安定ソート順(パス文字列の昇順)」を1つの
  巡回リストとみなし、カーソル(直近まで走査したパスの位置)から開始して、
  `--max_events` 件処理するか、リストを一周し終えるまでスキャンを続ける
  「循環スキャン」方式を採用する。各ディレクトリについて `attr.json` の
  `event_data_version` を読み、目標バージョンより低ければ処理対象としてカウントし、
  既に最新なら読み飛ばして次に進む(API 呼び出しなし)。
- **Rationale**: `scripts/fetch/refresh_users.py` の `--cursor_path`/`--max_users` と
  同じ考え方を流用しつつ、「対象が動的に減っていく」(処理済みイベントは
  次回スキャンで対象から外れる)という違いに対応する。全ディレクトリを
  母数にした巡回にすることで、「1周しても対象が1件も見つからなかった」を
  そのまま FR-010 の「正常終了」条件として使える。対象のみを都度抽出した
  リストを母数にすると、リストが動的に縮む影響でカーソル位置の意味が
  実行ごとにズレる問題がある。
- **Alternatives considered**: 対象イベントだけを都度抽出してインデックス管理する案
  (`refresh_users.py` に近い) — 却下(上記の理由)。日付ディレクトリ順に
  `tournaments.jsonl` を走査する案 — 却下。イベント単位の一元的な走査には
  `pathlib.Path.rglob("attr.json")` によるディレクトリ直接走査の方が
  `scripts/fix/validate_data.py`/`find_empty_events.py` と一貫する。

## 4. カーソルの永続化場所

- **Decision**: `data/startgg/schema_backfill_cursor.txt` に、直近にスキャンを終えた
  イベントディレクトリのパス(1行、プレーンテキスト)を保存する。
- **Rationale**: `update_user.yml` が使う `data/startgg/users_refresh_cursor.txt` と
  同じ形式・同じディレクトリに置くことで、既存の運用(`chore-update` ブランチへの
  コミット対象に含める等)をそのまま踏襲できる。
- **Alternatives considered**: インデックス番号(int)を保存する案 — 却下。
  ディレクトリの集合はイベントの新規追加によって日次で変化するため、
  数値インデックスよりも「最後に見たパス」を保存する方が、リストの並び替えや
  新規イベント追加に対して頑健。

## 5. 新規スクリプトと既存スクリプトの関係

- **Decision**: 新規スクリプト `scripts/fetch/backfill_schema_version.py` を追加する。
  既存の `scripts/fix/backfill_events.py`(日付範囲・イベントIDリスト指定の
  手動一括再取得)や `data_force_refresh_backfill.yml`(`workflow_dispatch` の
  全項目強制再取得)は変更せず、そのまま残す。
- **Rationale**: 既存の2つは「人手による意図的な全量再取得」という別のユースケースを
  担っており、本機能の「バージョン差分のみを自動的・継続的に埋める」という
  ユースケースとは呼び出しパターンが異なる(対象の決め方、実行トリガー、
  バッチ処理の有無)。無理に1つのスクリプトに统合すると、
  引数の意味が「日付範囲」と「バージョン差分」で混在し複雑になる。
- **Alternatives considered**: `backfill_events.py` に `--only-outdated-version` の
  ようなフラグを追加する案 — 却下。既存スクリプトは `--token` 必須で
  `event_ids_file`/日付範囲どちらか起点の設計であり、「全イベントを
  ディレクトリ走査してバージョン比較する」という今回のスキャンモデルとは
  起点が異なるため、フラグ追加よりも新規スクリプトの方が単純。

## 6. スケジュールと同時実行制御

- **Decision**: 新規ワークフロー `.github/workflows/schema_backfill.yml` を追加し、
  `schedule: cron: "30 18 * * *"`(`update_tournament.yml`/`update_user.yml` と
  ずらした時刻で日次実行、初期値)+ `workflow_dispatch` を trigger とする。
  `concurrency.group: chore-update-branch` を共有し、`chore-update` ブランチへの
  同時書き込みを防ぐ。
- **Rationale**: 既存の日次更新ワークフロー群と同じ concurrency グループを
  共有することが FR-008 の直接的な実装であり、`cancel-in-progress: true` を
  引き継ぐことで、日次更新が優先実行中であれば本ワークフローは待機/
  キャンセルされ、ブランチ競合を構造的に防げる。
- **Alternatives considered**: 1時間毎の cron(`0 * * * *`) — 初期値としては
  過剰と判断し、日次を初期値としつつ `workflow_dispatch` で頻度を上げられる
  余地を残す(spec の Assumptions 参照、実測を踏まえ調整可能)。

## 7. 既存の `validate_data.py`(001）との関係

- **Decision**: 本機能は `event_data_version` の付与・巡回更新のみを担当し、
  `validate_data.py` 側のチェックロジック(`001-consolidate-validation-checks` の
  `guest_entrant_count` 等)には触れない。`guest_entrant_count` が
  `attr.json` に存在しない場合のフォールバック動作(001 の FR-015)は、
  本機能のバックフィルが完了するまでの間、引き続き機能する。
- **Rationale**: 2つの機能は独立してリリース可能であるべきで(001 は
  バージョンフィールドが無くても動作するようフォールバックを持つ)、
  依存順序を強制しない。

## Resolved unknowns

Technical Context の項目はすべて上記決定で確定し、NEEDS CLARIFICATION は残っていない。
