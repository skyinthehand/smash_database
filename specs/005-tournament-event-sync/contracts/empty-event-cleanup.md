# Contract: 空イベントディレクトリの整理(`scripts/fix/prune_empty_events.py`)

**2026-08-18 改訂**: 実データ運用で「ローカルが空 = 削除して安全」という前提が誤って
いたことが判明した(187-7-23verで実データを持つディレクトリを誤削除)。削除前に
start.gg への再確認を必須とする設計に改めた。

## `count_data_entries(path) -> int`

### 契約

- 指定された JSON ファイル(`{"data": [...]}` 形式)の `data` 配列の要素数を返す。
- ファイルが存在しない、または読み込めない(壊れている)場合は `0` を返す(例外を
  送出しない)。

## `is_empty_event(event_dir) -> bool`

### 契約

- **FR-001 対応**: `count_data_entries(event_dir / "standings.json") == 0` かつ
  `count_data_entries(event_dir / "matches.json") == 0` の場合に `True` を返す。
- `seeds.json` / `attr.json` の中身は判定に使わない。
- あくまで**削除候補の一次選別**であり、この結果だけで削除してはならない。

## `find_empty_event_dirs(events_root) -> list[Path]`

### 契約

- `events_root` 以下の、`standings.json` または `matches.json` を持つ全ディレクトリの
  うち、`is_empty_event()` が `True` を返すものの一覧(削除候補)を返す。

## `resolve_event_id(event_dir, tournaments) -> int | None`

### 契約

- `attr.json` から `event_id` を読む。読めない/存在しない場合は `tournaments.jsonl`
  の記録(`events[].path == str(event_dir)`)から復元する。どちらでも特定できない
  場合は `None` を返す。

## `resolve_tournament_id(event_id, event_dir, tournaments) -> int | None`

### 契約

- `tournaments.jsonl` の記録から、`path` または `event_id` が一致するエントリの
  `tournament_id` を返す。見つからない場合は `None`。

## `has_unrecorded_sibling_event(tournament_id, game_id, tournaments) -> bool | None`

### 契約

- `fetch_event_ids_from_tournament(tournament_id, game_id)`(既存関数)を呼び出し、
  `tournaments.jsonl` に未記録の event_id が含まれるかどうかを返す。
- `NoEventsForGameError`(GraphQLの`errors`を伴わずeventsがnullだった場合。
  クエリ自体は正常完了した上で対象ゲームのイベントが0件だったことを表す)を捕捉した
  場合は `False`(兄弟イベント無しと確定)を返す。
- それ以外の `FetchError`(通信エラー・トーナメント自体が見つからない・GraphQLの
  `errors`を伴う場合など、確認そのものができなかった場合)を捕捉した場合は、
  確認不能を表す `None` を返す。呼び出し元はこれを「安全側に倒して削除しない」として
  扱うこと。

## `reconcile_empty_event(event_dir, tournaments, users, users_file_path, game_id) -> str`

### 契約

- **FR-002/FR-003 対応**: 次の順で確認し、`"healed"` | `"deleted"` | `"kept"` の
  いずれかを返す。
  1. `event_id` を特定できない場合 → `"kept"`(削除しない)。
  2. `backfill_one_event()`(`scripts/fetch/backfill_schema_version.py` の既存関数、
     `event(id: $eventId)` を直接叩く経路で再取得)を呼ぶ。再取得後に
     `is_empty_event()` が `False` になった場合(実データが見つかった)→
     `"healed"`(保存済み、削除しない)。
  3. まだ空で `tournament_id` を特定できない場合 → `"kept"`。
  4. `has_unrecorded_sibling_event()` が `None`(確認不能)または `True`(未記録の
     他イベントあり)の場合 → `"kept"`(削除しない)。
  5. 上記いずれにも該当せず(再取得後も空、かつ同トーナメント配下に他のイベントも
     無いことを確認できた場合)のみ → ディレクトリを削除し `"deleted"`。
- 削除は、ローカルの空判定だけでなく、start.gg 側で今も空であることと、
  同トーナメント配下に見逃している別イベントが無いことの両方を確認できた場合に
  限る。

## `prune_empty_events(events_root, tournament_file_path, users_file_path, game_id, apply) -> dict`

### 契約

- 戻り値: `{"found": int, "healed": int, "deleted": int, "kept": int, "deleted_paths": list[str]}`
- `apply=False`(デフォルト)の場合、`find_empty_event_dirs()` の件数を報告するのみで、
  API呼び出し・ファイルシステム・`tournaments.jsonl` のいずれも変更しない
  (`scripts/fix/redownload_event.py` の `--yes` フラグと同じ dry-run デフォルトの
  パターンを踏襲する)。
- `apply=True` の場合、各候補について `reconcile_empty_event()` を呼び、
  `"deleted"` になったものについてのみ `shutil.rmtree()` で削除し、
  `tournaments.jsonl` から対応するイベント記録を取り除く。`"healed"`/`"deleted"`
  が1件でもあれば `tournaments.jsonl` を `write_jsonl()` で1回だけ書き戻す
  (`"kept"` のみの場合は書き戻さない)。
