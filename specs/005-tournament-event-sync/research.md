# Research: トーナメント単位でのイベント作り直し検知と空イベントの整理

Technical Context に `NEEDS CLARIFICATION` は無い(既存コードベースの延長で完結するため)。
本ドキュメントは、実装方針を決定する上で調査・比較検討した論点を記録する。

## 論点1: 新規イベント発見の実装場所とAPI経路

**Decision**: 新規スクリプト `scripts/fetch/backfill_tournament_events.py` を追加し、
`tournaments.jsonl` に記録済みの各トーナメントについて、既存の
`fetch_event_ids_from_tournament(tournament_id, game_id)`(`scripts/fetch/download.py`、
`004` で `events is None` の場合に `FetchError` を送出するよう修正済み)をそのまま再利用して
現在のイベント一覧を取得する。

**Rationale**: この関数は既に `data_backfill.yml` 等の既存経路で使われており、新しい
API実装を追加する必要が無い(Constitution V)。`004` の修正により `events` が `null` の
場合もクラッシュせず `FetchError` として扱えるため、安全に呼び出せる。

**Alternatives considered**:
- *`download_all_tournaments()` 自体に差分検知ロジックを組み込む*: `004` で既に
  `download_all_tournaments()` は「日付の食い違い」を検知する責務を持っており、
  さらに「event_id集合の食い違い」まで持たせると1つの関数の責務が肥大化する。また
  `download_all_tournaments()` は大会一覧の**新規発見**(日付範囲スキャン)が主目的であり、
  「既知のトーナメントを改めて掘り下げる」循環スキャンとは走査の性質が異なる(既存の
  `backfill_schema_version.py` がイベント単位のバージョンチェックを独立スクリプトに
  分離しているのと同じ考え方)。
- *`backfill_schema_version.py` に統合する*: 走査対象の粒度が「イベントディレクトリ」
  (schema backfill)と「トーナメント」(本機能)で異なり、対象発見のロジックを共存させると
  `iter_event_dirs()` 相当の関数が複雑になる。役割分離の観点から独立スクリプトとする。

## 論点2: 新規発見したイベントの取得・保存方法

**Decision**: `fetch_event_details(event_id)`(`event(id: $eventId)` を直接叩く、
`backfill_schema_version.py` / `scripts/fix/redownload_event.py` に既に存在するパターンと
同一の小さな関数)を `backfill_tournament_events.py` 内にも定義し、新しく発見した
event_id ごとに、`get_date_parts()` + `get_event_directory()` でディレクトリを計算した上で、
`download_standings()` → `download_seeds()` → `extend_user_info()` → `download_all_set()` →
`write_event_attributes()` という、既存の新規イベント取得と全く同じ手順を実行する。

**Rationale**: `fetch_event_ids_from_tournament()`(トーナメント→イベント一覧、
`videogameId` フィルタ付き)は一覧取得にのみ使い、個々のイベントの詳細取得には
`event(id: $eventId)` を直接叩く経路を使うことで、フィルタの副作用(今回発生した
`events: null` のような事象)を個別イベント取得の段階では受けない。この
`fetch_event_details()` パターンは既に2箇所(`backfill_schema_version.py`,
`redownload_event.py`)に独立定義されており、3箇所目の重複は既存の規約(`write_event_attributes`
が `download.py` / `download_specific_event.py` に独立定義されているのと同じ理由:
ファイル間の依存を増やさない)の範囲内として許容する。

**Alternatives considered**:
- *`backfill_one_event()` を新規イベントにも使えるよう拡張する*: `backfill_one_event()`
  は「既存ディレクトリの再取得」を前提にした関数(`event_dir` が既に存在する想定)であり、
  「まだディレクトリが存在しない新規イベント」を扱うには事前にディレクトリパスを計算する
  ロジックの追加が必要になる。責務が変わるため、別関数として実装する方が単純。

## 論点3: 空イベントディレクトリの削除基準と安全性

**Decision**: `standings.json` と `matches.json` の両方について、`{"data": [...]}` の
`data` 配列の要素数が0件(またはファイル自体が読めない)の場合にのみ削除対象とする
(ユーザー確認済み: `seeds.json` / `attr.json` の中身は判定に使わない)。削除は git 管理下の
ファイルに対して行われるため、誤りがあった場合も `git log` / `git checkout` で復元できる
(`004` の `record_event_path()` が `shutil.rmtree()` で古いディレクトリを削除する際の
安全性の考え方と同一)。

**Rationale**: この2ファイルは「実際に参加者がいたか」「実際に試合が行われたか」を直接
表す最も信頼できる指標であり、`004` の調査で実例(第7回チバスマ交流会 2025/08/16、
`num_entrants: 0`、両ファイルとも空)が確認されている。git によるバージョン管理が
安全網として機能するため、削除前に改めて start.gg へ再確認する追加のAPI呼び出しは
必須要件としない(spec.md Assumptions で明記済み)。

**Alternatives considered**:
- *削除前に該当 event_id を live に再確認する*: 追加のAPI呼び出しが必要になり、
  Constitution II(不要なAPI負荷を避ける)に反する。ローカルのファイル内容(既に
  正しく取得された結果)を信頼する方が既存の設計思想(取得済みデータをそのまま
  正とする)と一貫する。
- *`num_entrants` フィールド(attr.json)を判定に使う*: `attr.json` が欠落している
  ディレクトリ(`004` の対象)には使えないため、`standings.json`/`matches.json` という
  より基礎的なファイルを直接見る方が対象範囲が広く、`attr.json` の有無に依存しない。

## 論点4: `tournaments.jsonl` からの記録削除方法

**Decision**: `prune_empty_events.py` は、削除対象と判定した全ディレクトリについて、
まず `read_tournaments_jsonl()` で全体を読み込み、各トーナメントの `events[]` から
削除対象ディレクトリに一致する `path` を持つエントリを取り除いた上で、`write_jsonl()`
(既存の完全上書き関数、`004` の `record_event_path()` が使うのと同じ関数)で
`tournaments.jsonl` 全体を1回だけ書き戻す。

**Rationale**: `extend_jsonl()`(追記のみ)では古いエントリを消せない。`004` の
調査で判明した「`tournaments.jsonl` は追記専用ロジックだと同じ event_id のエントリが
更新されず古いまま残り続ける」問題と同じ構造のため、`004` で確立した「変更が必要な
場合は `write_jsonl()` で全体を書き戻す」パターンをそのまま踏襲する。

## 論点5: 循環スキャンの要否(User Story 1 と User Story 2 で異なる)

**Decision**: User Story 1(API呼び出しを伴う)は `backfill_schema_version.py` と同じ
カーソルファイル方式(`data/startgg/tournament_event_sync_cursor.txt`)の循環スキャンとする。
User Story 2(ローカルファイルの読み取り・削除のみ)はカーソルを持たず、毎回
`events_root` 全体をスキャンする単純なツールとする。

**Rationale**: User Story 1 はトーナメント数分のAPI呼び出しが発生するため、既存の
段階的バックフィルと同じ「1回の実行あたりの処理件数を制限し、続きから再開する」設計が
必要(spec.md FR-007、Constitution 開発ワークフロー節)。User Story 2 はAPI呼び出しが
無く、ローカルディスクの読み取りのみのため、既存の `scripts/fix/validate_data.py` 等と
同様、毎回全件処理しても実行コスト・API負荷の懸念が無い。

## 論点6: `schema_backfill.yml` に統合せず新規ワークフローとする理由

**Decision**: 既存の `schema_backfill.yml` に処理を追加するのではなく、新規ワークフロー
`tournament_event_sync.yml` を作成する。ただし `concurrency: group: chore-update-branch`
には参加させ、`chore-update` へ直接コミットする既存の3ワークフロー
(`schema_backfill.yml`(毎時), `update_tournament.yml`(毎日), `update_user.yml`(毎日))
と同じキューに並ばせる。

**Rationale**: `schema_backfill.yml` は `cron: "30 * * * *"`(毎時)で
event_data_version のロールアウトを細かく刻む用途にチューニングされており、頻度が
本機能(頻繁には起きないイベント作り直しの検知)には合わない。別ファイルにすることで
`update_tournament.yml` 等と同様の、より疎な独立した頻度を選べる。また、
`schema_backfill.yml` のジョブに処理を追加すると、その1ジョブの実行時間が延び、
`cancel-in-progress: true` により次の毎時トリガーで自分自身がより頻繁に打ち切られる
リスクが増す。ワークフローを分けつつ同じ `concurrency` グループに参加させることで、
コミット競合(3ワークフローとも同じ `chore-update` に直接pushする)は既存の仕組みで
引き続き回避しつつ、実行頻度・実行時間は独立に保てる。既存ワークフロー
(`data_backfill`/`data_force_refresh_backfill`/`schema_backfill`/`update_tournament`/
`update_user`/`data_gap_check`/`fetch_large_event`)がいずれも1関心事1ファイルの
単機能構成である、という確立された運用規約とも一貫する。

**Alternatives considered**:
- *`schema_backfill.yml` に本機能のステップを追加する*: ワークフローファイル数は
  減るが、上記の頻度・実行時間・障害切り分けの理由により却下。

**採用する具体的な頻度**: 毎週日曜 `cron: "0 12 * * 0"`(12:00 UTC = 21:00 JST)。
同じ「取りこぼしを定期的に拾う」性質の `data_gap_check.yml`(毎週日曜 10:00 UTC)に
頻度を合わせつつ、起動時刻を2時間ずらして同時実行の重なりを避ける。イベントの
作り直しは頻繁に起きる事象ではなく、検知が1週間遅れても実害は小さい一方、対象
トーナメント数分のAPI呼び出しが発生するため、`schema_backfill.yml` のような毎時実行は
不要と判断した。

## 既存実装への影響確認

- `fetch_event_ids_from_tournament()` / `download.py` 内の他の関数は変更しない
  (`004` で追加した `null` ハンドリングはそのまま利用するのみ)。
- `backfill_schema_version.py` / `download_all_tournaments()` / `download_by_ids()` は
  変更しない。本機能は完全に新規ファイルとして追加する。
- 新規ワークフロー `tournament_event_sync.yml` は、既存の `schema_backfill.yml` と
  同じ `chore-update` ブランチへのコミット・push パターンをそのまま踏襲する。
