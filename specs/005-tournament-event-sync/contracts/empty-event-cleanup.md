# Contract: 空イベントディレクトリの整理(`scripts/fix/prune_empty_events.py`)

## `count_data_entries(path) -> int`

### 契約

- 指定された JSON ファイル(`{"data": [...]}` 形式)の `data` 配列の要素数を返す。
- ファイルが存在しない、または読み込めない(壊れている)場合は `0` を返す(例外を
  送出しない)。既存の `scripts/fix/redownload_event.py::count_data_entries()` と
  同一の契約。

## `is_empty_event(event_dir) -> bool`

### 契約

- **FR-003 対応**: `count_data_entries(event_dir / "standings.json") == 0` かつ
  `count_data_entries(event_dir / "matches.json") == 0` の場合に `True` を返す。
- `seeds.json` / `attr.json` の中身は判定に使わない(Assumptions 参照)。
- **FR-005 対応**: どちらか一方でも1件以上のデータを持つ場合は `False` を返す
  (削除対象にならない)。

## `find_empty_event_dirs(events_root) -> list[Path]`

### 契約

- `events_root` 以下の、`standings.json` または `matches.json` を持つ全ディレクトリ
  (`002-incremental-schema-backfill` / `004-fix-duplicate-events` の
  `iter_event_dirs()` と同様の走査対象)のうち、`is_empty_event()` が `True` を
  返すものの一覧を返す。
- カーソル永続化は行わない(`research.md` 論点5参照、API呼び出しを伴わないため)。

## `prune_empty_events(events_root, tournament_file_path, apply) -> dict`

### 契約

- 戻り値: `{"found": int, "deleted": int, "deleted_paths": list[str]}`
- **FR-004 対応**: `apply=True` の場合、`find_empty_event_dirs()` で見つかった各
  ディレクトリを `shutil.rmtree()` で削除し、`tournaments.jsonl` を読み込んで
  該当する `path` を持つイベントエントリを全トーナメントから取り除いた上で、
  `write_jsonl()` で1回だけ書き戻す。
- `apply=False`(デフォルト)の場合、削除対象を報告するのみで、ファイルシステム・
  `tournaments.jsonl` のどちらも変更しない(`scripts/fix/redownload_event.py` の
  `--yes` フラグと同じ dry-run デフォルトのパターンを踏襲する)。
- **FR-005 対応**: `is_empty_event()` が `False` と判定したディレクトリは
  `find_empty_event_dirs()` の結果に含まれないため、削除処理の対象にすらならない。
