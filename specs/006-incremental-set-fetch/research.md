# Research: setごとの逐次取得によるマッチ取得とリカバリ

## 1. イベントのset ID一覧を安く取得する

**決定**: `scripts/queries.py`に新規の最小限GraphQLクエリ
（`get_event_set_ids_query()`）を追加する。`event(id: $eventId)`配下の
`sets(page, perPage) { pageInfo { total totalPages } nodes { id } } }`のみを
要求し、既存の`_SET_NODE_FIELDS`/`_SET_NODE_FIELDS_LIGHT`（`slots`、`games`、
`selections`等を含む）ではなく、`id`のみのフィールド選択にする。取得は既存の
`fetch_all_nodes()`ヘルパー経由（ページング・リトライ込み）で、今日の一括setsクエリ
と同じ仕組みを使う。

**根拠**: 元々の失敗（`grand_slum`: `max_pages=200`に対し`total_pages=1267`。
`SHIBUYA_DAIRAN`: `total_pages=510`）は、start.ggのリクエストあたりGraphQL
complexity上限に起因し、1ノードあたりに要求するネストしたフィールド数×1ページ
あたりのノード数に比例してcomplexityが増大する。IDのみの射影であれば1ノード
あたりのコストは小さく一定なので、complexity上限に到達するまでに1ページに収まる
set数が大幅に増える——このlisting段階は、実際に観測された最大級のイベントでも
問題なくページングを完走できると見込んでいる（spec.md Assumptions）。

**検討した代替案**:
- listingに既存の`get_event_sets_light_query()`（`_SET_NODE_FIELDS_LIGHT`）を
  流用する。却下: `slots`、`games`、`phaseGroup`を1ノードあたり要求する点は変わらず
  ——complexity爆発を縮小しただけで、根本的には解消していない。
- `standings`/`seeds`のエントラント数からset数を推定する。却下: エントラント数
  からは個々の`set_id`が得られず、プレースホルダーの投入（FR-002）や未取得分の
  検出（FR-007）に必要な情報が不足する。

## 2. 単一setの詳細をIDで直接取得する

**決定**: 未取得の各setの詳細は、`event.sets`や`phaseGroup.sets`のページング
継続ではなく、start.ggのトップレベルクエリ`set(id: ID!): Set`を使って取得する。
フィールド選択は既存の`_SET_NODE_FIELDS`をそのまま再利用する。

**根拠**: start.ggの公開GraphQLスキーマリファレンス（`developer.start.gg` →
`smashgg-schema.netlify.app/reference/query.doc.html`）を実際に取得して確認した
ところ、ルートの`Query`型には`event`、`phaseGroup`、`phase`等と並んで
`set(id: ID!): Set`が存在する。IDで取得することで、1リクエストあたりの
complexityは`_SET_NODE_FIELDS`の固定的な形状にのみ依存し——イベントの総set数や
どのphase/poolに属するかとは無関係になる。これが「逐次的」であることの本質
（FR-003）であり、1つのリクエストが二度と「イベント全体」を見る必要が無くなる。

**検討した代替案**:
- `event.sets`/`phaseGroup.sets`のページング（今日の実装。`download.py`の
  `_fetch_all_sets_by_phase_group` / `_fetch_sets_with_fallback`）を続けつつ、
  set_idではなくページ番号でチェックポイントを取る。却下: 巨大なプール1つを
  持つイベントでは、チェックポイント粒度に関係なく1ページ目でcomplexity予算を
  使い切ってしまう可能性がある（これはまさに、既知の問題phaseGroupを除外する
  ための`excluded_phases.json`という手動escape hatchが既に存在する理由と同じ）。
  ページ単位のチェックポイントは根本原因を解消せず、被害範囲を縮小するだけ。
- `phaseGroup.sets`を非常に小さい`per_page`（例: 1）で叩き、「1件ずつページング
  する」ことで新規クエリを不要にする。却下: phaseGroupのページング機構を解決する
  ためのリクエストあたりオーバーヘッドは依然として発生する。加えて
  `SETS_PER_PAGE_FALLBACKS = (50, 25, 10, 5, 3, 1)`の通り、`per_page=1`は既存の
  フォールバック梯子の最終手段であり、既知として、問題のあるphaseGroupでは
  それでも失敗することがある（`excluded_phases.json`の存在理由）。set_idで直接
  取得すればphase/poolのページングそのものを完全に回避できる。

## 3. 1リクエストで複数setをバッチ処理する

**決定**: 未取得のsetは、同じ`set(id:)`フィールドに対するGraphQLエイリアス
（例: `s0: set(id: $id0) { ... } s1: set(id: $id1) { ... }`）を使って、1リクエスト
あたり小さなバッチ単位で取得する。バッチサイズは既存の
`SETS_PER_PAGE_FALLBACKS`の値と同程度の桁数（数十、数百ではない）とし、正確な
サイズはPhase 2（tasks）で実測されたcomplexityコストに基づいて調整する。
一貫性の観点から、`_fetch_sets_with_fallback`の既存パターンに倣ったフォールバック
戦略（サイズを縮小しながらリトライ）を用いる（憲法Principle V: 独自のリトライ
ロジックは書かないが、「1リクエストに何set含めるか」というリクエスト整形は
本機能固有の関心事であり、リトライ/バックオフとは別物）。

**根拠**: 1リクエストあたりset 1件のバッチであれば正しさは保証できるが、
`grand_slum`規模のイベントを完全にバックフィルするには数千回もの個別HTTP
往復（加えてリクエスト間の`page_delay`）が必要になり、GitHub Actionsの60分の
jobタイムアウト——本セッション中の調査で、これが独立に既に2026-08-02、
2026-08-09、2026-08-16の`data_gap_check`実行を`Download`ステップの途中で強制
終了させていたことが判明済み——に再び抵触するリスクが高い。バッチ化することで、
リクエストあたりオーバーヘッドを償却しつつ、複雑さを（バッチサイズ×set1件あたり
の固定コスト）として予測可能な範囲に保てる。旧方式ではcomplexityが*イベントの*
総set数に比例して増大していたのとは対照的である。

**検討した代替案**:
- フォールバック無しの固定バッチサイズ。却下: イベントによってset単体あたりの
  complexity（ゲーム数・キャラクター選択数が多いsetとシンプルなsetなど）が異なる
  ため、単一の固定定数よりも（`SETS_PER_PAGE_FALLBACKS`を踏襲した）フォール
  バック梯子の方が堅牢であり、`download.py`の他部分が既にこの種の問題をどう
  扱っているかとも一貫する。

## 4. プレースホルダーレコードの表現と未取得分の検出

**決定**: `matches.json`のプレースホルダーレコードは`{"set_id": <int>}`のみを
持つdictとする。完了済みレコードは、今日の既存の形状（`winner_id`、`loser_id`、
`winner_score`、...、`details`）に、新規の`set_id`フィールドを加えたものとする。
「未取得」は、`matches.json`の`data`リストの中から、キーが`set_id`のみのレコード
（同義として`winner_id`を持たないレコード）を走査して求める。プレースホルダーの
置き換えは、`set_id`をキーとしたリストの「その場」更新であり、追記ではない
（FR-008）。

**根拠**: spec.mdのKey Entitiesの記述（「`set_id`のみが投入されている」 vs
フル形状）と正確に一致し、`matches.json`を自己完結させられる——同期を取る必要
のある2つ目のファイルや派生インデックスが不要になる。

**検討した代替案**:
- 全フィールドを持たせつつ値を`null`にするプレースホルダー（例:
  `{"set_id": 1, "winner_id": None, ...}`）。却下: 完了済みレコードでも既に
  発生し得る正当な`null`値（例: `docs/data_model.md`が既に注記している通り、
  doubles/crew等では`winner_id`/`loser_id`が`null`になり得る参加者リンク無し
  エントラントのケース）との区別が曖昧になる。キー存在チェック
  （`"winner_id" not in record`）であれば、値ベースのチェック
  （`record["winner_id"] is None`）と違い、完了済みレコードの正当な`null`と
  混同されない。

## 5. `EVENT_DATA_VERSION`の引き上げとバックフィルへの統合

**決定**: `scripts/utils.py`の`EVENT_DATA_VERSION`を`5`から`6`に引き上げる。
既存イベント（`matches.json`レコードに`set_id`が無いもの、または旧来の
all-or-nothing取得により中断されて`attr.json`自体が存在しないもの）は、
`scripts/fetch/backfill_schema_version.py`の既存の巡回スキャンでバックフィル
する——新規の移行スクリプトは作らない。このスキャナは、（`attr.json`だけでなく）
`standings.json`の存在によってもディレクトリを発見するよう既に実装されており
（`iter_event_dirs()`のdocstring参照）、これはまさに中断済みイベント（現状:
`attr.json`が無い）を見つけ出すためのものである——この性質のおかげで、FR-011の
バックフィルは、旧バグにより不完全なまま放置されたイベントが、新しい逐次取得
経路で再処理された際に自然に拾われる。

**根拠**: 憲法Principle Iが求めている（「既存データへの影響がある場合は...
MUST 移行する」）まさにその仕組みであり、かつこの種の変更のためにこの
コードベースに既に存在している仕組みを再利用するものであり、並行する一回限りの
バックフィルツールを新設しない。

## 6. `large-event-skip`／`fetch_large_event`の廃止

**決定**: `.github/workflows/fetch_large_event.yml`を削除する。
`data_gap_check.yml`の`max_pages`/`skip_report_path`/`MaxPagesExceededError`/
`_record_skip`の仕組みと「Create large-event-skip issue」ステップを削除する。
set取得の一括`event.sets`/`phaseGroup.sets`ページングをID単位の取得に置き換える
ことで、set取得由来の`MaxPagesExceededError`はどのコードパスからも発生し得なく
なるため。

**根拠**: FR-012/013（spec.md）——`/speckit-clarify`の中でユーザーが見落としでは
なく意図的なスコープ判断として確認済み。本セッション中の調査で、
`large-event-skip`のissue作成経路は実運用で一度も発火していなかったことが既に
判明している（リポジトリに`large-event-skip`ラベル自体が存在しない）。原因は
`download_all_tournaments`の`finish_date`到達時の早期returnという別件のバグで、
これは本フィーチャーとは別に既に修正済みである——つまり廃止するのは、機能して
いた安全網ではなく、実運用上は死んでいた経路である。

**注記**: `MaxPagesExceededError`と`max_pages`自体は、本機能が引き続き使用する
他のページングクエリ（§1の新規ID専用set一覧クエリ、`standings`、`seeds`）には
今後も関係し得る——廃止するのは*set詳細取得*が引き金となるskip/report/issue
経路のみであり、`max_pages`という仕組み自体ではない。

## 7. `scripts/fix/validate_data.py`との相互作用

**調査結果（設計判断ではなく、コードを読んで確認した事実）**:
`validate_data.py`は`events_root.rglob("attr.json")`によってイベント
ディレクトリを発見しており、`attr.json`が無いディレクトリを訪れることは無い。
`attr.json`はプレースホルダーが1件も残っていない場合にのみ書き込まれる
（FR-009）ため、逐次的に埋められている途中のイベントは今日のバリデータからは
不可視であり、部分的に埋まった`matches.json`から誤検知エラーが出ることは無い。
`validate_data.py`の発見ロジックを変更する必要は無い。

**任意の強化（推奨だが必須ではない）**: あるイベントの`attr.json`が存在する
場合、`validate_data.py`側で、そのイベントの`matches.json`にプレースホルダー
形状のレコード（`winner_id`が欠落したレコード）が1件も無いことを追加でassert
してもよい——将来、仮に`attr.json`が時期尚早に書き込まれるバグが混入した場合の
防御的な不変条件チェックとなる。ブロッキングな要件ではなく、タスク候補として
残す。

## 8. 既存のリトライ/バックオフとの整合（憲法Principle V）

**決定**: 新設する2つのクエリ（§1のID一覧取得、§2/§3のIDによる詳細取得）は
どちらも、`download.py`が他の全クエリで既に使っているのと同じヘルパー——単発
リクエストには`fetch_data_with_retries()`、ページングするlistingクエリには
`fetch_all_nodes()`——経由で発行する。新しいリトライ/バックオフ/complexity検知
ロジックは一切書かない。

**根拠**: 憲法Principle Vによる直接の要求であり、これにより
`fetch_data_with_retries()`の既存の429/5xxハンドリング
（`docs/startgg_design.md`「ページングとリトライ」節）が、追加の作業無しで
新規クエリにもそのまま適用される。
