# Directory

## 全体構成（概観）
```
.
├── .github
│   ├── ISSUE_TEMPLATE
│   │   ├── bug_report.yml
│   │   ├── config.yml
│   │   └── data_error.yml
│   ├── workflows
│   │   ├── data_backfill.yml
│   │   ├── data_force_refresh_backfill.yml
│   │   ├── data_gap_check.yml
│   │   ├── prune_empty_events.yml
│   │   ├── schema_backfill.yml
│   │   ├── update_tournament.yml
│   │   └── update_user.yml
│   ├── dependabot.yml
│   └── pull_request_template.md
├── .claude
│   └── skills
├── .specify
├── docs
│   ├── chore-tournament
│   │   ├── README.md
│   │   └── checked_dates.json
│   ├── data_model.md
│   ├── directory.md
│   ├── fix.md
│   ├── flow.md
│   ├── github_actions.md
│   └── startgg_design.md
├── specs
│   └── {NNN}-{feature-name}
├── config
│   └── startgg
│       ├── excluded_events.json
│       └── label_rules.json
├── state
│   └── startgg
│       ├── done.csv
│       ├── done_events.csv
│       ├── schema_backfill_cursor.txt
│       ├── tournament_fetch_cursor_jp.txt
│       └── users_refresh_cursor.txt
├── data
│   └── startgg
│       ├── events
│       │   └── {Region}/{YYYY}/{MM}/{DD}/{Tournament}/{Event}
│       │       ├── attr.json
│       │       ├── matches.json
│       │       ├── seeds.json
│       │       └── standings.json
│       ├── tournaments.jsonl
│       ├── upcoming_tournaments.jsonl
│       └── users.jsonl
├── scripts
│   ├── __init__.py
│   ├── labeling.py
│   ├── queries.py
│   ├── utils.py
│   ├── fetch
│   │   ├── __init__.py
│   │   ├── download.py
│   │   ├── download_specific_event.py
│   │   ├── download_upcoming_tournaments.py
│   │   └── refresh_users.py
│   ├── check
│   │   ├── __init__.py
│   │   ├── diagnose_missing_tournament.py
│   │   ├── diagnose_stuck_sets.py
│   │   ├── find_empty_events.py
│   │   ├── find_events_missing_attr.py
│   │   ├── find_path_collisions.py
│   │   └── validate_data.py
│   ├── fix
│   │   ├── __init__.py
│   │   ├── apply_label_rules.py
│   │   ├── backfill_events.py
│   │   ├── backfill_schema_version.py
│   │   ├── backfill_tournament_index.py
│   │   ├── check_events_in_tournaments.py
│   │   ├── check_missing_attr_events.py
│   │   ├── fix_missing_tournaments.py
│   │   ├── fix_path_collision.py
│   │   ├── prune_empty_events.py
│   │   ├── prune_excluded_events.py
│   │   ├── redownload_event.py
│   │   ├── refresh_event_dir.py
│   │   └── update_chore_tournament_log.py
│   ├── merge
│   │   ├── __init__.py
│   │   ├── check_event_conflicts.py
│   │   └── resolve_merge_conflicts.py
│   ├── test
│   │   ├── __init__.py
│   │   └── test_*.py
│   └── event_analysis_prompt.txt
├── .mcp.json
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── SECURITY.md
└── requirements.txt
```

## 説明
- `.github/`: GitHub Actions のワークフロー、Dependabot 設定、Issue / Pull Request テンプレート。
- `.claude/`・`.specify/`: 開発支援ツール(Claude Code・Spec Kit)の設定とテンプレート。
- `docs/`: 仕様・運用・設計資料。`chore-tournament/` は GitHub Actions が確認した日付の記録。
- `specs/`: 機能ごとの仕様・計画・タスク(Spec Kit で作成)。
- `data/`: start.gg から取得した**公開データ**だけを置く(イベントごとのファイル・大会索引・未開催大会・選手)。
  各ファイルの形式は [data_model.md](data_model.md) を参照。
- `state/`: 取得処理の進捗(取得済みID・巡回カーソル)。スクリプトとワークフローが自動で更新する。公開データではない。
- `config/`: 人が編集する取得処理の設定(除外イベント・ラベル判定ルール)。公開データではない。
- `scripts/`: 取得・検証・補完のスクリプト群。置き場所は「データを書き換えるかどうか」で決める。
  - 直下: 共通ライブラリ(`utils.py`・`queries.py`・`labeling.py`)。単体では実行しない。
  - `fetch/`: start.gg から新しく取得して保存する。
  - `check/`: 調べて報告するだけで、データを**一切書き換えない**。
  - `fix/`: 既存のデータや記録を書き換えうる。`--apply` / `--yes` を付けたときだけ書き込むものと、実行するとすぐ書き込むものがあるため、実行前に `--help` を確認する。
  - `merge/`: `git merge` で起きたデータの競合を解消する補助。
  - `test/`: 上記のテスト。
- `requirements.txt`: Python の依存パッケージ。
