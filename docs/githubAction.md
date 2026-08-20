# GitHub Actions

## 概要
- 定期実行される更新系ワークフロー(`update_tournament.yml` / `update_user.yml` /
  `schema_backfill.yml` / `prune_empty_events.yml`)は、差分があれば `main` ブランチへ
  **直接** commit / push する(中間ブランチや PR は経由しない)。
  複数ワークフローが同時に `main` へ push しうるため、`concurrency: group: main-data-commits`
  で直列化し、push が競合した場合は `git pull --rebase origin main` してリトライする。
  (旧: `chore-update` ブランチへ集約し PR 経由の rebase auto-merge で `main` に反映していたが、
  `main` への直接コミットが `chore-update` ベースの自動化から見えず、古い状態のまま処理が
  継続する実害が確認されたため廃止した。詳細は憲法 Principle IV を参照。)
- `data_backfill.yml` / `data_force_refresh_backfill.yml` / `data_gap_check.yml` /
  `fetch_large_event.yml` は上記とは別系統で、実行ごとに専用ブランチを作成し `main` への
  PR を経由するパターンを引き続き使う(大規模・破壊的になりうる手動実行のため、レビューを
  挟む設計を意図的に維持している)。
- 大会データの取得状況は `docs/chore-tornament/README.md` に日付単位で記録する。
- 記録対象の日付範囲は `2018-12-29` から当日まで。

## ワークフロー

### `update_tournament.yml`
- 定義ファイル: `.github/workflows/update_tournament.yml`
- 実行タイミング:
  - `schedule`: 毎日 `18:00 UTC` = 毎日 `03:00 JST`
  - `workflow_dispatch`
- 実行内容:
  - `scripts/fetch/download.py` を日本 (`JP`) 向けに当日・前日分で実行
  - `python -m unittest scripts.test.test_validate_data` を実行
  - `scripts/fix/update_chore_tournament_log.py` で `docs/chore-tornament/` を更新
  - 差分があれば `main` ブランチへ直接 push

### `update_user.yml`
- 定義ファイル: `.github/workflows/update_user.yml`
- 実行タイミング:
  - `schedule`: 毎日 `18:05 UTC` = 毎日 `03:05 JST`
  - `workflow_dispatch`
- 実行内容:
  - `scripts/fetch/refresh_users.py --max_users 300` を実行
  - 差分があれば `main` ブランチへ直接 push

### `data_backfill.yml`
- 定義ファイル: `.github/workflows/data_backfill.yml`
- 実行タイミング:
  - `workflow_dispatch`
- 入力:
  - `start_date`
  - `end_date`
  - `country_code`
- 実行内容:
  - 指定期間で `scripts/fetch/download.py` を実行
  - `python -m unittest scripts.test.test_validate_data` を実行
  - 指定期間を `scripts/fix/update_chore_tournament_log.py` に記録
  - 差分があれば `chore-update` ブランチへ直接 push

### `data_monthly_check.yml`
- 定義ファイル: `.github/workflows/data_monthly_check.yml`
- 実行タイミング:
  - `schedule`: 毎日 `18:10 UTC` = 毎日 `03:10 JST`
  - `workflow_dispatch`
- 実行内容:
  - `scripts/fix/check_events_in_tournaments.py --apply` を実行
  - `scripts/fix/update_chore_tournament_log.py` を実行して記録表を再生成
  - 差分があれば `chore-update` ブランチへ直接 push
  - `check_events_in_tournaments.py` が失敗した場合は workflow 全体も失敗にする

### `schema_backfill.yml`
- 定義ファイル: `.github/workflows/schema_backfill.yml`
- 実行タイミング:
  - `schedule`: 毎時30分(`cron: "30 * * * *"`)
  - `workflow_dispatch`(`max_events` 入力で1回あたりの処理件数を上書き可能)
- 実行内容:
  - `scripts/fetch/backfill_schema_version.py` を実行し、`attr.json` の
    `event_data_version`(`scripts/utils.py` の `EVENT_DATA_VERSION`)が古い既存イベントを
    安定ソート順で循環スキャンし、`schema_backfill_cursor.txt` に保存されたカーソルの
    続きから、1回につき `--max_events`(既定200件)まで再取得する
  - `python -m unittest scripts.test.test_validate_data` /
    `scripts.test.test_backfill_schema_version` を実行
  - 差分があれば `main` ブランチへ直接 push(バッチごとに commit / push を繰り返す)

### `prune_empty_events.yml`
- 定義ファイル: `.github/workflows/prune_empty_events.yml`
- 実行タイミング:
  - `schedule`: 毎週日曜 `12:00 UTC`(`cron: "0 12 * * 0"`)
  - `workflow_dispatch`
- 実行内容:
  - `python -m unittest scripts.test.test_validate_data` /
    `scripts.test.test_prune_empty_events` を実行
  - `scripts/fix/prune_empty_events.py --apply` を実行し、`standings.json` /
    `matches.json` が空のイベントディレクトリを、start.gg への再確認を経てから削除する
  - 差分があれば `main` ブランチへ直接 push

## 手動実行と定期実行の挙動

- `update_tournament.yml`
  - `schedule` の場合: 毎日 `03:00 JST` に起動し、その日の JST 日付と前日の JST 日付を対象に大会データ取得を行う。
  - `workflow_dispatch` の場合: 実行した時点ですぐ起動し、同じく実行日の JST 日付と前日の JST 日付を対象に大会データ取得を行う。

- `update_user.yml`
  - `schedule` の場合: 毎日 `03:05 JST` に起動し、`users_refresh_cursor.txt` を使ってユーザー更新を継続する。
  - `workflow_dispatch` の場合: 実行した時点ですぐ起動し、同じ処理をその場で実行する。

- `data_backfill.yml`
  - `schedule` はない。
  - `workflow_dispatch` の場合のみ起動し、指定した `start_date` から `end_date` の範囲を取得して、その範囲を `docs/chore-tornament` に記録する。

- `data_monthly_check.yml`
  - `schedule` の場合: 毎日 `03:10 JST` に起動し、`tournaments.jsonl` の補正と `docs/chore-tornament` の再生成を行う。
  - `workflow_dispatch` の場合: 実行した時点ですぐ起動し、同じ補正処理と再生成をその場で実行する。

- `schema_backfill.yml`
  - `schedule` の場合: 毎時30分に起動し、`schema_backfill_cursor.txt` を使って
    `event_data_version` が古いイベントのバックフィルを継続する。
  - `workflow_dispatch` の場合: 実行した時点ですぐ起動し、同じ処理をその場で実行する
    (`max_events` 入力で1回あたりの処理件数を上書き可能)。

- `prune_empty_events.yml`
  - `schedule` の場合: 毎週日曜 `21:00 JST`(`12:00 UTC`)に起動する。
  - `workflow_dispatch` の場合: 実行した時点ですぐ起動する。

- 共通挙動
  - `update_tournament.yml` / `update_user.yml` / `schema_backfill.yml` /
    `prune_empty_events.yml` は `main` を checkout し、差分がある場合のみ `main` へ
    直接 commit / push する(PR は経由しない)。
  - 同時に `main` へ push しうるため `concurrency: group: main-data-commits` で
    直列化し、push 競合時は `git pull --rebase origin main` してリトライする。
  - `schedule` は GitHub Actions の仕様上、デフォルトブランチ上の workflow 定義を元に起動される。

## `docs/chore-tornament`

### 生成ファイル
- `docs/chore-tornament/README.md`
  - `2018-12-29` から当日までを 1 日 1 行の Markdown テーブルで出力する。
  - `data/startgg/events/Japan/YYYY/MM/DD` のフォルダ有無を `Folder Exists` に記録する。
  - GitHub Actions がその日付を取得対象として処理した場合、`Checked By GitHub Actions` / `Last Checked At (JST)` / `Workflow` を更新する。
- `docs/chore-tornament/checked_dates.json`
  - Markdown 生成用の記録データを保持する。

### 更新スクリプト
- `scripts/fix/update_chore_tournament_log.py`
  - `--mark-start` と `--mark-end` で、GitHub Actions が確認した日付範囲を記録する。
  - 指定がない場合は、既存記録を維持したままテーブルだけ再生成する。

## 実際に使うシークレット
- `STARTGG_TOKEN`
