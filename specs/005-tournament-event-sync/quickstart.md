# Quickstart: 空イベントディレクトリの整理

実装後、以下の手順でこの機能がエンドツーエンドで動作することを確認できる。

## 前提

- `scripts/fix/prune_empty_events.py` が実装済み。
- `scripts/fetch/download.py` の記録タイミング修正(取得処理開始前に
  `tournaments.jsonl` へ記録)が適用済み。
- start.gg API トークンが環境変数等で利用可能(`$STARTGG_TOKEN`)。
  ※空判定されたディレクトリは削除前に必ず start.gg へ再確認するため、
  `--apply` 時は本機能もAPIアクセスを必要とする。

## 1. 単体テストを実行する

```bash
python -m unittest scripts.test.test_prune_empty_events
python -m unittest scripts.test.test_download           # download.pyの記録タイミング修正
python -m unittest scripts.test.test_validate_data       # 既存テストが壊れていないことも確認
```

期待結果: 全てパスする。特に以下がカバーされていること
([contracts/empty-event-cleanup.md](./contracts/empty-event-cleanup.md) 参照):

- `standings.json` と `matches.json` が両方空のディレクトリのみが削除候補になる
  (どちらか一方でもデータがあれば削除されない)。
- 削除前に同じ event_id を再取得し、実データが見つかった場合は削除せず保存する
  (`healed`)。
- 再取得後も空の場合、同じトーナメント配下に未記録の他のイベントが無いかを確認し、
  見つかった場合、または確認できなかった場合(APIエラー等)は削除しない(`kept`)。
- 再取得後も空、かつ他のイベントも無いことを確認できた場合のみ削除する(`deleted`)。
- `--apply` を付けない(dry-run)場合はAPI呼び出しを一切行わず、候補件数の報告のみ行う。

## 2. 第7回チバスマ交流会での実データ検証

`event_id=1533881`(tournament_id=867504)は、`004-fix-duplicate-events` の記録
タイミング修正の発見過程で `scripts/fix/redownload_event.py --event-id 1533881 --yes`
により既に手動取得済み。残るのは `event_id=1423946`(tournament_id=811466、実データ
無し)のディレクトリの削除確認。

修正適用前:

```bash
ls data/startgg/events/Japan/2025/08/16/第7回チバスマ交流会/
```

→ ディレクトリが存在する。

`STARTGG_TOKEN` が利用可能な環境で:

```bash
# まず dry-run で候補件数を確認(API呼び出し無し)
python3 scripts/fix/prune_empty_events.py --token "$STARTGG_TOKEN"

# 実際に確認・削除
python3 scripts/fix/prune_empty_events.py --token "$STARTGG_TOKEN" --apply
```

確認ポイント:

- ログに `[811466] sibling check` 等の確認過程が出力され、最終的に
  `Deleted empty event directory` として `2025/08/16/第7回チバスマ交流会/` が削除される。
- `data/startgg/tournaments.jsonl` の tournament_id=811466 のエントリから
  `event_id=1423946` の記録が取り除かれる。

**未実施(本セッションのサンドボックス環境には実際の `STARTGG_TOKEN` / start.gg への
実ネットワークアクセスが無いため実行不可)**: マージ前またはマージ後、実環境で人手による
実施が必要。これは `003-attr-end-at` の T018、`004-fix-duplicate-events` の T024 と
同様の制約。

## 3. ドキュメント整合性の確認

```bash
grep -n "STARTGG_TOKEN" .github/workflows/prune_empty_events.yml
```

新規ワークフローが `chore-update` ブランチへのみコミットする既存パターンに従っており、
かつ `prune_empty_events.py` の実行に `STARTGG_TOKEN` を渡していることを確認する
(Constitution IV)。
