# Data Model: 取得対象からのイベント除外

## Excluded Event Entry(除外イベント登録)

`data/startgg/excluded_events.json`に保存される、event_id単位の除外記録。

### フィールド

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| event_id(オブジェクトのキー) | string(数値文字列) | MUST | start.gg上のevent_id。JSONオブジェクトのトップレベルキーとして表現する。 |
| excluded_at | string(`YYYY-MM-DD`) | MUST | 除外を記録した日付。FR-002。 |
| reason | string(自由記述) | MUST | 除外理由。FR-002。 |

### ファイル形状

```json
{
  "1359150": {
    "excluded_at": "2026-08-29",
    "reason": "テスト運用のみの重複イベント(壁スマ#2 ggテスト運用と同一)"
  }
}
```

### バリデーションルール

- event_idキーは、start.gg上の実在するevent_idに対応する数値文字列で
  MUSTある(スキーマレベルでの実在性検証は行わない。フォーマットのみ)。
- `excluded_at`・`reason`は空文字列であってはならない(MUST NOT)。
- 同一event_idのキーがJSONオブジェクト内に複数出現することは、JSON仕様上
  構造的にありえない(後勝ちで1件に統合される点は、既存の
  `excluded_phases.json`の実装がkey重複を想定していないのと同様)。

### ライフサイクル

- **追加**: JSONオブジェクトへ新しいキーを直接追記する(手動編集 +
  git commit)。
- **解除**: JSONオブジェクトから該当キーを削除する(FR-008)。無効化
  フラグ等の中間状態は持たない — エントリが存在する/しないの2値のみ。
- ファイル自体が存在しない場合は「除外イベント0件」として扱う
  (`excluded_phases.json`と同じ既存パターン)。

### 既存エンティティとの関係

- `data/startgg/excluded_phases.json`(既存, phase_id単位の除外)とは
  独立した別ファイル・別レジストリ。粒度が異なる(event全体 vs
  phase_group)ため統合しない。
- `tournaments.jsonl`の`events`配列・`data/startgg/events/`配下の
  イベントディレクトリとは、「このevent_idが登録されていれば、
  それらを新規に作らない」という一方向の制約関係を持つ(既存の
  イベントディレクトリ/`tournaments.jsonl`エントリのスキーマ自体への
  変更は無い)。
