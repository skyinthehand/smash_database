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
│   ├── githubAction.md
│   └── startgg_design.md
├── specs
│   └── {NNN}-{feature-name}
├── data
│   └── startgg
│       ├── done.csv
│       ├── done_events.csv
│       ├── excluded_events.json
│       ├── label_rules.json
│       ├── schema_backfill_cursor.txt
│       ├── tournament_fetch_cursor_jp.txt
│       ├── users_refresh_cursor.txt
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
│   ├── fetch
│   │   ├── __init__.py
│   │   ├── backfill_schema_version.py
│   │   ├── download.py
│   │   ├── download_specific_event.py
│   │   ├── download_upcoming_tournaments.py
│   │   ├── refresh_event_dir.py
│   │   └── refresh_users.py
│   ├── fix
│   │   ├── __init__.py
│   │   ├── apply_label_rules.py
│   │   ├── backfill_events.py
│   │   ├── backfill_tournament_index.py
│   │   ├── check_events_in_tournaments.py
│   │   ├── check_missing_attr_events.py
│   │   ├── diagnose_missing_tournament.py
│   │   ├── diagnose_stuck_sets.py
│   │   ├── find_empty_events.py
│   │   ├── find_events_missing_attr.py
│   │   ├── find_path_collisions.py
│   │   ├── fix_missing_tournaments.py
│   │   ├── fix_path_collision.py
│   │   ├── prune_empty_events.py
│   │   ├── prune_excluded_events.py
│   │   ├── redownload_event.py
│   │   ├── update_chore_tournament_log.py
│   │   └── validate_data.py
│   ├── test
│   │   ├── __init__.py
│   │   └── test_*.py
│   ├── check_event_conflicts.py
│   ├── event_analysis_prompt.txt
│   ├── labeling.py
│   ├── queries.py
│   ├── resolve_merge_conflicts.py
│   ├── storeJson.py
│   └── utils.py
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
- `data/`: start.gg から取得したデータと、取得処理の管理用ファイル(取得済みID・巡回カーソル・除外設定・ラベル判定ルール)。
  各ファイルの形式は [data_model.md](data_model.md) を参照。
- `scripts/`: 取得(`fetch/`)・検証と補完(`fix/`)のスクリプト群と、そのテスト(`test/`)。
- `requirements.txt`: Python の依存パッケージ。
