# Data Model

## 保存全体像
- start.gg の取得結果は `data/startgg/` に集約。
- 各イベントは `attr.json` / `standings.json` / `seeds.json` / `matches.json` に分割保存。

## 管理ファイル

### `data/startgg/done.csv`
```csv
12345
67890
```
- 1行1大会ID（既取得の大会）

### `data/startgg/done_events.csv`
```csv
999
1000
```
- 1行1イベントID（個別取得済み）

## 大会索引

### `data/startgg/tournaments.jsonl`
```json
{"tournament_id": 12345, "name": "Example Tournament", "events": [{"event_id": 999, "event_name": "Ultimate Singles", "path": "data/startgg/events/Japan/2024/01/01/Example_Tournament/Ultimate_Singles"}], "version": "1.0"}
```

## ユーザー

### `data/startgg/users.jsonl`
```json
{"user_id": 111, "player_id": 222, "gamer_tag": "PlayerName", "prefix": "Team", "gender_pronoun": "he/him", "startgg_discriminator": "1234", "x_id": "1", "x_name": "user_x", "discord_id": "2", "discord_name": "user#0001", "version": "1.0"}
```

## イベント属性

### `data/startgg/events/.../attr.json`
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
  "place": {
    "country_code": "JP",
    "city": "Tokyo",
    "lat": 35.68,
    "lng": 139.76,
    "venue_name": "Example Hall",
    "timezone": "Asia/Tokyo",
    "postal_code": "100-0001",
    "venue_address": "Tokyo, Japan",
    "maps_place_id": "..."
  },
  "labels": {
    "registration_type": "full-open",
    "event_type": "main",
    "game_rule": "1on1"
  },
  "archive_status": "completed",
  "state": "COMPLETED",
  "type": 1,
  "event_data_version": 6,
  "guest_entrant_count": 0
}
```
- `archive_status`: このスクリプトによるデータ取得処理自体が完了したことを表すマーカー(常に`"completed"`)。
  `event_data_version >= 6` では、そのイベントの`matches.json`に**プレースホルダー
  レコード(後述)が1件も残っていない場合にのみ**`attr.json`自体が書き込まれる
  ため、`attr.json`が存在すること自体がこの完了条件を満たしたことの証左になる
  (「matches」節参照)。
- `state`: start.gg API の `event.state`(`ACTIVE`/`COMPLETED`など、大会イベント自体の進行状況)。
  `event_data_version < 4` の既存データには存在しない(`null`扱い)。
  以前は`status`という紛らわしい名前のフィールドが`archive_status`の意味で使われていたが、
  `event_data_version=4`で`archive_status`にリネームし、`state`を新設した。
- `type`: start.gg API の `event.type`(イベント種別)。`event_data_version < 5` の既存データには
  存在しない(`null`扱い)。`event_data_version=5`で新設した。

## standings

### `data/startgg/events/.../standings.json`
```json
{
  "version": "1.0",
  "data": [
    {"placement": 1, "user_id": 111},
    {"placement": 2, "user_id": 112}
  ]
}
```

## seeds

### `data/startgg/events/.../seeds.json`
```json
{
  "version": "1.0",
  "data": [
    {"seed_num": 1, "user_id": 111},
    {"seed_num": 2, "user_id": 112}
  ]
}
```

## matches

### `data/startgg/events/.../matches.json`
`data`配列内の各レコードは、**完了済み(complete)**または**プレースホルダー
(placeholder)**のいずれかの状態を取る(`event_data_version >= 6`)。

- 完了済みレコード: そのsetの結果一式(下記フル形状)を持つ。
- プレースホルダーレコード: `set_id`のみを持ち、他のキーは一切存在しない
  (`winner_id`キーの有無で区別する。値が`null`の完了済みレコードと混同しない
  ため、値ではなくキーの存在で判定すること)。

一括取得(`event.sets`/`phaseGroup.sets`)が成功したイベントでは、プレースホルダーは
一切生成されず、全レコードが最初から完了済みの状態で書き込まれる。一括取得が
ページ/complexity上限などで失敗したイベントについてのみ、まずそのイベントの
全`set_id`についてプレースホルダーを投入し、`set(id: ID!)`によるset単位の取得で
順次完了済みレコードへ置き換えていく(「イベント属性」節の`archive_status`の
説明も参照)。同じ`set_id`のレコードが2件以上存在することはない。

```json
{
  "version": "1.0",
  "data": [
    {
      "set_id": 888,
      "winner_id": 111,
      "loser_id": 112,
      "winner_score": 2,
      "loser_score": 1,
      "round_text": "Winners Round 1",
      "round": 1,
      "phase": "A",
      "wave": "Wave 1",
      "dq": false,
      "cancel": false,
      "state": 3,
      "details": [
        {
          "game_id": 9999,
          "order_num": 1,
          "winner_id": 111,
          "entrant1_score": 1,
          "entrant2_score": 0,
          "stage": "Battlefield",
          "selections": [
            {
              "user_id": 111,
              "selection_id": 1,
              "character_id": 10,
              "character_name": "Mario"
            }
          ]
        }
      ]
    },
    {
      "set_id": 889
    }
  ]
}
```
上記の2件目(`{"set_id": 889}`のみ)がプレースホルダーの例。

- `set_id`: start.gg上のset ID。`event_data_version < 6`の既存データには存在しない
  (`null`相当)。既存イベントは`scripts/fetch/backfill_schema_version.py`の巡回
  バックフィルにより順次付与される。

## 注意点
- doubles/crew などは user_id が取得できず `null` になる場合がある。
- `labels` は OpenAI による推定であり、正確性は保証されない。
- `event_data_version` は「イベントごとに取得されるべきデータの内容(スキーマ世代)」を
  表す整数値であり、ファイル形式全体を表す `version` とは別物(`scripts/utils.py` の
  `EVENT_DATA_VERSION` 定数が現在の目標値)。本機能導入前に取得された既存イベントには
  存在せず、その場合は `0` 相当(最も古い)として扱う。
- `guest_entrant_count` は、start.gg アカウントにリンクされていない(ゲスト)参加者数。
  `download_standings()` が `standings` クエリから取得した参加者一覧のうち、
  `participants[0].user` が `null` だったエントラント数をそのまま数えており、
  追加のAPI呼び出しは発生しない。本機能導入前に取得された既存イベントには
  存在しない(`null`)。
- `end_at` は大会(トーナメント)全体の終了日時(UNIXタイムスタンプ、`timestamp` と
  同じ形式)。イベント(種目)ごとの個別の終了日時ではない。start.gg 側で終了日時が
  未確定の場合は `null`。`event_data_version` が `3` 未満の既存イベントには
  フィールド自体が存在しない(段階的バックフィルにより順次追加される)。
