# クイックスタート: setごとの逐次取得によるマッチ取得とリカバリの検証

このガイドは、実装完了後に本機能をエンドツーエンドで検証する手順である。
レコード形状は[data-model.md](./data-model.md)、確認すべき保証事項は
[contracts/matches-record-contract.md](./contracts/matches-record-contract.md)
を参照。

## 前提条件

- Python 3.11、`pip install requests`（本リポジトリには他の依存関係は無い）。
- 以下のライブ実API検証シナリオには、読み取り権限を持つstart.gg APIトークン
  （`STARTGG_TOKEN`）が必要。ユニットテストのシナリオはトークン不要（全ての
  GraphQL呼び出しは、`scripts/test/test_download.py`の既存パターンに従い
  モックされる）。
- 全てのコマンドはリポジトリのルートから実行すること。

## 1. ユニットテスト（高速・ネットワーク不要——まずこれを実行する）

```bash
python -m unittest scripts.test.test_download -v
python -m unittest scripts.test.test_validate_data -v
python -m unittest scripts.test.test_backfill_schema_version -v
```

期待結果: 全てpass。これは憲法Principle IIIのゲートであり、最低限以下を
カバーすること:

- setの詳細を取得する前に、既知の全setについて1件ずつプレースホルダー
  （`set_id`のみ）レコードで`matches.json`が投入される（FR-002）。
- プレースホルダーと完了済みレコードが混在するイベントへの後続の実行では、
  まだプレースホルダーのままの`set_id`のみ詳細を取得し（FR-006/FR-007）、
  既にレコードが存在する`set_id`に対して重複レコードを追記することは無い
  （FR-008）。
- `attr.json`（`archive_status: "completed"`付き）が書き込まれるのは、
  プレースホルダーレコードが1件も残っていない場合に限る（FR-009）。
- set/マッチ詳細取得のどのコードパスからも、もはや`MaxPagesExceededError`
  は発生し得ず、`large-event-skip`ラベル付きの成果物も生成されない
  （FR-012/FR-013）。
- `backfill_schema_version.py`は、`attr.json.event_data_version`が新しい
  `EVENT_DATA_VERSION`を下回るイベント（または`attr.json`が完全に存在しない
  イベント）を検出し、逐次取得経路で再取得する（FR-010/FR-011）。

## 2. ライブAPIシナリオ: 中断された取得がデータを失わないこと（User Story 1）

`STARTGG_TOKEN`が必要。実在する大規模な大会（あるいは本機能の調査で既に
特定済みのもの——「第１９回グランドスラム」「渋谷大乱 第一陣」。spec.mdの
User Story 1参照）とその`tournament_id`を選ぶ。

```bash
python scripts/fetch/download.py --token "$STARTGG_TOKEN" \
  --tournament_ids <TOURNAMENT_ID> --country_code JP
# しばらく実行させ、大規模イベントのset詳細取得フェーズの途中で中断する
# （Ctrl-C）
```

**確認事項**（User Story 1 / SC-001）:

```bash
python3 -c "
import json
d = json.load(open('<event_dir>/matches.json'))
placeholders = [r for r in d['data'] if 'winner_id' not in r]
complete = [r for r in d['data'] if 'winner_id' in r]
print(f'placeholders={len(placeholders)} complete={len(complete)}')
assert not any(r for r in d['data'] if 'set_id' not in r), '全レコードがset_idを持つべき'
"
ls <event_dir>/attr.json  # まだ存在しないはず——イベントは未完了
```

同じ`download.py`コマンドを再実行する。**確認事項**（User Story 1 / FR-006,
SC-002）: `complete`の件数のみが増加し、既に完了していたレコードは1バイトも
変化せず、`set_id`が2回以上出現することも無い。`attr.json`が現れるまでこれを
繰り返す——これにより、手動ワークフローを一切使わず、通常のコマンドの
再実行だけで完了に到達できることが証明される（User Story 2 / SC-005）。

## 3. トレーサビリティの確認（User Story 4）

```bash
python3 -c "
import json
d = json.load(open('<event_dir>/matches.json'))
set_ids = [r['set_id'] for r in d['data']]
assert len(set_ids) == len(set(set_ids)), '重複するset_idが見つかった'
print(f'{len(set_ids)} 件のset_idが全て一意')
"
```

## 4. バックフィルの確認（FR-010/FR-011）

既にコミット済みの、本機能導入前のイベントディレクトリ（`attr.json`の
`event_data_version`が新しい値未満のもの）を1件選ぶ:

```bash
python scripts/fetch/backfill_schema_version.py --token "$STARTGG_TOKEN" --max_events 1
```

**確認事項**: そのイベントの`attr.json.event_data_version`が最新になっており、
`matches.json`の全レコードに`set_id`が付与され、プレースホルダーが1件も
残っていないこと。

## 5. 廃止の確認（FR-012/FR-013）

```bash
test ! -f .github/workflows/fetch_large_event.yml && echo "削除済み: OK"
grep -L "large-event-skip" .github/workflows/data_gap_check.yml && echo "large-event-skipステップ無し: OK"
```

## 6. ドキュメント同期の確認（憲法Principle I）

`docs/data_model.md`にプレースホルダーレコード形状と新しい
`EVENT_DATA_VERSION`が記載されていること、`docs/fix.md`に「set ID一覧取得
自体が破綻した場合、手動escape hatchが無い」という残存リスク（spec.mdの
Edge Cases）が記録されていることを確認する。
