# Contract: トーナメント単位でのイベント作り直し検知(`scripts/fetch/backfill_tournament_events.py`)

## `iter_tournament_ids(tournaments) -> list[int]`

### 契約

- **FR-001 対応**: `read_tournaments_jsonl()` の戻り値(`tournament_id -> {..., "events": [...]}`)
  を受け取り、記録済みの全 `tournament_id` を安定ソート順(文字列化した ID の昇順など、
  実装は既存の `iter_event_dirs()` と同様パス文字列ソートに準じる)で返す。
- `events` が空配列のトーナメントも含む(Clarifications 参照)。

## `find_new_event_ids(tournament_id, game_id, recorded_event_ids) -> list[int]`

### 契約

- **FR-001 対応**: `fetch_event_ids_from_tournament(tournament_id, game_id)`
  (既存関数、`004` で `events is None` の場合 `FetchError` を送出するよう修正済み)を
  呼び出し、返された event_id のうち `recorded_event_ids`(そのトーナメントの
  `events[].event_id` の集合)に含まれないものだけを返す。
- `fetch_event_ids_from_tournament()` が `FetchError` を送出した場合(トーナメントが
  見つからない、対象ゲームのイベントが無い等)、呼び出し元に例外を伝播せず、空リストを
  返し、警告ログを出力する(スキャン全体を止めない)。

## `save_new_event(tournament_id, tournament_name, event_id, country_code, startgg_dir, tournaments) -> bool`

### 契約

- **FR-002 対応**: `event(id: $eventId)` を直接叩く `fetch_event_details(event_id)`
  (`backfill_schema_version.py` / `scripts/fix/redownload_event.py` と同一パターンで
  本ファイル内に定義)で詳細を取得し、`get_date_parts()` + `get_event_directory()` で
  ディレクトリを計算した上で、`download_standings()` → `download_seeds()` →
  `extend_user_info()` → `download_all_set()` → `write_event_attributes()` という
  既存の新規イベント取得と同一の手順で保存する。
- 保存後、`tournaments[tournament_id]["events"]` に新しいエントリ
  (`event_id`, `event_name`, `path`)を追加する。
- 取得に失敗した場合(`FetchError` 等)は `False` を返し、当該イベントをスキップして
  スキャンを継続する(例外は送出しない)。

## `run_tournament_event_sync(tournaments_root, tournament_file_path, cursor_path, users_file_path, game_id, max_tournaments) -> dict`

### 契約

- 戻り値: `{"tournaments_checked": int, "new_events_found": int, "wrapped_around": bool}`
- `002-incremental-schema-backfill` / `backfill_schema_version.py::run_backfill()` と
  同じカーソル永続化・循環スキャンパターンに従う(パスの代わりに `tournament_id` を
  カーソル値として保存する)。
- 変更があった場合(新規イベントを1件以上保存した場合)のみ `tournaments.jsonl` を
  `write_jsonl()` で書き戻す。変更が無い場合はファイルに触れない。
