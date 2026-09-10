# Quickstart: 未開催トーナメントの管理

実装後、以下の手順でエンドツーエンドに動作確認する。`data-model.md`の
ファイル形状、`spec.md`のFR/SCを合わせて参照。

## 前提

- リポジトリのルートで作業する。
- start.gg APIトークンが必要(`--token`)。

## 0. 実装着手前のAPI疎通確認(research.md #1/#2)

実装に入る前に、`contracts/cli.md`で定義した新規クエリ
(`get_upcoming_tournaments_by_game_query`)の形を、start.ggのAPI
Explorerまたは`curl`で1回試し、以下2点を確認する:

- `afterDate: <現在のUnixタイムスタンプ>`フィルタにより、`startAt`が
  現在時刻より未来の大会のみが返ること。
- 大会一覧ノードにネストした`events { ... numEntrants ... }`が、実際に
  参加登録人数を含んで返ること。

どちらかが期待通り動かない場合は、`research.md`のFallback節の方針で
実装する(`afterDate`無効時: クライアント側での早期終了判定。
`events`ネスト無効時: FR-003aの個別呼び出しフォールバック)。

## 1. 基本的な取得を確認する(US1, FR-001/002)

```bash
python3 scripts/fetch/download_upcoming_tournaments.py \
  --token <TOKEN> --country_code JP
```

- `data/startgg/upcoming_tournaments.jsonl`が新規作成・上書きされる
  ことを確認する。
- 出力されたJSONLの各行が`data-model.md`のスキーマ(`tournament_id`・
  `name`・`start_at`・`end_at`・`place`・`url`)を満たすことを確認する。
- 実際にstart.gg上で確認できる、開始日時が未来の代表的なJP大会が
  1件以上含まれていることを目視確認する。
- 既に開催済みの大会(例: 直近で終了した大会)が含まれていないことを
  確認する。

## 2. 参加登録人数を確認する(US2, FR-003/FR-003a)

- 上記1で取得した結果のうち、start.gg上で参加登録者数が分かっている
  大会を1つ選び、`events[].num_entrants`の値がstart.ggの表示と一致する
  ことを確認する。
- （`events`ネストが無効だった場合のみ）個別呼び出しフォールバックが
  発動していることをログから確認し、それでも`num_entrants`が正しく
  埋まっていることを確認する。

## 3. ラベル判定を確認する(US3, FR-004)

- `data/startgg/label_rules.json`に定義済みのルールに、種目名が合致する
  未開催イベントが含まれるよう取得対象を選ぶ(無ければ一時的にテスト用
  ルールを追加してもよい)。
- そのイベントの`labels`に該当ラベルが`true`で含まれることを確認する。
- ルールセットの`min_event_data_version`要件を満たさない場合、
  `label_version`が`null`になることを確認する。

## 4. 完全洗い替えを確認する(FR-006)

```bash
# 1回目の実行結果を保存しておく
cp data/startgg/upcoming_tournaments.jsonl /tmp/before.jsonl

# 少し時間を置いてから再実行
python3 scripts/fetch/download_upcoming_tournaments.py \
  --token <TOKEN> --country_code JP
```

- `/tmp/before.jsonl`の内容と比較し、1回目に存在したが2回目には
  開催日を過ぎて消えた大会が(該当があれば)いなくなっていることを
  確認する。
- 差分マージではなく、ファイル全体が最新の取得結果で置き換わっている
  こと(2回目のレコード数が2回目のAPIレスポンスの件数と一致すること)を
  確認する。

## 5. 既存データへの非干渉を確認する(FR-007)

```bash
git status --porcelain
```

- 上記1〜4の実行前後で、`data/startgg/tournaments.jsonl`・
  `data/startgg/events/`配下・`data/startgg/done.csv`・
  `data/startgg/done_events.csv`のいずれにも変更が無いことを確認する
  (`data/startgg/upcoming_tournaments.jsonl`以外に差分が出ないこと)。

## 6. ワークフロー統合時の失敗許容を確認する(FR-009)

- `scripts/fetch/download_upcoming_tournaments.py`を意図的に失敗させる
  (例: 無効なトークンを渡す)状態で`update_tournament.yml`相当の手順を
  ローカルで再現し、このステップが失敗しても後続の既存ステップ(履歴
  データ取得・テスト・commit)が実行されることを確認する
  (`continue-on-error: true`の効果確認)。

## 7. 自動テスト

```bash
python3 -m unittest discover -s scripts/test -p "test_*.py"
```

本機能に対応するテスト(`scripts/test/test_download_upcoming_tournaments.py`)
を含め、リポジトリ全体のテストが通ることを確認する(憲法Principle III)。
