# Contract: attr.json欠落イベントの発見と復元(`scripts/fetch/backfill_schema_version.py`)

## `iter_event_dirs()`

### 契約

- **FR-005 対応**: 戻り値は「`standings.json` を持つディレクトリ」の一覧(Japan優先ソートは
  維持)。従来の「`attr.json` を持つディレクトリ」の一覧より広い集合を返す
  (`attr.json` の有無を問わない)。
- 戻り値の型・呼び出し元(`run_backfill()`)のインターフェースは変更しない。

## `backfill_one_event()`

### 変更前のシグネチャ

```python
def backfill_one_event(event_dir, users, users_file_path) -> bool
```

### 変更後のシグネチャ

```python
def backfill_one_event(event_dir, users, users_file_path, tournaments=None) -> bool
```

- `tournaments`: `read_tournaments_jsonl()` の戻り値と同じ形式の辞書(`tournament_id -> {..., "events": [...]}`)。
  省略時(`None`)は `tournaments.jsonl` からの `event_id` 復元を行わない(呼び出し元の
  後方互換性のため)。

### 契約

- **FR-006 対応**: `event_dir/attr.json` が存在しない、または読み込めない、または
  `event_id` を含まない場合:
  1. `tournaments` が渡されていれば、各エントリの `events[]` を走査し、`path` が
     `str(event_dir)` と一致するものを探す。
  2. 見つかった場合、そのエントリの `event_id` を使って以降の再取得処理(`fetch_event_details`
     以降)を続行する。
  3. 見つからなかった場合(または `tournaments` が渡されていない場合)、
     `[UNRESOLVED] {event_dir}: event_id を特定できません` を標準エラー出力へ出力し、
     `False` を返す(呼び出し元の走査は継続する ── 例外は送出しない)。
- 上記以外の既存の契約(`event_id` が判明した以降の取得・書き込みフロー、
  戻り値 `True`/`False` の意味)は変更しない。

## `run_backfill()` のサマリー

### 契約

- 戻り値の辞書に `unresolved`(int)キーを追加する: `{"processed": int, "skipped": int,
  "wrapped_around": bool, "unresolved": int}`。
- `unresolved` は、`backfill_one_event()` が event_id を特定できず `[UNRESOLVED]` として
  スキップした件数(このバックフィル実行中の累計)。
- 既存の3キー(`processed`, `skipped`, `wrapped_around`)の意味・計算方法は変更しない。
  既存テスト(`test_no_eligible_events_exits_cleanly` 等)が辞書の完全一致を検証している
  箇所は、新キー追加に合わせて更新する。
