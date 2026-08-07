# Contract: `attr.json`(イベント記録)

データ利用者(分析スクリプト・`scripts/queries.py` 等)に対する、イベント記録ファイルの
出力契約。本機能による変更点のみを記載する。フルスキーマは `docs/data_model.md` を参照。

## 変更前(`event_data_version <= 2`)

```json
{
  "version": "1.0",
  "event_id": 999,
  "tournament_name": "Example Tournament",
  "event_name": "Ultimate Singles",
  "timestamp": 1710001000,
  "region": "Japan",
  "num_entrants": 128,
  "offline": true,
  "url": "https://www.start.gg/tournament/...",
  "place": { "...": "..." },
  "labels": { "...": "..." },
  "status": "completed",
  "event_data_version": 2,
  "guest_entrant_count": 0
}
```

`end_at` フィールドは存在しない。

## 変更後(`event_data_version >= 3`)

```json
{
  "version": "1.0",
  "event_id": 999,
  "tournament_name": "Example Tournament",
  "event_name": "Ultimate Singles",
  "timestamp": 1710001000,
  "end_at": 1710086400,
  "region": "Japan",
  "num_entrants": 128,
  "offline": true,
  "url": "https://www.start.gg/tournament/...",
  "place": { "...": "..." },
  "labels": { "...": "..." },
  "status": "completed",
  "event_data_version": 3,
  "guest_entrant_count": 0
}
```

## 契約

- `end_at` は `event_data_version >= 3` のレコードにのみ存在を期待してよい。
  `event_data_version < 3` のレコードに対して `end_at` を読もうとするデータ利用側の
  コードは、キー自体が存在しない場合(`KeyError`/`None`)を MUST ハンドルする。
- `end_at` が存在する場合、値は `int`(UNIXタイムスタンプ、`timestamp` と同じ基準)
  または `null`(start.gg 側で終了日時が未確定)のいずれか。
- 後方互換性: `end_at` は `ATTR_REQUIRED_FIELDS` に含まれないため、既存の
  バリデーション(`scripts/fix/validate_data.py`)・既存データ利用コードは本変更に
  よって破壊されない。
