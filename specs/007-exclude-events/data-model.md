# Data Model: 取得対象からのイベント除外

## ファイル: `data/startgg/excluded_events.json`

既存の`data/startgg/excluded_phases.json`をリネーム・拡張した、単一の
git管理ファイル。トップレベルはevent_id(文字列キー)をキーとする
JSONオブジェクトで、値の形によって2種類のエントリを区別する。

```json
{
  "436192": [
    {"phase_id": 731718, "reason": "start.gg側のデータ不整合によりsetsのページネーションが安定しない (2026-08-04確認)"}
  ],
  "1359150": {
    "reason": "テスト運用のみの重複イベント(壁スマ#2 ggテスト運用と同一)"
  }
}
```

## Excluded Phase Entry(除外Phase登録)— 既存、挙動不変

値が**配列**の場合。event_id配下の特定phaseのみを除外する、既存の
エンティティ(挙動・スキーマともに変更なし)。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| phase_id | number | MUST | 除外対象のphaseGroup ID相当の識別子。 |
| reason | string(自由記述) | MUST | 除外理由。 |

## Excluded Event Entry(除外イベント登録)— 新規

値が**オブジェクトかつ`reason`を直下に持つ**場合。event_idに対応する
イベント**全体**を除外する、新規のエンティティ。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| reason | string(自由記述) | MUST | 除外理由。FR-002。 |

除外日時は持たない。ファイル自体がgit管理されているため、いつ追加/
変更されたかは当該ファイルの`git log`/`git blame`で確認する
(`research.md` Decision 1a参照)。

### 2種類のエントリの判別ルール

- 値が配列(`list`) → **Excluded Phase Entry**の集合(phase単位の除外)。
- 値がオブジェクト(`dict`)かつ`"reason"`キーを直下に持つ →
  **Excluded Event Entry**(イベント全体の除外)。
- 専用の`type`フィールドは持たない(値の形自体が判別根拠。
  `research.md` Decision 1参照)。

### バリデーションルール

- event_idキーは、start.gg上の実在するevent_idに対応する数値文字列で
  MUSTある(スキーマレベルでの実在性検証は行わない。フォーマットのみ)。
- Excluded Event Entryの`reason`は空文字列であってはならない
  (MUST NOT)。
- 同一event_idのキーがJSONオブジェクト内に複数出現することは、JSON
  仕様上構造的にありえない。

### ライフサイクル

- **追加**: JSONオブジェクトへ新しいキー(またはキーの値)を直接追記
  する(手動編集 + git commit)。
- **解除**: JSONオブジェクトから該当キーを削除する(FR-008)。
  無効化フラグ等の中間状態は持たない — エントリが存在する/しないの
  2値のみ。
- ファイル自体が存在しない場合は「除外イベント・除外phaseともに0件」
  として扱う(既存の`excluded_phases.json`が無い場合の挙動を踏襲)。

### 既存エンティティとの関係

- `tournaments.jsonl`の`events`配列・`data/startgg/events/`配下の
  イベントディレクトリとは、「そのevent_idにExcluded Event Entryが
  存在すれば、それらを新規に作らない」という一方向の制約関係を持つ
  (既存のイベントディレクトリ/`tournaments.jsonl`エントリのスキーマ
  自体への変更は無い)。
- Excluded Phase Entryは、従来通り`fetch_set_ids_for_event()`/
  `fetch_all_sets()`(`scripts/fetch/download.py`)がsets取得時に
  参照する(本フィーチャーによる挙動変更なし)。
