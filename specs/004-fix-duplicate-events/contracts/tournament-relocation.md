# Contract: 大会延期の検知とディレクトリ統合(`scripts/fetch/download.py`)

`download_all_tournaments()` / `should_skip_tournament()` の呼び出し元(既存の
`data_backfill.yml` / `update_tournament.yml` 等)に対する振る舞いの契約。

## `should_skip_tournament()`

### 変更前のシグネチャ

```python
def should_skip_tournament(tournament_id, tournaments, done_tournaments, force_refresh) -> bool
```

### 変更後のシグネチャ

```python
def should_skip_tournament(tournament_id, tournaments, done_tournaments, force_refresh, current_date_parts=None) -> bool
```

- `current_date_parts`: `(year, month, day)` のタプル(`get_date_parts()` の戻り値と同じ形式)。
  呼び出し元は、そのループで処理中の大会の最新 `startAt` から計算した値を渡す。
- 後方互換性: `current_date_parts` はキーワード引数でデフォルト `None`。`None` の場合は
  従来通りの判定(ファイル存在ベースの完了判定のみ)を行う ── 呼び出しテストが日付比較を
  意図的に検証しない場合の互換性を保つため。

### 契約

- **FR-001, FR-003 対応**: `force_refresh=False` かつ `tournament_id` が `done_tournaments`
  に含まれ、かつ `tournaments[tournament_id]` の記録上のイベントファイルが全て揃っている
  (`tournament_events_complete()` が `True`)場合でも、`current_date_parts` が指定されて
  おり、記録済みのいずれかのイベントパスが `current_date_parts` から導かれる
  `/{year}/{month}/{day}/` を含まない場合は `False`(スキップしない)を返す。
- それ以外の場合の判定基準は変更前と同一。

## `download_all_tournaments()` のイベント記録更新

### 契約

- **FR-001, FR-002, FR-003 対応**: 各イベントの処理後(`matches_only=False` の通常経路で
  `write_event_attributes()` が呼ばれた後)、`tournaments[tournament_id]["events"]` 内に
  同じ `event_id` を持つ既存エントリがある場合:
  - 既存エントリの `path` が今回計算した `event_dir` と同じ場合 → 何もしない(従来通り)。
  - 異なる場合 → `event_files_complete(event_dir)` が `True` であることを確認した上で、
    既存エントリの `path` を `event_dir` に更新し、`rewrite_tournaments` を `True` にする。
    さらに、旧 `path` がディスク上に存在し、かつ新しい `event_dir` と異なる場合は
    `shutil.rmtree(旧path)` で削除する。
  - `event_files_complete(event_dir)` が `False` の場合(このイベントの取得が今回も
    最後まで完了しなかった場合)は、`path` の更新・旧ディレクトリの削除のどちらも行わない
    (次回実行時に再試行される)。
  - 既存エントリが無い場合 → 従来通り新規追加する(`matches_only` の場合は追加しない、
    という既存の挙動も維持)。
- 旧ディレクトリの削除は `matches_only=True` の経路では行わない(`write_event_attributes()`
  自体が呼ばれず `attr.json` が書かれないため、統合の起点にできない)。

### 呼び出し例(擬似コード)

```python
year, month, day = get_date_parts(timestamp)
if should_skip_tournament(tournament_id, tournaments, done_tournaments, force_refresh,
                           current_date_parts=(year, month, day)):
    continue
```
