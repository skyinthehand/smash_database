# Contracts: 未開催トーナメントの管理

## 1. `scripts/queries.py`(新規クエリ関数、内部ライブラリ契約)

```python
def get_upcoming_tournaments_by_game_query(country_code: str, after_date: int) -> str: ...
```

- 既存の`get_tournaments_by_game_query()`(`scripts/queries.py:431`)とは
  別関数として新設する(既存関数・既存呼び出し元は一切変更しない)。
- クエリ変数: `$gameId: ID!`, `$perPage: Int!`, `$page: Int!`(既存と同じ)。
- filter: `{videogameIds: [$gameId], published: true, countryCode:
  "<country_code>", afterDate: <after_date>}`。
- `nodes`は既存の大会フィールド(`id name startAt endAt countryCode
  isOnline addrState city lat lng mapsPlaceId postalCode venueAddress
  venueName timezone url`)に加え、
  `events(filter: {videogameId: [$gameId]}) { id name numEntrants state
  type isOnline startAt }`をネストする。
- `research.md #1`/`#2`の通り、`afterDate`フィルタ・`events`ネストの
  両方について、実装着手時に実際のAPIレスポンスで有効性を確認する
  (`quickstart.md`参照)。無効だった場合のフォールバックは
  `research.md`の該当セクション・`data-model.md`の`num_entrants`の
  取得規則に従う。

## 2. `scripts/fetch/download_upcoming_tournaments.py`(新規スクリプト、CLI契約)

### コマンド

```bash
python3 scripts/fetch/download_upcoming_tournaments.py \
  --token <TOKEN> \
  [--country_code JP] \
  [--game_id 1386] \
  [--url https://api.start.gg/gql/alpha] \
  [--tournaments_file data/startgg/upcoming_tournaments.jsonl] \
  [--max_retries 20] [--retry_delay 5]
```

- `--token`(必須): start.gg APIトークン。
- `--country_code`(既定`JP`): 対象国コード。将来他地域を追加する場合も
  この引数を変えるだけで済む構造にする(コード内にハードコードしない)。
- `--game_id`(既定`1386`、既存`download.py`と同じ既定値): 対象ゲームID。
- `--tournaments_file`(既定`data/startgg/upcoming_tournaments.jsonl`)。
- リトライ関連引数は既存`download.py`と同じ意味・既定値
  (`scripts/utils.py`の`set_retry_parameters`にそのまま渡す)。

### 実行内容の契約

1. 指定`country_code`・`game_id`について、`afterDate`=実行時刻で
   `get_upcoming_tournaments_by_game_query`をページングしながら全件
   取得する(`fetch_all_nodes`または既存の`fetch_data_with_retries`+
   手動ページングいずれかを、既存パターンに合わせて選択する。
   憲法Principle V遵守)。
2. 各大会・各種目について、`data-model.md`のスキーマでレコードを組み立て、
   `scripts/labeling.py`の`compute_event_labels`でラベルを付与する。
3. `write_jsonl(records, tournaments_file, with_version=True)`で
   **毎回全件を上書き**する(既存ファイルの内容とのマージは一切行わない)。
4. 標準出力に、取得件数(大会数・種目数)を最低1行報告する
   (`update_tournament.yml`側での確認・デバッグ用)。
5. 本スクリプトは`data/startgg/tournaments.jsonl`・
   `data/startgg/events/`配下・`done.csv`・`done_events.csv`の
   いずれも一切読み書きしない(既存の履歴データから完全に独立)。
6. `git add`/`git commit`は行わない(既存の`scripts/fetch/*`と同じ、
   コミットはワークフロー側の責務)。

### 終了コード

- 正常終了: `0`。
- start.gg APIへの接続・クエリが最終的に失敗した場合: 非0で終了する
  (`.github/workflows/update_tournament.yml`側で`continue-on-error:
  true`により、この失敗が既存の履歴データ取得・commitを止めないように
  する)。

## 3. `.github/workflows/update_tournament.yml`(既存ワークフロー、追加ステップ契約)

既存の「Download tournaments (JP only)」ステップの後に、以下のステップを
1つ追加する(既存ステップの前後関係・既存ロジックは変更しない):

```yaml
- name: Refresh upcoming tournaments (JP)
  continue-on-error: true
  env:
    STARTGG_TOKEN: ${{ secrets.STARTGG_TOKEN }}
  run: |
    set -euxo pipefail
    python scripts/fetch/download_upcoming_tournaments.py \
      --token "$STARTGG_TOKEN" \
      --country_code "JP"
```

- `continue-on-error: true`により、このステップが失敗しても後続の
  「Run tests」「Detect changes」「Commit changes」「Push to main」は
  通常通り実行される。
- 既存の「Detect changes」(`git status --porcelain`)・
  「Commit changes」(`git add -A`)は変更不要
  (`upcoming_tournaments.jsonl`の変更も自動的に拾われる)。
