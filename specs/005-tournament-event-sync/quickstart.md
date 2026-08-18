# Quickstart: トーナメント単位でのイベント作り直し検知と空イベントの整理

実装後、以下の手順でこの機能がエンドツーエンドで動作することを確認できる。

## 前提

- `scripts/fetch/backfill_tournament_events.py` が実装済み(User Story 1)。
- `scripts/fix/prune_empty_events.py` が実装済み(User Story 2)。
- start.gg API トークンが環境変数等で利用可能(`$STARTGG_TOKEN`)。

## 1. 単体テストを実行する

```bash
python -m unittest scripts.test.test_backfill_tournament_events
python -m unittest scripts.test.test_prune_empty_events
python -m unittest scripts.test.test_validate_data   # 既存テストが壊れていないことも確認
```

期待結果: 全てパスする。特に以下がカバーされていること
([contracts/tournament-event-discovery.md](./contracts/tournament-event-discovery.md) /
[contracts/empty-event-cleanup.md](./contracts/empty-event-cleanup.md) 参照):

- 記録済みの event_id 集合に無い新しい event_id が、通常の取得手順で新規保存される。
- 記録イベント数が0件のトーナメントも再チェック対象に含まれる。
- `standings.json` と `matches.json` が両方空のディレクトリのみが削除対象になる
  (どちらか一方でもデータがあれば削除されない)。
- `apply=False`(dry-run)では何も変更されない。

## 2. 第7回チバスマ交流会での実データ検証

修正適用前:

```bash
grep -A3 '"tournament_id": 811466' data/startgg/tournaments.jsonl
```

→ event_id は `1423946` のみが記録されている。

`STARTGG_TOKEN` が利用可能な環境で:

```bash
# User Story 1: 新しいevent_id(1533881)を発見・取得
python3 scripts/fetch/backfill_tournament_events.py --token "$STARTGG_TOKEN" --tournament_ids 811466

# User Story 2: 空のディレクトリ(event_id=1423946)を削除
python3 scripts/fix/prune_empty_events.py --apply
```

確認ポイント:

- `data/startgg/events/Japan/2026/02/07/第7回チバスマ交流会/.../attr.json` が
  `event_id: 1533881` で新規作成されていること。
- `data/startgg/events/Japan/2025/08/16/第7回チバスマ交流会/` が削除されていること。
- `data/startgg/tournaments.jsonl` の tournament_id=811466 のエントリが、event_id
  `1533881` のみを含み、`1423946` は取り除かれていること。

**未実施(本セッションのサンドボックス環境には実際の `STARTGG_TOKEN` / start.gg への
実ネットワークアクセスが無いため実行不可)**: マージ前またはマージ後、実環境で人手による
実施が必要。これは `003-attr-end-at` の T018、`004-fix-duplicate-events` の T024 と
同様の制約。

## 3. ドキュメント整合性の確認

```bash
grep -n "tournament_event_sync" .github/workflows/tournament_event_sync.yml
```

新規ワークフローが `chore-update` ブランチへのみコミットする既存パターンに従っていることを
確認する(Constitution IV)。
