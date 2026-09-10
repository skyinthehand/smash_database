# Research: 未開催トーナメントの管理

## 1. 未開催大会の絞り込み方法

**Decision**: 既存の`get_tournaments_by_game_query()`(`scripts/queries.py:431`)
と同じ構造で、`beforeDate`と対になる`afterDate: <現在のUnixタイムスタンプ>`
フィルタを追加した新規クエリを用意し、`sortBy: "startAt desc"`のまま
`afterDate`で開始日時が未来の大会のみに絞り込む。

**Rationale**: 既存コードは`beforeDate`(過去方向の絞り込み)のみを
使っており、`afterDate`(未来方向)は一度も使われていないが、
`beforeDate`と対になるフィルタとしてstart.gg側のクエリ層に存在する
可能性が高い(一般的なGraphQL APIの日時範囲フィルタの実装パターン、
および`beforeDate`の実装から見て対称的なフィルタが用意されているのが
自然)。既存コード内の事実からは断定できないため、**実装の最初の
ステップとして、実際にこのクエリをstart.gg APIに対して1回実行し、
`afterDate`が意図通り機能する(未来の大会のみが返る)ことを確認する**
(このリポジトリでの既存の慣習として、ユーザー自身のトークンで
GraphQL Explorer等を使って事前検証してから実装に進むパターンを踏襲する)。

**Alternatives considered**:
- フィルタ無しで全件取得し、クライアント側で`startAt > now`を判定する案:
  `sortBy: "startAt desc"`のみだと過去・未来が1本のソートに混在し、
  何年分もの過去データを無駄にページングすることになるため不採用。
- `past: true`を使う案: 名前からして「過去のみ」を返す既存フィルタと
  推測され、今回欲しい「未来のみ」の逆方向には使えない。

**Fallback(`afterDate`が実際には機能しなかった場合)**: `beforeDate`
無し・`afterDate`無しで全件取得しつつ、`sortBy: "startAt desc"`により
最新(＝最も未来)の大会から順に返る性質を利用し、`startAt`が現在時刻を
下回った時点でページング自体を打ち切る(クライアント側の早期終了判定)。
既存の`download_all_tournaments`の`finish_date`到達時の`break`
(`scripts/fetch/download.py:457-460`)と同じ考え方を未来方向に反転させた
もの。

## 2. 参加登録人数の取得方法

**Decision**: まず、大会一覧クエリの`nodes`内に
`events(filter: {videogameId: [$gameId]}) { id name numEntrants state
type isOnline startAt }`をネストした形で1リクエストにまとめる方式を試す。
実装の最初のステップとして、この形のクエリが実際に有効か(`numEntrants`
を含むevents情報が返るか)をユーザーのトークンで確認する。

**Rationale**: 既存の`get_event_details_by_tournament_query()`
(`scripts/queries.py:479`)が`tournament { ... } events(filter:
{slug:...}) { ... numEntrants ... }`という、まさに「トーナメントの下に
eventsをネストしてnumEntrantsを取る」形を既に使っている実例であるため、
同じネスト構造を大会一覧クエリに適用できる可能性が高い。これが有効なら、
既存の履歴収集が行っている「トーナメント一覧→トーナメントごとにevents
個別取得→イベントごとに詳細取得」というN+1呼び出しを避けられる。

**Alternatives considered**: 既存の履歴収集と同じ2段階(`
fetch_event_ids_from_tournament`相当→イベントごとに`numEntrants`取得)を
最初から採用する案。呼び出し回数が確実に増える(トーナメント数×平均
イベント数に比例)ため、まずは1リクエストで済む方式を試す。

**Fallback(2026-09-10のクリアリングで確定、FR-003a)**: 一覧クエリへの
ネストが機能しない場合、既存の履歴収集と同じ「トーナメントごとに
`fetch_event_ids_from_tournament`相当で種目一覧を取得→種目ごとに
`get_event_details_by_id_query`相当で`numEntrants`を取得」という個別
呼び出しにフォールバックする。コストは増えるが、対象がJP圏の開催前
大会のみ(小規模)であるため許容範囲と判断する。

## 3. ラベル判定の再利用方法

**Decision**: `scripts/labeling.py`の`compute_event_labels(existing_labels,
tournament_name, event_name, event_data_version, rules_path=...)`を
そのまま呼び出す。`existing_labels=None`(未開催大会には前回状態が
存在しない)、`event_data_version=EVENT_DATA_VERSION`
(`scripts/utils.py`で定義される現行の最新スキーマバージョン定数)を渡す。

**Rationale**: `compute_event_labels`は`tournament_name`/`event_name`の
文字列ベースの判定のみを行い、既存の`attr.json`のスキーマバージョンに
紐づく他のフィールドには依存しない(`event_data_version`は「ルール自体が
まだ判定対象にできるか」のバージョンゲートとしてのみ使われる)。未開催
大会には元々「スキーマバージョン」という概念が無いため、判定が
バージョンゲートで不必要にスキップされないよう、常に最新版
(`EVENT_DATA_VERSION`)として扱うのが妥当。`compute_event_labels`は
`rules_path`ごとにプロセス内キャッシュされるため、追加のキャッシュ制御は
不要(`scripts/labeling.py:190`)。

**Alternatives considered**: なし(既存機構をそのまま再利用する以外の
選択肢を検討する理由がない)。

## 4. 出力ファイルの書き込み方法

**Decision**: `scripts/utils.py`の`write_jsonl(records, file_path,
with_version=True)`をそのまま使い、毎回全件を上書きする(既存の
`extend_jsonl`のような追記は使わない)。

**Rationale**: 既存の`tournaments.jsonl`書き込みと全く同じ関数を再利用
できるため、新規実装が不要。`with_version=True`により各レコードに
`version`フィールドが自動付与され、憲法Principle Iの要件を満たす。

**Alternatives considered**: 差分検出して`extend_jsonl`で部分更新する案。
spec.mdで「差分検知ロジックは不要、毎日全件取得し直して完全上書き」と
既に確定しているため不採用。
