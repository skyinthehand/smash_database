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

- **一括取得が成功する（小〜中規模の）イベントでは、`set_id`は一括クエリの
  レスポンスから直接抽出され、プレースホルダーは一切生成されず、set一覧
  取得クエリも`set(id:)`個別取得クエリも一切呼ばれない**（FR-001/FR-002。
  本フィーチャー導入前と比べてAPIリクエスト数が増えないことの直接的な
  裏付け——SC-001）。
- 一括取得が失敗した場合にのみ、setの詳細を取得する前に、既知の全setに
  ついて1件ずつプレースホルダー（`set_id`のみ）レコードで`matches.json`が
  投入される（FR-003）。
- `matches.json`は既に存在するが`attr.json`がまだ無いイベント（＝前回
  フォールバックに入ったイベント）を後続の実行で処理する場合、一括取得は
  再試行されず、まだプレースホルダーのままの`set_id`のみ詳細を取得する
  （FR-004/FR-007/FR-008）。既にレコードが存在する`set_id`に対して重複
  レコードを追記することは無い（FR-009）。
- `attr.json`（`archive_status: "completed"`付き）が書き込まれるのは、
  プレースホルダーレコードが1件も残っていない場合に限る（FR-010）。
- large-event-skipの自動issue作成と`fetch_large_event`ワークフローに
  関するコード・ワークフロー定義がもはや存在しない（FR-013/FR-014）。
  （`MaxPagesExceededError`自体は一括取得の失敗検知として引き続き発生し
  得る——research.md §6の「注記」参照。）
- `backfill_schema_version.py`は、`attr.json.event_data_version`が新しい
  `EVENT_DATA_VERSION`を下回るイベント（または`attr.json`が完全に存在しない
  イベント）を検出し、一括優先・失敗時のみ逐次取得の経路で再取得する
  （FR-011/FR-012）。

## 2. ライブAPIシナリオ 0: 小規模イベントは今日と同じ経路のまま（回帰確認）

`STARTGG_TOKEN`が必要。既に問題なく取得できている小〜中規模の大会
（`tournament_id`）を1件選ぶ。

```bash
python scripts/fetch/download.py --token "$STARTGG_TOKEN" \
  --tournament_ids <SMALL_TOURNAMENT_ID> --country_code JP
```

**確認事項**（SC-001）:

```bash
python3 -c "
import json
d = json.load(open('<event_dir>/matches.json'))
placeholders = [r for r in d['data'] if 'winner_id' not in r]
assert len(placeholders) == 0, '一括取得が成功したイベントにプレースホルダーは残らないはず'
assert all('set_id' in r for r in d['data']), '全レコードがset_idを持つべき'
print('OK: 一括取得のみで完了、プレースホルダー無し')
"
ls <event_dir>/attr.json  # 直後に存在するはず——今日と同じ挙動
```

併せて、実行ログ（標準出力）にID専用のset一覧クエリや`set(id:)`個別取得
クエリのリクエストログが**出ていない**ことを目視で確認する——これが
「無駄にクエリ実行回数を増やさない」ことの直接的な確認になる。

## 3. ライブAPIシナリオ 1: 中断された取得がデータを失わないこと（User Story 1）

実在する大規模な大会（あるいは本機能の調査で既に特定済みのもの——
「第１９回グランドスラム」「渋谷大乱 第一陣」。spec.mdのUser Story 1参照）
とその`tournament_id`を選ぶ。一括取得が実際に失敗し、逐次取得モードへ
フォールバックすることを前提としたシナリオである。

```bash
python scripts/fetch/download.py --token "$STARTGG_TOKEN" \
  --tournament_ids <LARGE_TOURNAMENT_ID> --country_code JP
# 一括取得が失敗してフォールバックし、逐次取得（プレースホルダーの詳細取得）
# フェーズの途中で中断する（Ctrl-C）
```

**確認事項**（User Story 1 / SC-002）:

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

同じ`download.py`コマンドを再実行する。**確認事項**（User Story 1 /
FR-004/FR-007, SC-003）: 実行ログに一括取得の再試行（`event.sets`/
`phaseGroup.sets`への大量ページングリクエスト）が出ておらず、既存の
プレースホルダーの詳細取得から直接始まっていること。`complete`の件数のみが
増加し、既に完了していたレコードは1バイトも変化せず、`set_id`が2回以上
出現することも無い。`attr.json`が現れるまでこれを繰り返す——これにより、
手動ワークフローを一切使わず、通常のコマンドの再実行だけで完了に到達
できることが証明される（User Story 2 / SC-006）。

## 4. トレーサビリティの確認（User Story 4）

```bash
python3 -c "
import json
d = json.load(open('<event_dir>/matches.json'))
set_ids = [r['set_id'] for r in d['data']]
assert len(set_ids) == len(set(set_ids)), '重複するset_idが見つかった'
print(f'{len(set_ids)} 件のset_idが全て一意')
"
```

## 5. バックフィルの確認（FR-011/FR-012）

既にコミット済みの、本機能導入前のイベントディレクトリ（`attr.json`の
`event_data_version`が新しい値未満のもの）を1件選ぶ:

```bash
python scripts/fetch/backfill_schema_version.py --token "$STARTGG_TOKEN" --max_events 1
```

**確認事項**: そのイベントの`attr.json.event_data_version`が最新になっており、
`matches.json`の全レコードに`set_id`が付与され、プレースホルダーが1件も
残っていないこと。

## 6. 廃止の確認（FR-013/FR-014）

```bash
test ! -f .github/workflows/fetch_large_event.yml && echo "削除済み: OK"
grep -L "large-event-skip" .github/workflows/data_gap_check.yml && echo "large-event-skipステップ無し: OK"
```

## 7. ドキュメント同期の確認（憲法Principle I）

`docs/data_model.md`にプレースホルダーレコード形状と新しい
`EVENT_DATA_VERSION`が記載されていること、`docs/fix.md`に「set ID一覧取得
自体が破綻した場合、手動escape hatchが無い」という残存リスク（spec.mdの
Edge Cases）が記録されていることを確認する。
