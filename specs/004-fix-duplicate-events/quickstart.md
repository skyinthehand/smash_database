# Quickstart: 大会延期による重複イベントディレクトリとattr.json欠落の解消

実装後、以下の手順でこの機能がエンドツーエンドで動作することを確認できる。

## 前提

- `scripts/fetch/download.py` の `should_skip_tournament()` が延期検知
  (`current_date_parts`)に対応済み、`download_all_tournaments()` がイベント記録の
  パス更新・旧ディレクトリ削除に対応済み。
- `scripts/fetch/backfill_schema_version.py` の `iter_event_dirs()` が
  `standings.json` ベースの発見に対応済み、`backfill_one_event()` が
  `tournaments.jsonl` からの `event_id` 復元に対応済み。

## 1. 単体テストを実行する

```bash
python -m unittest scripts.test.test_download
python -m unittest scripts.test.test_backfill_schema_version
python -m unittest scripts.test.test_validate_data   # 既存テストが壊れていないことも確認
```

期待結果: 全てパスする。特に以下がカバーされていること
([contracts/tournament-relocation.md](./contracts/tournament-relocation.md) /
[contracts/backfill-discovery.md](./contracts/backfill-discovery.md) 参照):

- 記録済みの開催日と現在の `startAt` から計算した開催日が異なる場合、`should_skip_tournament()`
  が `False`(スキップしない)を返す。
- 再取得によりイベントの保存先パスが変わり、新パスの必須ファイルが揃った場合、旧ディレクトリが
  削除され、`tournaments.jsonl` の記録パスが新パスに更新される。
- 新パスの必須ファイルが揃わなかった場合、旧ディレクトリは削除されない。
- `attr.json` を持たないが `standings.json` を持つディレクトリが `iter_event_dirs()` の
  結果に含まれる。
- `attr.json` が読めないイベントディレクトリでも、`tournaments.jsonl` に一致するパスの
  記録があれば `event_id` が復元され再取得が行われる。一致が無い場合は `[UNRESOLVED]` として
  報告され、処理全体は継続する。

## 2. 第7回チバスマ交流会の重複解消を確認する(実データでの検証)

修正適用前:

```bash
find data/startgg/events/Japan -path "*第7回チバスマ交流会*" -maxdepth 6 -type d
```

→ `2025/08/16/...` と `2026/02/07/...` の2件が表示される。

`STARTGG_TOKEN` が利用可能な環境で、tournament_id=811466 を含む範囲の再取得を実行する
(通常運用の日次更新 `update_tournament.yml` 相当、または):

```bash
python3 scripts/fetch/download.py --token "$STARTGG_TOKEN" \
  --country_code JP --finish_date <2026-02-07以前の適当な日付>
```

修正適用後、再度確認:

```bash
find data/startgg/events/Japan -path "*第7回チバスマ交流会*" -maxdepth 6 -type d
```

確認ポイント:

- 結果が `2026/02/07/...` の1件のみになっていること(`2025/08/16/...` は削除されている)。
- `2026/02/07/.../attr.json` が存在し、`event_id: 1423946` を含むこと。
- `data/startgg/tournaments.jsonl` 内の `tournament_id: 811466` エントリの `events[0].path`
  が `2026/02/07/...` を指していること。

**未実施(本セッションのサンドボックス環境には実際の `STARTGG_TOKEN` / start.gg への実
ネットワークアクセスが無いため実行不可)**: マージ前またはマージ後、実環境(ローカル or
GitHub Actions の `workflow_dispatch` 手動実行)で人手による実施が必要。これは
`003-attr-end-at` の T018 と同様の制約。

## 3. attr.json欠落イベントの段階的な補完を確認する

```bash
python3 scripts/fetch/backfill_schema_version.py --token "$STARTGG_TOKEN" --max_events 5
```

確認ポイント:

- 実行ログに、従来は発見されなかった(`attr.json` 欠落の)イベントディレクトリの処理が
  含まれること。
- 対象イベントに `attr.json` が新規作成されること。
- `event_id` を `tournaments.jsonl` からも復元できなかったイベントがあれば、
  `[UNRESOLVED]` としてログに出力され、処理全体は最後まで完走すること。

同様に **未実施**: 実際の start.gg アクセスが必要なため、実環境での実施が必要。
