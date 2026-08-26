# 実装計画: setごとの逐次取得によるマッチ取得とリカバリ

**ブランチ**: `006-incremental-set-fetch` | **日付**: 2026-08-26 | **仕様書**: [spec.md](./spec.md)

**入力**: `/specs/006-incremental-set-fetch/spec.md` のフィーチャー仕様

## 概要

大規模なstart.ggイベント（数百人規模、数千set規模）は現在、単一の一括ページング
クエリ（`event.sets`）がページ/complexity上限を超えると、`matches.json`と
`attr.json`が一切保存されないまま失敗する。`standings.json`/`seeds.json`は既に
成功しているにもかかわらずである。この修正では、既存の一括取得を主経路として
維持したまま（無駄にAPIリクエスト回数を増やさないため。大多数のイベントは
今日と同じく1回の一括クエリで完了する）、一括取得が実際に失敗した場合にのみ、
逐次的でレジューム可能な方式にフォールバックする。フォールバック時は、まず
新設する軽量なID専用の`event.sets`クエリで、set詳細を取得する前に
`matches.json`をset1件につきプレースホルダーレコード（`set_id`のみ）1件で
埋めておく。その後、未取得の各setについて詳細をIDで直接取得し
（`set(id: ID!)`。start.gg APIに実在することを確認済み）、プレースホルダーを
その場で置き換えていく。一度フォールバックしたイベント（`matches.json`は
存在するが`attr.json`がまだ無い状態）は、以後の実行で一括取得を再試行せず、
直接プレースホルダーの詳細取得に進む。これにより、フォールバック時の
1リクエストあたりのcomplexityはイベント規模に関係なく一定に保たれ、部分的に
取得済みのイベントは中断されてもデータを失わず、スケジュール実行をまたいで
再開できる。さらに`matches.json`自体（プレースホルダーと完了済みレコードの
混在状態）が、未取得分の追跡役を兼ねるため、別の中間ファイルは不要になる。
あわせて、不要になったmax_pagesベースのlarge-event-skip issue／
`fetch_large_event`手動リカバリ経路を廃止し（FR-013/014）、既存の
`event_data_version`駆動の巡回バックフィルサイクル経由で、過去分の
`matches.json`レコードにも`set_id`をバックフィルする（FR-011/012）。

## Technical Context（技術的コンテキスト）

**言語/バージョン**: Python 3.11（`.github/workflows/*.yml`のCI設定と一致）

**主要な依存関係**: `requests`（唯一のサードパーティ依存）。それ以外は全て標準
ライブラリ（`json`, `argparse`, `os`, `time`, `unittest`）。Webフレームワークや
ORM、パッケージマネージャの設定ファイルは無し（CI内で`pip install requests`を
直接実行）。

**ストレージ**: `data/startgg/events/{Region}/{YYYY}/{MM}/{DD}/{Tournament}/
{Event}/{attr,standings,seeds,matches}.json`配下のフラットなJSONファイル。git
リポジトリに直接コミットされる（データベースなし）。本機能により`matches.json`
にプレースホルダーレコード形状が追加されるが、新規ファイルは導入しない。

**テスト**: `python -m unittest scripts.test.<module>`（標準ライブラリの
`unittest`、GraphQL/APIのモックには`unittest.mock.patch`を使用 —
`fetch_latest_tournaments_by_game`、`fetch_event_ids_from_tournament`、
`download_all_set`等をモックする既存パターンは`scripts/test/test_download.py`を
参照）。憲法Principle IIIにより、`scripts.test.test_validate_data`は常にpassさせる
必要があり、新しいデータ形状には対応するテストの追加が必須。

**対象プラットフォーム**: 定期実行にはGitHub Actions（`ubuntu-latest`、
`.github/workflows/data_gap_check.yml`のjobタイムアウト60分）、手動・個別実行には
ローカルCLI実行（`scripts/fetch/download.py`、`download_specific_event.py`、
`backfill_schema_version.py`）。

**プロジェクト種別**: CLI／バッチ型データパイプライン（サーバーもUIも無し）。
`scripts/`配下の単一プロジェクト構成（Project Structure参照）。

**パフォーマンス目標**: レイテンシは重要ではない。制約となるのはGitHub Actions
のjobタイムアウト（60分）とstart.ggのリクエストあたりGraphQL complexity上限の
組み合わせであり、設計上の目標は「1リクエストのcomplexityがイベントの総set数に
比例して増大しないこと」——これにより進捗がall-or-nothingにならなくなる。

**制約**: 憲法Principle V — start.ggへの新規API呼び出しは全て
`scripts/utils.py`の`fetch_data_with_retries()`（単発リクエスト）／
`fetch_all_nodes()`（ページング）を経由し、独自のリトライ/バックオフを実装しない
こと。憲法Principle II — 冪等・インクリメンタルを維持すること。プレースホルダーと
完了済みレコードが混在するイベントに対して再実行しても、完了済みsetの再取得や
レコードの重複を起こさないこと。憲法Principle I — `matches.json`のスキーマ変更に
伴い`EVENT_DATA_VERSION`を上げ、同一PRで`docs/data_model.md`を更新し、既存データの
移行経路を用意すること（一回限りの移行スクリプトではなく、
`scripts/fetch/backfill_schema_version.py`の巡回サイクルを再利用する）。

**規模/スコープ**: `data/startgg/events/`配下には現状数千件のイベントディレクトリ
が存在する。実際に観測された大規模イベント: `grand_slum`（488人、`max_pages=200`
に対し`total_pages=1267`）、`SHIBUYA_DAIRAN`（256人、`total_pages=510`）——
spec.mdのUser Story 1参照。週次gap-check（`data_gap_check.yml`）は直近60日を走査
し、その他のワークフロー（`schema_backfill.yml`、`data_backfill.yml`、
`update_tournament.yml`）はそれぞれ独自のスケジュールで全履歴を対象に実行される。

## Constitution Check（憲法チェック）

*ゲート: Phase 0のresearch前に必ずpassすること。Phase 1の設計後に再チェックする。*

| 原則 | チェック内容 | 判定 |
|---|---|---|
| I. データスキーマの整合性とバージョニング | `matches.json`に新しいプレースホルダーレコード形状が加わる → `EVENT_DATA_VERSION`を5→6に上げ、同一PRで`docs/data_model.md`を更新し、既存データは*既存の*`backfill_schema_version.py`の巡回サイクル（FR-011/012）で移行する。独自の移行スクリプトは作らない。 | PASS（設計として確約） |
| II. 冪等でインクリメンタルな収集 | 一括取得は常に主経路として維持し、実際に失敗した場合にのみフォールバックする（FR-001〜FR-004）。プレースホルダー/完了済みレコードが混在するイベントへの再実行は、プレースホルダーのみを再取得し、一括取得を再試行しない（FR-004/007/008/009）。`done.csv`/`tournament_events_complete()`は既に「`attr.json`が無いイベントは未完了」として扱っているため、取得中の大規模イベントは自然に再訪される——新しい「完了」管理は不要。 | PASS |
| III. マージ前の検証ゲート | `scripts/test/`に新規テストが必要: プレースホルダーの投入、未取得setの検出、set_id重複の禁止、プレースホルダー0件による完了判定、large-event-skip廃止。`scripts.test.test_validate_data`は引き続きpassさせる（Phase 1の`validate_data.py`に関する注記参照）。 | PASS（タスクとして計画） |
| IV. ブランチとオートメーションの規律 | `data_gap_check.yml`等が使っている、`main`への直接commit／concurrency group／push競合時のrebaseリトライという既存パターンには変更なし。本機能は新しい自動化を追加するのではなく、既存ワークフロー内で`download.py`が行う処理を変更するだけ。`fetch_large_event.yml`の削除は既存自動化の削除であり、新規自動化経路の追加ではない。 | PASS |
| V. 外部APIへの耐障害アクセス | 新規クエリ（イベントのset ID一覧取得、`set(id:)`による単体/バッチ詳細取得）は、それぞれ`fetch_all_nodes()`/`fetch_data_with_retries()`を経由すること——独自のリトライループは書かない。`set(id: ID!): Set`がstart.ggのスキーマに実在することを確認済み（research.md参照）。 | PASS（設計として確約） |
| データ保存規約 | ディレクトリレイアウト（`{Region}/{YYYY}/{MM}/{DD}/{Tournament}/{Event}`）は変更なし。「set ID一覧取得自体が破綻した場合の手動escape hatchが無い」という残存リスク（spec.md Edge Cases）は、コードコメントではなく`docs/fix.md`に規約通り記録する。 | PASS（タスクとして計画） |
| 開発ワークフロー | 変更は`scripts/fetch/download.py`（取得ロジック）と`scripts/queries.py`（新規クエリ）に収まる——今日と同じファイル/役割分担であり、新しいスクリプト区分は増えない。`docs/data_model.md`、`docs/startgg_design.md`、`docs/flow.md`、`docs/fix.md`の更新は、スキーマ/ワークフロー変更と同一PRに含める。 | PASS（タスクとして計画） |

正当化が必要な違反は無し——Complexity Trackingの表は意図的に空。

**設計後の再チェック**（Phase 0/1後。research.md, data-model.md, contracts/,
quickstart.md参照）: 新たな違反は生じていない。上表で確約した内容——
`fetch_all_nodes()`/`fetch_data_with_retries()`の再利用（Principle V。
research.md §2でstart.ggの実スキーマに対して確認済み）、`EVENT_DATA_VERSION`＋
既存の`backfill_schema_version.py`サイクルを通したスキーマ変更の反映
（Principle I。research.md §5）、`matches.json`を唯一の真実の情報源とすることで
新しい「完了」管理を不要にした点（Principle II）、残存リスクをコードコメントでは
なく`docs/fix.md`に記録する点（データ保存規約）——は全てPhase 1の設計成果物に
一貫して引き継がれている。引き続きPASS。

## Project Structure（プロジェクト構成）

### ドキュメント（本フィーチャー）

```text
specs/006-incremental-set-fetch/
├── plan.md              # 本ファイル（/speckit-plan コマンドの出力）
├── research.md          # Phase 0 出力（/speckit-plan コマンド）
├── data-model.md         # Phase 1 出力（/speckit-plan コマンド）
├── quickstart.md        # Phase 1 出力（/speckit-plan コマンド）
├── contracts/           # Phase 1 出力（/speckit-plan コマンド）
│   └── matches-record-contract.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 出力（/speckit-tasks コマンド — 本コマンドでは作成しない）
```

### ソースコード（リポジトリルート）

これは既存のリポジトリ構成そのものであり、新しいトップレベルディレクトリは
導入しない。変更は既存の`fetch`/`fix`/`test`の分離（憲法「開発ワークフロー」）の
中に収まる。

```text
scripts/
├── fetch/
│   ├── download.py                 # 変更: 既存の一括download_all_set()経路は
│   │                                #   主経路として維持し、失敗時のみプレース
│   │                                #   ホルダー投入＋setごとの逐次取得へフォール
│   │                                #   バックする（FR-001〜FR-004）。FR-013/014
│   │                                #   によりmax_pagesベースのlarge-event-skip
│   │                                #   issue化ロジックのみ削除（max_pages自体は残る）
│   ├── backfill_schema_version.py  # 変更（download.pyの関数に完全委譲していれば
│   │                                #   影響なしの可能性あり）: EVENT_DATA_VERSION
│   │                                #   の引き上げにより、set_idを持たないイベント
│   │                                #   が巡回バックフィル対象として拾われる
│   ├── download_specific_event.py  # 整合性を確認。旧・一括取得パターンを重複
│   │                                #   実装している箇所があれば変更
│   └── refresh_event_dir.py        # 整合性を確認（matches_only経路）
├── fix/
│   └── validate_data.py            # 確認のみ。任意で、attr.json存在時に
│                                    #   プレースホルダーレコードが残っていないことを
│                                    #   検証する強化を追加してもよい
├── test/
│   ├── test_download.py            # 変更: FR-001〜FR-010, FR-015の新規テスト
│   │                                #   （一括成功時にプレースホルダーが一切
│   │                                #   生成されないことの確認を含む）
│   └── test_validate_data.py       # 引き続きpassさせる必要あり（憲法Principle III）
├── queries.py                      # 変更: 軽量なID専用event.setsクエリと、
│                                    #   set(id:)による詳細取得クエリを追加
└── utils.py                        # 変更: EVENT_DATA_VERSIONを5→6に引き上げ

.github/workflows/
├── data_gap_check.yml              # 変更なし（download.pyの新しい取得戦略の
│                                    #   副次効果として挙動が改善する）
└── fetch_large_event.yml           # 削除（FR-013）

docs/
├── data_model.md                   # 変更: matches.jsonのプレースホルダー形状、
│                                    #   set_idフィールド、EVENT_DATA_VERSION=6を記載
├── startgg_design.md               # 変更: 新設した2つのクエリを記載
├── flow.md                         # large-event-skipの手順が図示されていれば変更
└── fix.md                          # 変更: 「set ID一覧取得自体が破綻した場合、
                                     #   手動escape hatchが無い」という残存リスクを記録

data/startgg/events/{Region}/{YYYY}/{MM}/{DD}/{Tournament}/{Event}/
├── attr.json        # 形状は変更なし。プレースホルダーが1件も残っていない時に
│                     #   のみ書き込まれるようになる
├── standings.json    # 変更なし
├── seeds.json        # 変更なし
└── matches.json      # 形状変更: レコードはプレースホルダー（set_idのみ）または
                       #   完了済みのいずれか。全レコードにset_idを追加
```

**構成方針**: 既存のPythonスクリプトプロジェクト単一構成
（`scripts/fetch`、`scripts/fix`、`scripts/test`、`scripts/queries.py`、
`scripts/utils.py`）をそのまま使う——新規プロジェクト・パッケージ・トップレベル
ディレクトリは追加しない。本機能は`download.py`の取得戦略の変更と、
`queries.py`への新規GraphQLクエリ2件の追加として実装し、憲法が既に定めている
fetch/fix/testの分離をそのまま踏襲する。

## Complexity Tracking（複雑さの追跡）

> 憲法チェックの違反は無し——この表は意図的に空にしている。
