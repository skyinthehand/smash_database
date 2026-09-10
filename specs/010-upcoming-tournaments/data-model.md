# Phase 1 Data Model: 未開催トーナメントの管理

## エンティティ

### `data/startgg/upcoming_tournaments.jsonl`(新規データファイル)

1行1大会のJSONL。実行のたびに全件が洗い替えられる(既存の
`tournaments.jsonl`と異なり、行の追記・部分更新は行わない)。

```json
{
  "tournament_id": 12345,
  "name": "第◯回◯◯",
  "country_code": "JP",
  "start_at": 1234567890,
  "end_at": 1234567890,
  "url": "https://www.start.gg/tournament/...",
  "place": {
    "city": "...",
    "lat": 0.0,
    "lng": 0.0,
    "venue_name": "...",
    "timezone": "Asia/Tokyo",
    "postal_code": "...",
    "venue_address": "...",
    "maps_place_id": "..."
  },
  "events": [
    {
      "event_id": 999,
      "event_name": "Singles",
      "num_entrants": 42,
      "is_online": false,
      "state": "...",
      "type": 1,
      "labels": {"registration_type": "...", "event_type": "..."},
      "label_version": 4
    }
  ],
  "fetched_at": 1234567890,
  "version": "1.0"
}
```

- **`tournament_id`**(int、必須): start.ggの大会ID。
- **`name`**(string、必須): 大会名。
- **`country_code`**(string、必須): 取得対象国コード(現状は常に`"JP"`。
  将来他地域を対象に追加する場合も、既存レコードと混在できるよう
  レコード単位で持たせる)。
- **`start_at`** / **`end_at`**(int、Unixタイムスタンプ、必須/任意):
  start.ggの`startAt`/`endAt`をそのまま格納。`end_at`は`null`の場合が
  ある(既存の`attr.json`の`end_at`と同じ扱い)。
- **`url`**(string、必須): 大会ページURL。
- **`place`**(object、必須): 既存`attr.json`の`place`辞書
  (`docs/data_model.md`)と同一のキー構成
  (`city`/`lat`/`lng`/`venue_name`/`timezone`/`postal_code`/
  `venue_address`/`maps_place_id`。`country_code`は上記のトップレベル
  フィールドと重複するためplace内には含めない)。将来、開催済みへの
  移行時に`write_event_attributes`等へ流用しやすくするため、既存の
  スキーマに合わせる。
- **`events`**(array、必須。空配列も許容): この大会に属する対象ゲームの
  種目一覧。
  - **`event_id`**(int、必須): start.ggの種目ID。
  - **`event_name`**(string、必須): 種目名。
  - **`num_entrants`**(int、必須(取得できた場合)。取得経路の障害等で
    どうしても取得できなかった場合のみ`null`を許容): 現時点の参加登録
    人数(FR-003a: 一覧クエリで取得できない場合は個別クエリに
    フォールバックしてでも取得する)。
  - **`is_online`**(bool、必須): オンライン開催かどうか。
  - **`state`**(start.gg側の種目state、必須。値の意味は既存`attr.json`の
    `state`フィールドと同じ)。
  - **`type`**(start.gg側の種目type、必須。既存`attr.json`の`type`と
    同じ)。
  - **`labels`**(object、必須。空dictも許容): 既存のイベントラベリング
    機構(`scripts/labeling.py`、`compute_event_labels`)による判定結果。
    スキーマは既存`attr.json`の`labels`と同一。
  - **`label_version`**(int、任意/`null`許容): `compute_event_labels`が
    返す判定バージョン。ルールセットの`min_event_data_version`要件を
    満たさない場合は`null`(既存の`attr.json`と同じ挙動)。
- **`fetched_at`**(int、Unixタイムスタンプ、必須): このレコードを取得
  した時刻。
- **`version`**(string、必須): `write_jsonl(..., with_version=True)`に
  より自動付与されるファイルフォーマットバージョン。

**Validation rules**:
- `tournament_id`は同一ファイル内で一意(1大会1行)。
- `events`が空配列の大会は、対象ゲームの種目が無いことを意味する
  (そのまま記録してよい。フィルタして除外する必要はない)。
- 本ファイルは既存の`tournaments.jsonl`・`data/startgg/events/`配下の
  いかなるファイルとも参照関係を持たない(独立したデータセット)。

**State transitions**: このエンティティに明示的な状態遷移は無い
(毎回全件が新規取得結果で置き換わるのみ)。大会の開催日を過ぎると、
次回実行時に取得対象から自然に外れて本ファイルから消える(既存の
履歴収集側が別途、開催済み大会として独立に収集する。両者間の
データの引き継ぎは無い、spec.md Edge Cases参照)。
