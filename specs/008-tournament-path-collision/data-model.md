# Data Model: 同日同名トーナメントの保存先パス衝突の解消

本フィーチャーは新しいデータファイルを追加しない。既存の
`tournaments.jsonl`/イベントディレクトリの取り扱いロジックのみを変更する。

## Path Collision(保存先パス衝突)— 概念上のエンティティ、永続化はしない

`tournaments.jsonl`から導出される、一時的な(計算のたびに再構築される)
概念上のエンティティ。専用のファイルには保存しない。

| フィールド | 型 | 説明 |
|---|---|---|
| path | string | 衝突しているディレクトリパス(地域/年/月/日/大会名/イベント名)。 |
| tournament_id_a / event_id_a | number | 衝突当事者1の識別子。 |
| tournament_id_b / event_id_b | number | 衝突当事者2の識別子。 |
| num_entrants_a / num_entrants_b | number \| null | 各当事者の参加者数。判明していない場合は`null`。 |
| resolved | boolean | 既に一方の保存先が調整済み(=もう衝突していない)かどうか。 |

- User Story 3の監査ツール(`find_path_collisions.py`)は、この形の情報を
  `tournaments.jsonl`から算出して一覧表示する(ファイルには書き出さない)。
- User Story 4の修復ツール(`fix_path_collision.py`)は、この情報を入力
  として受け取り、`resolved: true`の状態に変換する(=両者を別ディレクトリ
  に再配置し、`tournaments.jsonl`を更新する)。

## 既存エンティティへの影響

### `tournaments.jsonl`(既存、スキーマ変更なし)

各イベントエントリの`path`フィールドの**値**が、衝突が発生した場合に
限り、`get_event_directory()`が素直に計算する名前ではなく、調整後の
名前(大会名 + `tournament_id`のサフィックス。`research.md` Decision 4)
になり得る。フィールド自体の追加・削除は無い。

```json
{"tournament_id": 823456, "name": "新京都DSW#34", "events": [{"event_id": 1576210, "event_name": "SingleTournament", "path": "data/startgg/events/Japan/2026/03/20/新京都DSW#34_(823456)/SingleTournament"}], "version": "1.0"}
```

### `attr.json`(既存、スキーマ変更なし)

`tournament_name`フィールドの値は、start.gg上の実際の大会名のまま
変更しない(衝突解決によるディレクトリ名の調整は、あくまで**保存先
パスの計算**にのみ影響する。`attr.json`内に記録される大会名自体は
これまで通り実際の名前を保持する)。これにより、`attr.json`を見れば
「なぜこのディレクトリ名にサフィックスが付いているか」(実際の大会名と
ディレクトリ名が食い違って見える理由)を追跡できる。

## 新規関数のシグネチャ(実装の手引き)

- `build_path_index(tournaments: dict) -> dict[str, tuple[int, int]]`:
  `path -> (tournament_id, event_id)`。
- `resolve_path_collision(new_event_dir, new_num_entrants, existing_tournament_id, existing_event, tournaments) -> str`:
  最終的に使うべき`new_event_dir`(調整後の場合あり)を返す。既存側を
  調整すべき場合は、`tournaments`辞書内の既存エントリの`path`をその場で
  書き換え、対応するディレクトリを実際にリネームする副作用を持つ。
- `disambiguate_event_name(tournament_name: str, tournament_id: int) -> str`:
  `f"{tournament_name}_({tournament_id})"`(既存の空白/スラッシュ置換を
  適用した上で)。
