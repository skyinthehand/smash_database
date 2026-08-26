# start.gg API 設計

## 概要
- start.gg の GraphQL API を利用して大会・イベント・結果データを取得し、`data/startgg/` 配下に保存する。
- 実装は `scripts/fetch/download.py` を中心に構成され、補助スクリプトで欠損補完や個別取得を行う。

## エンドポイントと認証
- エンドポイント: `https://api.start.gg/gql/alpha`
- 認証: `Authorization: Bearer <token>`
- 送信ボディ（例）
```json
{
  "query": "query TournamentsByGame($gameId: ID!, $perPage: Int!, $page: Int!) { ... }",
  "variables": {
    "gameId": 1386,
    "perPage": 5,
    "page": 1
  }
}
```

## 取得クエリと主なレスポンス例

### 大会一覧
- クエリ: `get_tournaments_by_game_query`
- 目的: 最新順で大会一覧を取得
- 主なレスポンス（抜粋）
```json
{
  "data": {
    "tournaments": {
      "nodes": [
        {
          "id": 12345,
          "name": "Example Tournament",
          "startAt": 1710000000,
          "endAt": 1710086400,
          "countryCode": "JP",
          "isOnline": false,
          "city": "Tokyo",
          "lat": 35.68,
          "lng": 139.76,
          "mapsPlaceId": "...",
          "postalCode": "100-0001",
          "venueAddress": "Tokyo, Japan",
          "venueName": "Example Hall",
          "timezone": "Asia/Tokyo",
          "url": "https://www.start.gg/tournament/..."
        }
      ],
      "pageInfo": {
        "totalPages": 10
      }
    }
  }
}
```

### 大会内イベント一覧
- クエリ: `get_tournament_events_query`
- 目的: 大会IDごとにイベントを取得
- 主なレスポンス（抜粋）
```json
{
  "data": {
    "tournament": {
      "events": [
        {
          "id": 999,
          "name": "Ultimate Singles",
          "startAt": 1710001000,
          "isOnline": false
        }
      ]
    }
  }
}
```

### standings（順位 + 参加者）
- クエリ: `get_standings_query`
- 目的: placements と participant 情報を取得
- 主なレスポンス（抜粋）
```json
{
  "data": {
    "event": {
      "standings": {
        "nodes": [
          {
            "placement": 1,
            "entrant": {
              "id": 555,
              "participants": [
                {
                  "user": {
                    "id": 111,
                    "genderPronoun": "he/him",
                    "discriminator": "1234",
                    "authorizations": [
                      {"type": "TWITTER", "externalId": "1", "externalUsername": "user_x"},
                      {"type": "DISCORD", "externalId": "2", "externalUsername": "user#0001"}
                    ]
                  },
                  "player": {
                    "id": 222,
                    "gamerTag": "PlayerName",
                    "prefix": "Team"
                  }
                }
              ]
            }
          }
        ]
      }
    }
  }
}
```

### seeds（シード）
- クエリ: `get_seeds_query`
- 目的: seedNum と participant 情報を取得
- 主なレスポンス（抜粋）
```json
{
  "data": {
    "phase": {
      "seeds": {
        "nodes": [
          {
            "id": 777,
            "seedNum": 1,
            "entrant": {
              "id": 555,
              "participants": [
                {
                  "user": {"id": 111},
                  "player": {"id": 222, "gamerTag": "PlayerName", "prefix": "Team"}
                }
              ]
            }
          }
        ]
      }
    }
  }
}
```

### sets（試合 + ゲーム詳細）
- クエリ: `get_event_sets_query`
- 目的: セット情報とゲーム詳細（キャラ選択など）を取得
- 主なレスポンス（抜粋）
```json
{
  "data": {
    "event": {
      "sets": {
        "nodes": [
          {
            "id": 888,
            "state": 3,
            "winnerId": 555,
            "round": 1,
            "fullRoundText": "Winners Round 1",
            "phaseGroup": {
              "displayIdentifier": "A",
              "wave": {"identifier": "Wave 1"}
            },
            "slots": [
              {
                "entrant": {"id": 555},
                "standing": {"stats": {"score": {"value": 2}}}
              },
              {
                "entrant": {"id": 556},
                "standing": {"stats": {"score": {"value": 1}}}
              }
            ],
            "games": [
              {
                "id": 9999,
                "orderNum": 1,
                "winnerId": 555,
                "entrant1Score": 1,
                "entrant2Score": 0,
                "stage": {"name": "Battlefield"},
                "selections": [
                  {
                    "id": 1,
                    "entrant": {"id": 555},
                    "character": {"id": 10, "name": "Mario"}
                  }
                ]
              }
            ]
          }
        ]
      }
    }
  }
}
```

### set一覧（ID専用・逐次取得モードのプレースホルダー投入用）
- クエリ: `get_event_set_ids_query` / `get_phase_group_set_ids_query`
- 目的: 上記の`sets`一括クエリが失敗した(ページ/complexity上限などにより)イベント
  でのみ使う、フォールバック用の軽量な取得。`id`のみを要求し、`slots`/`games`等は
  一切含めないため、1ノードあたりのcomplexityコストが小さく、イベント総set数に
  対して1ページに収まる件数が大幅に増える。`excluded_phases.json`に登録された
  イベントでは`get_phase_group_set_ids_query`をphaseGroup単位で使う(通常の
  `get_phase_group_sets_query`と同じ除外パターン)。
- 主なレスポンス（抜粋）
```json
{
  "data": {
    "event": {
      "sets": {
        "pageInfo": {"total": 512, "totalPages": 3},
        "nodes": [{"id": 888}, {"id": 889}]
      }
    }
  }
}
```

### set詳細のバッチ取得（逐次取得モード）
- クエリ: `get_sets_by_ids_query(set_ids)`
- 目的: 上記のID一覧で判明した未取得の`set_id`を、ルートの`set(id: ID!)`
  フィールドに対するGraphQLエイリアス（`s0: set(id: $id0) { ... } s1: set(id:
  $id1) { ... }`）でバッチ化して直接取得する。フィールド選択は`get_event_sets_query`
  と同じ`_SET_NODE_FIELDS`を再利用する。1リクエストのcomplexityはバッチサイズ×
  1setあたりの固定コストで決まり、イベントの総set数には依存しない——これが、
  一括取得の失敗が「イベント規模に比例してcomplexityが増大する」ことに起因する
  問題への対処になっている。
- 主なレスポンス（抜粋、`set_ids=[888, 889]`の場合）
```json
{
  "data": {
    "s0": {"id": 888, "state": 3, "winnerId": 555, "...": "..."},
    "s1": {"id": 889, "state": 3, "winnerId": 556, "...": "..."}
  }
}
```

## ページングとリトライ
- ページングは `fetch_all_nodes()` が担当。`page` を増やしながら `nodes` を全取得。
- API失敗時は `fetch_data_with_retries()` がリトライ。
  - 429 は待機時間を延長。
  - 5xx は指数的に待機時間を増加。
- 逐次取得モードのset詳細バッチ取得(`fetch_set_details_by_ids`)も
  `fetch_data_with_retries()`を経由し、独自のリトライ実装は行わない
  (憲法Principle V)。

## 保存先
- 取得結果は `docs/data_model.md` に記載の形式で `data/startgg/` に保存される。
