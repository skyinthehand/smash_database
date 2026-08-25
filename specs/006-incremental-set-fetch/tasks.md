---

description: "Task list template for feature implementation"
---

# Tasks: setごとの逐次取得によるマッチ取得とリカバリ

**入力**: `/specs/006-incremental-set-fetch/` の設計ドキュメント

**前提条件**: plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md（全て揃っている）

**テスト**: 本プロジェクトの憲法Principle III（マージ前の検証ゲート、NON-NEGOTIABLE）により、
新しいデータ形状・フィールドを追加する場合は対応するテストの追加が MUST。よって以下の
テストタスクは「要求があれば」ではなく必須として含めている。

**構成**: タスクはUser Storyごとにグループ化し、各Storyを独立に実装・テストできるようにする。

## フォーマット: `[ID] [P?] [Story] 説明`

- **[P]**: 並行実行可能（別ファイル、依存関係なし）
- **[Story]**: どのUser Storyに属するか（US1, US2, US3, US4）
- 各タスクの説明には具体的なファイルパスを含める

## パスの前提

本フィーチャーは既存の単一Pythonスクリプトプロジェクトへの変更であり、新しいディレクトリは
追加しない（plan.md「構成方針」参照）。変更対象は主に `scripts/fetch/download.py`、
`scripts/queries.py`、`scripts/utils.py`、`scripts/test/test_download.py`、
`.github/workflows/`、`docs/`。

---

## Phase 1: Setup（下調べ）

**目的**: 実装を始める前に、既存コードの現状を確認し、後続タスクの前提を固める。

- [ ] T001 [P] `scripts/utils.py` の `EVENT_DATA_VERSION` の現在値（5）と、それを参照している
      全箇所（`scripts/fetch/download.py`、`scripts/fetch/backfill_schema_version.py`、
      `scripts/fetch/download_specific_event.py`、`scripts/test/test_download.py`、
      `scripts/test/test_backfill_schema_version.py`）を洗い出し、T010でのバージョン引き上げに
      漏れが無いようにする
- [ ] T002 [P] `scripts/fetch/download_specific_event.py` と `scripts/fetch/refresh_event_dir.py`
      を確認し、`download.py` の一括sets取得ロジックを独自に再実装している箇所（例:
      `download_specific_event.py` 内の `fetch_all_sets()`/`download_all_set()`）を特定する。
      Phase 8（Polish）でこれらを本フィーチャーの一括優先・失敗時フォールバック方式に合わせる
      か、対象外とする場合はその理由を記録するための下調べ

**チェックポイント**: Foundationalフェーズ開始前の前提確認が完了

---

## Phase 2: Foundational（全User Storyの前提となる基盤）

**目的**: どのUser Storyの実装を始める前にも完了していなければならない、共通の基盤部分

**⚠️ CRITICAL**: このフェーズが完了するまで、どのUser Storyの実装も開始できない

- [ ] T003 [P] `scripts/utils.py` の `EVENT_DATA_VERSION` を `5` から `6` に引き上げる（FR-011,
      data-model.md「共有定数」節）
- [ ] T004 [P] `scripts/queries.py` に `get_event_set_ids_query()` を追加する: `event(id:
      $eventId)` 配下の `sets(page, perPage) { pageInfo { total totalPages } nodes { id } } }`
      のみを要求するID専用の軽量クエリ（既存の `_SET_NODE_FIELDS`/`_SET_NODE_FIELDS_LIGHT` は
      使わない）。FR-003(a)、research.md §1
- [ ] T005 [P] `scripts/queries.py` に、複数の`set_id`をGraphQLエイリアスでバッチ取得するための
      クエリビルダー関数（例: `get_sets_by_ids_query(set_ids)`。ルートの`set(id: ID!)`フィールド
      を`s0: set(id: $id0) { ... } s1: set(id: $id1) { ... }`の形でエイリアスし、既存の
      `_SET_NODE_FIELDS`をそのまま再利用）を追加する。FR-003(c)、research.md §2/§3
- [ ] T006 `scripts/fetch/download.py` に、マッチレコードがプレースホルダーかどうかを判定する
      ヘルパー `is_placeholder_record(record)`（`"winner_id" not in record` で判定。
      research.md §4の「キー存在チェック」方針）を追加する。FR-005, FR-008
- [ ] T007 `scripts/fetch/download.py` に、あるイベントの`matches.json`データと既知の
      `set_id`一覧から未取得の`set_id`集合を求めるヘルパー `outstanding_set_ids(matches_data,
      known_set_ids)`（T006の`is_placeholder_record`を利用）を追加する。FR-008
- [ ] T008 `scripts/fetch/download.py` の `write_matches()` を、常に新規上書きするのではなく
      既存の`matches.json`を読み込んで`set_id`をキーに「その場」でレコードを追加・置換できる
      よう変更する（新規追加時は末尾に追加、既存の`set_id`が来たら該当レコードを置き換える。
      追記による重複は発生させない）。FR-009
- [ ] T009 `scripts/fetch/download.py` に、あるイベントが既に逐次取得（フォールバック）モードに
      入っているかどうかを判定するヘルパー `event_in_fallback_mode(event_dir)`（`matches.json`
      が存在し、かつ`attr.json`が存在しない場合に`True`）を追加する。FR-004

**チェックポイント**: 基盤が整い、以降のUser Storyの実装を開始できる

---

## Phase 3: User Story 1 - 大規模イベントが中断されてもデータを失わない (Priority: P1) 🎯 MVP

**Goal**: 一括取得が失敗した場合にのみ逐次取得（プレースホルダー投入＋`set(id:)`による
バッチ取得）にフォールバックし、途中で中断されても既に取得済みのマッチレコードを失わず、
次回の実行で未取得分のみを再開できるようにする。

**Independent Test**: 一括取得が失敗するよう仕向けた（モックした）イベントに対して取得を
実行し、`matches.json`に一部の完了済みレコードとプレースホルダーが混在した状態で処理を
打ち切っても、完了済みレコードが失われないことを確認する。

### User Story 1のテスト（憲法Principle IIIによりMUST） ⚠️

> 実装前にまずテストを書き、FAILすることを確認してから実装に進むこと

- [ ] T010 [P] [US1] `scripts/test/test_download.py` に、一括sets取得が失敗した場合に
      `matches.json`が既知の全`set_id`について1件ずつプレースホルダーレコードのみで
      投入され、完了済みレコードが1件も無い状態になることを確認するテストを追加する
      （FR-003）
- [ ] T011 [P] [US1] `scripts/test/test_download.py` に、逐次取得中の中断（バッチ取得の
      途中で例外を発生させるモック）をシミュレートし、それまでに置き換え済みの完了済み
      レコードが`matches.json`に残り、残りのプレースホルダーはプレースホルダーのまま
      残ることを確認するテストを追加する（FR-006, SC-002）
- [ ] T012 [P] [US1] `scripts/test/test_download.py` に、既にプレースホルダーと完了済み
      レコードが混在する`matches.json`を持つイベントを再処理した場合、まだプレースホル
      ダーの`set_id`のみが取得され、既に完了済みのレコードは変化せず、同じ`set_id`の
      レコードが重複して追記されないことを確認するテストを追加する（FR-007, FR-009,
      SC-003）
- [ ] T013 [P] [US1] `scripts/test/test_download.py` に、既に`matches.json`が存在し
      `attr.json`が存在しないイベント（＝フォールバックモード中）を再処理する際、
      一括sets取得クエリが一切呼ばれない（`event_in_fallback_mode()`により一括取得を
      スキップする）ことを確認するテストを追加する（FR-004, FR-015）

### User Story 1の実装

- [ ] T014 [US1] `scripts/fetch/download.py` に `fetch_set_ids_for_event(event_id)` を
      追加する: T004の`get_event_set_ids_query()`を`fetch_all_nodes()`経由で呼び出し、
      そのイベントの全`set_id`をページングして取得する（FR-003(a)）
- [ ] T015 [US1] `scripts/fetch/download.py` に `fetch_set_details_by_ids(set_ids)` を
      追加する: T005のクエリビルダーを使い、未取得の`set_id`を小さなバッチ単位で
      `fetch_data_with_retries()`経由で取得する。既存の`SETS_PER_PAGE_FALLBACKS`と
      同様の考え方でバッチサイズを縮小しながらリトライするフォールバック戦略を実装する
      （FR-003(c)、research.md §3。憲法Principle V: 独自のリトライ/バックオフは書かず
      `fetch_data_with_retries()`を経由する）
- [ ] T016 [US1] `scripts/fetch/download.py` の`download_all_set()`を変更する: まず
      既存の一括`fetch_all_sets()`を試み（FR-001）、成功すれば各レコードに`set_id`
      （既存の`id`フィールドから抽出）を含めて直接`write_matches()`で書き込み、
      プレースホルダーは一切生成しない（FR-002）。一括取得が
      `MaxPagesExceededError`または既存のcomplexity超過による`FetchError`で失敗した
      場合のみ、T014でset_id一覧を取得し、T008の「その場更新」対応版`write_matches()`
      でプレースホルダーを投入した上で、T007の`outstanding_set_ids()`で未取得分を求め、
      T015でバッチ取得して置き換える（FR-003, FR-006, FR-009）
- [ ] T017 [US1] `scripts/fetch/download.py` の `download_all_tournaments()`
      内のイベント処理ループ（`download_all_set(event_id, entrant2user, event_dir,
      max_pages=max_pages)` を呼んでいる箇所）で、T009の`event_in_fallback_mode()`が
      `True`を返す場合は一括取得を呼び出さず、直接プレースホルダーの詳細取得のみを
      行うよう分岐させる（FR-004）

**チェックポイント**: 大規模イベントが中断されてもデータを失わず、単独でテスト可能な
状態になる（MVP）

---

## Phase 4: User Story 2 - 手動リカバリ無しで大規模イベントが完了する (Priority: P2)

**Goal**: 一括取得の失敗を「人手が気づいてissueを見て手動でワークフローを再実行する」
対象として扱う既存の仕組み（large-event-skip issue自動作成、`fetch_large_event`手動
ワークフロー）を廃止し、User Story 1のフォールバック機構だけで大規模イベントが完了する
ようにする。

**Independent Test**: 一括取得の上限を超える大規模イベントを、手動ワークフローの起動を
一切行わず、`download.py`の通常のスケジュール実行相当の呼び出しのみで完了状態まで
到達させ、`large-event-skip`関連のissueやレポートファイルが一切生成されないことを
確認する。

### User Story 2のテスト（憲法Principle IIIによりMUST） ⚠️

- [ ] T018 [P] [US2] `scripts/test/test_download.py` に、一括sets取得が
      `MaxPagesExceededError`で失敗しても、`skipped_events`への記録や
      `skip_report_path`ファイルへの書き出しが一切発生せず、代わりにUser Story 1の
      フォールバック処理（プレースホルダー投入）が実行されることを確認するテストを
      追加する（FR-013）
- [ ] T019 [P] [US2] `scripts/test/test_download.py` の既存テスト
      `test_download_all_tournaments_records_event_path_before_fetch_even_if_later_step_fails`
      （`MaxPagesExceededError`を`download_all_set`の`side_effect`にしているテスト）を、
      新しい「フォールバックに入る」挙動を検証する内容に更新する

### User Story 2の実装

- [ ] T020 [US2] `scripts/fetch/download.py` の `download_all_tournaments()`
      から、sets取得（`download_all_set`呼び出し）を包む
      `except MaxPagesExceededError: _record_skip(...); continue` ブロックを削除し、
      T016で実装したフォールバック処理に完全に置き換える（FR-013）。`_record_skip`
      関数と`skipped_events`リスト、`skip_report_path`引数・CLI引数
      （`--skip_report_path`）、`_record_skip`関連のimportを削除する
- [ ] T021 [US2] `scripts/fetch/download.py` の`standings`/`seeds`取得を包む
      `except MaxPagesExceededError: _record_skip(...); continue` ブロックからも
      `_record_skip(...)`呼び出しを削除する（`continue`によるその場スキップ自体は
      維持する——`skip_report_path`という出力先ワークフローステップが無くなるため、
      レポート自体を作る意味が無くなったのみで、動作自体はcontinueのまま変えない）
- [ ] T022 [US2] `.github/workflows/fetch_large_event.yml` を削除する（FR-013）
- [ ] T023 [US2] `.github/workflows/data_gap_check.yml` から、「Create large-event-skip
      issue」ステップ、`--max_pages`/`--skip_report_path`引数（sets取得のレポート用途で
      あった箇所）、および関連する`gh label create`/`gh issue create`呼び出しを削除する
      （FR-013）

**チェックポイント**: 大規模イベントに手動リカバリが不要になり、User Story 1と合わせて
単独でテスト可能

---

## Phase 5: User Story 3 - 未取得のsetを追跡できる（逐次取得モード時） (Priority: P3)

**Goal**: フォールバックモードにおいて、`matches.json`自体（プレースホルダー/完了済み
レコードの混在）だけを見れば、未取得のsetが何かを判別できることを保証する。

**Independent Test**: 一括取得が失敗したイベントについて、set一覧のみを取得し
（詳細はまだ取得しない）、`matches.json`にstart.ggが報告するset数ちょうどの
プレースホルダーレコードが生成され、完了済みレコードが1件も無いことを確認する。

**Note**: このStoryの中核となる仕組み（set一覧取得→プレースホルダー投入→未取得分の
走査）は、User Story 1の実装（T014, T007, T016）で既に構築されている——spec.mdが
明記する通り、これはUser Story 1のリカバリを成立させる前提条件そのものであるため。
本フェーズでは、その挙動をUser Story 1とは独立した観点から検証するテストのみを追加する。

### User Story 3のテスト（憲法Principle IIIによりMUST） ⚠️

- [ ] T024 [P] [US3] `scripts/test/test_download.py` に、一括取得の失敗後、set一覧
      取得クエリのみをモックしてset詳細取得はまだ行わない状態で`download_all_set()`
      （またはT016で追加した内部関数）を呼び出し、`matches.json`のレコード数が
      set一覧の件数と厳密に一致し、全レコードがプレースホルダー（`winner_id`を
      持たない）であることを確認するテストを追加する（FR-003(a)(b)、spec.md User
      Story 3 Independent Test）
- [ ] T025 [P] [US3] `scripts/test/test_download.py` に、`outstanding_set_ids()`
      （T007）が、プレースホルダーと完了済みレコードが混在する`matches.json`から、
      プレースホルダーの`set_id`のみを過不足なく返すことを確認する単体テストを
      追加する（FR-008）

**チェックポイント**: 未取得setの追跡が独立した観点からも検証済みになる（実装自体は
User Story 1で完了しているため、実装タスクは無し）

---

## Phase 6: User Story 4 - マッチレコードが元のsetまで追跡可能である (Priority: P4)

**Goal**: 一括取得経路・逐次取得経路のどちらで生成されたマッチレコードも、`set_id`
フィールドでstart.ggのsetと一意に突合できるようにする。

**Independent Test**: 任意のイベント（一括取得・逐次取得のどちらでも）を取得し、
`matches.json`の全レコードが実在する`set_id`を持ち、重複が無いことを確認する。

**Note**: 逐次取得（フォールバック）経路での`set_id`付与は、User Story 1（T016）で
既に実装済み。本フェーズで残っているのは、一括取得（今日と同じ、大多数のイベントが
通る経路）が今のところ`set_id`を書き込んでいない点のみ。

### User Story 4のテスト（憲法Principle IIIによりMUST） ⚠️

- [ ] T026 [P] [US4] `scripts/test/test_download.py` に、一括sets取得が成功した場合に
      `write_matches()`が書き込む各レコードに、そのsetのstart.gg上の`id`と一致する
      `set_id`フィールドが含まれることを確認するテストを追加する（FR-002, FR-005）
- [ ] T027 [P] [US4] `scripts/test/test_download.py` に、同一イベントの`matches.json`
      内で`set_id`が重複しないことを、一括取得経路・逐次取得経路の両方について
      確認するテストを追加する（SC-004）

### User Story 4の実装

- [ ] T028 [US4] `scripts/fetch/download.py` の`write_matches()`内、一括取得経路で
      `match_data`辞書を組み立てている箇所に、`"set_id": node.get("id")`を追加する
      （FR-002, FR-005）

**チェックポイント**: 全User Story（P1〜P4）が独立にテスト可能な状態で完了

---

## Phase 7: バックフィル経路の検証（FR-011, FR-012 — 専用User Storyには対応しない横断的事項）

**目的**: spec.mdのFR-011/FR-012およびAssumptionsが要求する「既存イベントへの
バックフィルは新規の移行スクリプトなしで、既存の`backfill_schema_version.py`巡回
サイクルにそのまま乗る」という前提を検証する。research.md §5の通り、
`backfill_schema_version.py`は`download.py`の関数（`download_all_set`等）を直接
importして呼んでいるため、Phase 2（T003のバージョン引き上げ）とPhase 3
（T016の`download_all_set`変更）だけで自動的に対応済みになり、このファイル自体への
コード変更は不要と想定される。

- [ ] T029 [P] `scripts/test/test_backfill_schema_version.py` に、
      `event_data_version`が`6`未満（または`attr.json`が存在しない）イベントが
      巡回対象として検出され、`download_all_set`経由で再取得された結果
      `matches.json`の全レコードに`set_id`が付与されることを確認するテストを
      追加する（FR-011, FR-012）
- [ ] T030 `scripts/fetch/backfill_schema_version.py`を通しで確認し、T003/T016の
      変更のみで意図通り動作するか、追加の変更が必要かを判断する。必要であれば
      最小限の変更を加える

**チェックポイント**: 既存イベントのバックフィル経路が新設計で機能することを確認済み

---

## Phase 8: Polish & Cross-Cutting Concerns（仕上げ）

**目的**: 憲法Principle Iが要求するドキュメント同期、および横断的な仕上げ

- [ ] T031 [P] `docs/data_model.md`の`matches.json`節を更新する: プレースホルダー
      レコード形状（`set_id`のみ）、`set_id`フィールドの追加、
      `EVENT_DATA_VERSION`が`6`になったことを記載する（憲法Principle I）
- [ ] T032 [P] `docs/startgg_design.md`に、T004/T005で追加した2つの新規クエリ
      （ID専用set一覧取得、`set(id:)`によるバッチ詳細取得）の目的とレスポンス例を
      追記する
- [ ] T033 [P] `docs/flow.md`のMermaid図・説明を確認し、large-event-skip関連の
      記述があれば、User Story 2で廃止した内容に合わせて更新する
- [ ] T034 [P] `docs/fix.md`に、「逐次取得モードにおけるset ID一覧取得自体が
      完走できない場合、専用の手動escape hatchは存在しない」という残存リスク
      （spec.md Edge Cases）を記録する（憲法データ保存規約: 既知の不完全な点は
      コードコメントではなく`docs/fix.md`へ）
- [ ] T035 T002の下調べに基づき、`scripts/fetch/download_specific_event.py`の
      独自のsets取得実装を、本フィーチャーの一括優先・失敗時フォールバック方式に
      合わせて更新するか、対象外とする場合はその理由を`docs/fix.md`または
      コミットメッセージに明記する
- [ ] T036 `python -m unittest scripts.test.test_download scripts.test.test_validate_data
      scripts.test.test_backfill_schema_version -v` を実行し、全テストがpassする
      ことを確認する（憲法Principle III）
- [ ] T037 [quickstart.md](./quickstart.md)の各シナリオ（特にシナリオ0「小規模
      イベントは今日と同じ経路のまま」とシナリオ1「中断された取得がデータを
      失わない」）を実行し、想定通りの挙動になることを確認する

**チェックポイント**: 本フィーチャー全体が完了し、ドキュメントも同期済み

---

## Dependencies & Execution Order（依存関係と実行順序）

### フェーズ間の依存関係

- **Setup（Phase 1）**: 依存なし。すぐ開始できる
- **Foundational（Phase 2）**: Setup完了後。全User Storyをブロックする
- **User Stories（Phase 3〜6）**: 全てFoundational完了後に開始可能
  - User Story 1（P1）が他の全Storyの基盤（プレースホルダー機構）を実装するため、
    実質的にはUser Story 1を最初に終わらせるのが最も効率的
  - User Story 2（P2）はUser Story 1の完了に依存する（フォールバック処理が無いと、
    置き換えるべき`_record_skip`分岐が無い）
  - User Story 3（P3）はUser Story 1の実装に依存する（追加実装は無く、検証のみ）
  - User Story 4（P4）はUser Story 1と独立に実装可能（一括経路への`set_id`追加は
    単独の変更）だが、User Story 1と同じファイル（`download.py`の`write_matches()`）
    を触るため、コンフリクトを避けるならUser Story 1の後に着手するのが安全
- **バックフィル検証（Phase 7）**: User Story 1・4の完了後
- **Polish（Phase 8）**: 実施したい全User Story・Phase 7の完了後

### User Story間の依存関係

- **User Story 1（P1）**: Foundational完了後に開始可能。他Storyへの依存なし
- **User Story 2（P2）**: User Story 1の実装（T016のフォールバック処理）に依存
- **User Story 3（P3）**: User Story 1の実装に依存（実装タスクは無く、検証のみ）
- **User Story 4（P4）**: Foundational完了後に開始可能。機能的には他Storyと独立だが、
  同一ファイルの同一関数（`write_matches()`）を編集するため、User Story 1の後に
  実施するとコンフリクトが少ない

### 各User Story内

- テスト（Principle IIIによりMUST）は実装前に書き、FAILすることを確認する
- ヘルパー関数（Foundational）→ 個々の取得関数 → 呼び出し元への配線、の順
- Storyが完了してから次の優先度のStoryに進む

### 並行実行の機会

- Setup（Phase 1）のT001, T002は並行実行可能
- Foundational（Phase 2）のT003, T004, T005は並行実行可能（別ファイル）。T006〜T009は
  同一ファイル（`download.py`）内の別関数だが、依存関係が無ければ並行編集も可能
- 各User Storyの[P]付きテストタスクは並行実行可能
- User Story 3・4は、User Story 1完了後であれば並行して着手可能（3は検証のみ、4は
  別経路の変更のため）

---

## Parallel Example: User Story 1

```bash
# User Story 1のテストをまとめて起票・実行:
Task: "scripts/test/test_download.py に一括取得失敗時のプレースホルダー投入を確認するテストを追加"
Task: "scripts/test/test_download.py に中断時のデータ保持を確認するテストを追加"
Task: "scripts/test/test_download.py に再開時の未取得分のみ取得を確認するテストを追加"
Task: "scripts/test/test_download.py にフォールバックモード中の一括取得スキップを確認するテストを追加"
```

---

## Implementation Strategy（実装戦略）

### まずMVP（User Story 1のみ）

1. Phase 1: Setup を完了する
2. Phase 2: Foundational を完了する（CRITICAL — 全Storyをブロックする）
3. Phase 3: User Story 1 を完了する
4. **一旦停止して検証**: User Story 1単独でテストする（quickstart.mdシナリオ1）
5. 準備ができていればデプロイ/デモ

### 段階的デリバリー

1. Setup + Foundational を完了 → 基盤が整う
2. User Story 1 を追加 → 単独でテスト → デプロイ/デモ（MVP！大規模イベントの
   データ消失が解消される）
3. User Story 2 を追加 → 単独でテスト → デプロイ/デモ（手動リカバリが不要になる）
4. User Story 3・4 を追加 → 単独でテスト → デプロイ/デモ（追跡性・検証の強化）
5. Phase 7（バックフィル検証）・Phase 8（Polish）を完了する
6. 各Storyが、前のStoryを壊すことなく価値を積み上げる

---

## Notes（メモ）

- [P] タスク = 別ファイル、依存関係なし
- [Story] ラベルはタスクを特定のUser Storyに紐付け、トレーサビリティを保つ
- 各User Storyは独立に完了・テスト可能であるべき
- 実装前にテストがFAILすることを確認する
- タスクごと、または論理的なまとまりごとにコミットする
- 各チェックポイントで一旦立ち止まり、Storyが独立して機能することを検証する
- 避けるべきこと: 曖昧なタスク、同一ファイルへの競合する変更、Storyの独立性を
  壊すStory間の依存関係
