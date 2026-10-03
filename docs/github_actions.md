# GitHub Actions

## 概要
ワークフローは、`main` に直接 push する**定期更新系**と、ブランチ上で動かす**手動実行系**の2系統に分かれる。

| ワークフロー | 起動 | 主な処理 | 書き込み先 |
| --- | --- | --- | --- |
| `update_tournament.yml` | 毎日 03:00 JST / 手動 | 日本の大会を取得、未開催大会一覧を更新 | `main` に直接 push |
| `update_user.yml` | 毎日 03:05 JST / 手動 | 選手情報を300件ずつ巡回更新 | `main` に直接 push |
| `schema_backfill.yml` | 毎時30分 / 手動 | 古い形式のイベントを再取得 | `main` に直接 push |
| `prune_empty_events.yml` | 毎週日曜 21:00 JST / 手動 | 中身が空のイベントを削除 | `main` に直接 push |
| `data_backfill.yml` | 手動のみ | 指定期間の大会を取得 | 指定ブランチに push |
| `data_force_refresh_backfill.yml` | 手動のみ | 指定期間の大会を強制的に再取得 | 指定ブランチに push |
| `data_gap_check.yml` | 手動のみ | 直近の取りこぼしを検出して取得 | 専用ブランチに push し PR を作成 |

- **定期更新系**(上の4つ)は `main` を checkout し、差分があれば `main` へ**直接** commit / push する(中間ブランチや PR は経由しない)。
  複数のワークフローが同時に `main` へ push しうるため、`concurrency: group: main-data-commits` で直列化し、push が競合した場合は `git pull --rebase origin main` してリトライする。
  (旧: `chore-update` ブランチへ集約し、PR 経由の rebase auto-merge で `main` に反映していた。`main` への直接コミットが `chore-update` ベースの自動化から見えず、古い状態のまま処理が継続する実害が確認されたため廃止した。詳細は憲法 Principle IV を参照。)
- **手動実行系**(下の3つ)は、大規模・破壊的になりうるため `main` へ直接は書き込まない。
- `schedule` は GitHub Actions の仕様上、デフォルトブランチ(`main`)上のワークフロー定義を元に起動される。
- 取得処理の進捗(取得済みID・巡回カーソル)は `state/startgg/`、人が編集する設定(除外イベント・ラベル判定ルール)は `config/startgg/` にある。
- 大会データの取得状況は `docs/chore-tournament/README.md` に日付単位で記録する。記録対象の日付範囲は `2018-12-29` から当日まで。
- 使うシークレットは `STARTGG_TOKEN` のみ。`data_gap_check.yml` の PR 作成には、自動で発行される `GITHUB_TOKEN` を使う。

### 廃止したワークフロー
- `fetch_large_event.yml`: 大規模イベントが一括取得の上限を超えて失敗した場合の専用リカバリ手段だった。`scripts/fetch/download.py` が一括取得の失敗を検知して自動的に逐次(set 単位)取得へフォールバックし、実行回をまたいで再開できるようになったため削除した。
- `data_monthly_check.yml`: `scripts/fix/check_events_in_tournaments.py --apply` による `tournaments.jsonl` の補正を毎日行っていた。現在は存在しない。

## 定期更新系

### `update_tournament.yml`
- 起動: `schedule` 毎日 `18:00 UTC`(= `03:00 JST`)、`workflow_dispatch`
- 処理:
  1. `scripts/fetch/download.py --country_code JP --finish_date <カーソル>` で、カーソルの日付から当日までの日本の大会を取得する。
     カーソルは `state/startgg/tournament_fetch_cursor_jp.txt`。ファイルがなければ前日(JST)から取得する。
  2. 取得が1件も取りこぼしなく終わった場合(ログの `incomplete_count=0`)だけ、カーソルを前日(JST)に進める。
     1件でも未完了があればカーソルは進めず、次回も同じ区間を再走査する。
  3. `scripts/fetch/download_upcoming_tournaments.py --country_code JP` で、未開催大会の一覧(`data/startgg/upcoming_tournaments.jsonl`)を作り直す。
  4. `python -m unittest scripts.test.test_validate_data` を実行する。
  5. `scripts/fix/update_chore_tournament_log.py` で `docs/chore-tournament/` を更新する。
  6. 差分があれば `main` へ直接 push する。

### `update_user.yml`
- 起動: `schedule` 毎日 `18:05 UTC`(= `03:05 JST`)、`workflow_dispatch`
- 処理:
  1. `scripts/fetch/refresh_users.py --max_users 300` で、`data/startgg/users.jsonl` の選手情報を300件ずつ更新する。
     続きの位置は `state/startgg/users_refresh_cursor.txt` に保存する。
  2. 差分があれば `main` へ直接 push する。

### `schema_backfill.yml`
- 起動: `schedule` 毎時30分(`cron: "30 * * * *"`)、`workflow_dispatch`(入力 `max_events`: 1回の処理件数、`batch_size`: 1コミットあたりの件数)
- 処理:
  1. `python -m unittest scripts.test.test_validate_data` / `scripts.test.test_backfill_schema_version` を実行する。
  2. `scripts/fix/backfill_schema_version.py` を実行し、`attr.json` の `event_data_version`(`scripts/utils.py` の `EVENT_DATA_VERSION`)が古い既存イベントを再取得する。
     日本リージョンを優先し、各リージョン内は日付が新しい順(直近のイベントを優先)に循環スキャンする。
     `state/startgg/schema_backfill_cursor.txt` に保存したカーソルの続きから、1回につき `--max_events`(既定200件)まで処理する。
     (直近優先のトレードオフ: バージョンアップが1周にかかる時間より頻繁に起きると、2018年頃などの最も古いイベント群は毎回後回しになり続ける。)
  3. バッチごとに `main` へ直接 commit / push を繰り返す。

### `prune_empty_events.yml`
- 起動: `schedule` 毎週日曜 `12:00 UTC`(= `21:00 JST`、`cron: "0 12 * * 0"`)、`workflow_dispatch`
- 処理:
  1. `python -m unittest scripts.test.test_validate_data` / `scripts.test.test_prune_empty_events` を実行する。
  2. `scripts/fix/prune_empty_events.py --apply` で、`standings.json` / `matches.json` が空のイベントディレクトリを、start.gg への再確認を経てから削除する。
  3. 差分があれば `main` へ直接 push する。

## 手動実行系

### `data_backfill.yml`
- 起動: `workflow_dispatch` のみ
- 入力: `start_date`(この日付まで)、`end_date`(この日付から)、`country_code`、`target_branch`(書き込み先。省略時は実行時に選んだブランチ)
- 処理:
  1. 指定期間で `scripts/fetch/download.py` を実行する。
  2. `python -m unittest scripts.test.test_utils` / `scripts.test.test_validate_data` を実行する。
  3. 指定期間を `scripts/fix/update_chore_tournament_log.py` で記録する。
  4. 差分があれば `target_branch` へ push する。PR は作らない。

### `data_force_refresh_backfill.yml`
- 起動: `workflow_dispatch` のみ
- 入力: `data_backfill.yml` と同じ入力に加えて、`matches_only`(既存イベントの `matches.json` だけを再取得する)
- 処理:
  1. 指定期間で `scripts/fetch/download.py --force_refresh` を実行し、取得済みの大会も取り直す。
  2. `python -m unittest scripts.test.test_utils` / `scripts.test.test_validate_data` / `scripts.test.test_download` を実行する。
  3. 指定期間を `scripts/fix/update_chore_tournament_log.py` で記録する。
  4. 差分があれば `target_branch` へ push する。PR は作らない。

### `data_gap_check.yml`
- 起動: `workflow_dispatch` のみ
- 入力: `since_days_ago`(何日前から走査するか。通常は60)
- 処理:
  1. 最新の `main` から `gap-check/<当日のJST日付>` ブランチを作る。
  2. 指定日数前から当日までの日本の大会を、期間を区切りながら `scripts/fetch/download.py` で取得する。区切りごとに `test_validate_data` を実行し、commit / push する。
  3. 新たに取得できた大会(取りこぼし)の一覧をレポートにまとめる。
  4. `scripts/fix/update_chore_tournament_log.py` で記録を更新する。
  5. 取りこぼしがあった場合だけ、`main` 向けの PR を `gh pr create` で作る。

## `docs/chore-tournament`

### 生成ファイル
- `docs/chore-tournament/README.md`
  - `2018-12-29` から当日までを 1 日 1 行の Markdown テーブルで出力する。
  - `data/startgg/events/Japan/YYYY/MM/DD` のフォルダ有無を `Folder Exists` に記録する。
  - GitHub Actions がその日付を取得対象として処理した場合、`Checked By GitHub Actions` / `Last Checked At (JST)` / `Workflow` を更新する。
- `docs/chore-tournament/checked_dates.json`
  - Markdown 生成用の記録データを保持する。

### 更新スクリプト
- `scripts/fix/update_chore_tournament_log.py`
  - `--mark-start` と `--mark-end` で、GitHub Actions が確認した日付範囲を記録する。
  - 指定がない場合は、既存記録を維持したままテーブルだけ再生成する。
