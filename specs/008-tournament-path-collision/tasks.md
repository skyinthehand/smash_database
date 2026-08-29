---

description: "Task list template for feature implementation"
---

# Tasks: 同日同名トーナメントの保存先パス衝突の解消

**Input**: Design documents from `/specs/008-tournament-path-collision/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: 憲法Principle III(マージ前の検証ゲート、NON-NEGOTIABLE)により、
本フィーチャーのテストタスクは必須として含める。

**Organization**: タスクはUser Story(spec.md のPriority順)ごとにグループ化
し、それぞれ独立して実装・検証できるようにする。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並行実行可能(別ファイル・依存関係なし)
- **[Story]**: どのUser Storyに属するか(US1〜US5)
- 各タスクには具体的なファイルパスを含める

## Path Conventions

既存の単一プロジェクト構成(`scripts/`直下、`data/`はデータ専用)。新規
ディレクトリの作成は不要。

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: 全User Storyが利用する、命名調整の共通プリミティブ。

**⚠️ CRITICAL**: このフェーズが完了するまで、いずれのUser Storyの実装も
開始できない。

- [X] T001 `disambiguate_event_name(tournament_name: str, tournament_id: int) -> str`
  を `scripts/fetch/download.py` に実装する(`research.md` Decision 4:
  `f"{tournament_name}_({tournament_id})"` に既存の空白/スラッシュ置換
  ルールを適用)。
- [X] T002 `build_path_index(tournaments: dict) -> dict[str, tuple[int, int]]`
  を `scripts/fetch/download.py` に実装する(`path -> (tournament_id, event_id)`
  の逆引き辞書、`research.md` Decision 1)。
- [X] T003 T001・T002の単体テストを `scripts/test/test_download.py` に追加する
  (通常の名前変換、`tournament_id`を含む調整後の名前の形式、逆引き辞書の
  構築結果を検証)。

**Checkpoint**: 共通プリミティブが揃い、以降のUser Story実装を開始できる。

---

## Phase 2: User Story 1 - 同日同名の別大会によるデータ破損を未然に防ぐ (Priority: P1) 🎯 MVP

**Goal**: 通常のクロールで、同一保存先パスに解決される別tournament_idの
イベントを検出し、片方(判定基準はUS2で洗練するまでは「後から検出された
側」)を重複しない名前へ調整する。

**Independent Test**: 同じ地域・開催日・大会名を持つtournament_idの異なる
2大会分を通常のクロールで取得し、実行後に両者が別ディレクトリに保存され、
`tournaments.jsonl` の記載パスが実体と一致していることを確認する。

### Implementation for User Story 1

- [X] T004 [US1] `download_all_tournaments()` 内、`event_dir = get_event_directory(...)`
  直後(既存の `load_excluded_event_ids()` チェックと同じ挿入点)に、
  T002の `build_path_index()` を用いた衝突検出を `scripts/fetch/download.py`
  に追加する。
- [X] T005 [US1] `download_by_ids()` にも同じ衝突検出を `scripts/fetch/download.py`
  に追加する。
- [X] T006 [US1] 衝突が検出された場合、新たに見つかった側の保存先を
  T001の `disambiguate_event_name()` で調整してから
  `update_event_registration()` による登録を行うベースラインの分岐を
  `scripts/fetch/download.py` に実装する(参加者数比較はUS2で追加)。
- [X] T007 [P] [US1] 衝突検出・ベースライン調整の単体テストを
  `scripts/test/test_download.py` に追加する(衝突時は新規側が調整され、
  衝突が無い場合は従来通り無調整であることを検証)。
- [X] T008 [US1] `download_all_tournaments()`/`download_by_ids()` への統合
  テストを `scripts/test/test_download.py` に追加する(衝突を再現した
  2大会分のデータを流し、両者が別ディレクトリに保存され、
  `tournaments.jsonl` の記載パスが実体と一致することを検証。FR-007の
  「衝突が無ければ挙動を変えない」ことも検証)。

**Checkpoint**: 通常のクロールにおける新規衝突が(どちらが調整されるかは
未定でも)確実に防止される。

---

## Phase 3: User Story 2 - 参加者数の多い大会の名前は変えない (Priority: P2)

**Goal**: 衝突解決の判定基準を、参加者数が多い方を優先して名前を維持する
決定的なロジックに置き換え、参加者数が未確定な場合は最終確定を遅延させる。

**Independent Test**: 参加者数が異なる2つの同日同名大会を衝突させ、参加者数
の少ない方だけが調整され、多い方は元の名前のまま保存されることを確認する。
3件目のさらに参加者数が多い衝突を追加しても、既に確定済みの保存先が
再度変更されないことも確認する。

### Implementation for User Story 2

- [X] T009 [US2] `resolve_path_collision(naive_event_dir, tentative_new_dir, new_num_entrants, new_tournament_id, existing_tournament_id, existing_event, tournaments, settled_tournament_ids)`
  を `scripts/fetch/download.py` に実装する(呼び出し元は衝突検出時点で
  `tentative_new_dir = disambiguate_event_name()`適用済みの暫定ディレク
  トリを先に計算し、`download_standings()`以降の書き込みはすべてそこへ
  行っておく。既存データが置かれた`naive_event_dir`へ書き込む前に比較
  結果を確定させるため。`research.md` Decision 2の実装時訂正)。
  `existing_tournament_id` が
  `settled_tournament_ids`(取得処理の開始時点で確定済みだった
  tournament_idの集合。T011が構築)に含まれる場合は、参加者数比較を
  行わず常に新規側のみを調整する(FR-005の恒久ロック)。含まれない場合
  (=既存側も同一の取得処理内でまだ確定していない)のみ、既存側の参加者数
  を `existing_event["path"]/attr.json` の `num_entrants` から読み取り
  (読めない場合は `0` 扱い)、参加者数が多い方は無調整、同数の場合は
  `tournament_id` が大きい方を調整対象とする決定的なタイブレークで比較
  する。`research.md` Decision 3(ユーザーフィードバック2026-08-29による
  再訂正)。
- [X] T010 [US2] T009の関数内、`settled_tournament_ids` に含まれない
  (同一取得処理内でまだ確定していない)既存側が調整対象になる場合の
  処理を `scripts/fetch/download.py` に実装する(既存イベントのディレク
  トリを実際にリネームし、`tournaments` 辞書内の該当エントリの `path`
  を更新する。既に調整名を持っていた場合は本来の名前に戻すのではなく、
  新規側が無調整の勝者になり既存側が新たに調整名を持つ入れ替えとなる。
  既存の安全なリロケーションパターン(`cleanup_relocated_directory()`)
  を踏襲)。
- [X] T011 [US2] `download_all_tournaments()`/`download_by_ids()` を、
  `read_tournaments_jsonl()` 直後(この取得処理自身がまだ何も新規登録
  していない時点)に、その時点の `tournaments` 辞書のキー集合を
  `settled_tournament_ids` としてスナップショットし(T009参照)、衝突
  検出時には早期の `update_event_registration()` 呼び出しをスキップし、
  `tentative_new_dir`(T001の`disambiguate_event_name()`適用済みの
  暫定ディレクトリ)へ `download_standings()` を実行した上でその戻り値
  (`len(user_data)`)を使ってT009の `resolve_path_collision()` を呼び出し、
  その結果(`event_dir`)で以降のseeds/sets/attr書き込みと本登録を行う
  よう `scripts/fetch/download.py` を変更する(`research.md` Decision 2、
  参加者数が未確定な場合の最終確定の遅延)。既存側がリネームされた場合、
  `tournaments.jsonl`を直ちに(この取得処理の終了を待たず)書き込み、
  中断時の不整合の窓を最小化する(憲法Principle II、T028参照)。
- [X] T012 [US2] Phase 2(US1)のベースライン分岐(T006)を
  `resolve_path_collision()` の呼び出しに置き換え、T004・T005の両方の
  統合ポイントに反映する(`scripts/fetch/download.py`)。
- [X] T013 [P] [US2] `resolve_path_collision()` の単体テストを
  `scripts/test/test_download.py` に追加する(参加者数が多い方の維持、
  同数時のタイブレーク、既存側リネームの正しさ、`attr.json` が
  読めない場合に `0` 扱いとなり新規側が優先されることを検証)。
- [X] T014 [US2] FR-005の「取得処理をまたいだ確定は不変」と、Edge Cases
  の「同一取得処理内では3件以上でも最多を維持」の両方を検証するテストを
  `scripts/test/test_download.py` に追加する。(a) 同一の
  `download_all_tournaments()`/`download_by_ids()` 呼び出しの中でA・B・C
  が順に検出され、Cが(それまでの暫定勝者Aより)最多の参加者数を持つ場合、
  最終的にCが元の名前を維持しAが調整されること(`settled_tournament_ids`
  に未だ含まれない場合の入れ替わり)。(b) Aが**別の**(先に完了した)
  取得処理で既に確定・保存済み(=次の呼び出し開始時点の
  `settled_tournament_ids` に含まれる)の場合、その後の取得処理で
  Aより参加者数の多いDが検出されても、Aは変更されずDのみが調整される
  こと。ユーザーフィードバック2026-08-29により、`/speckit-analyze`指摘
  R1時点の「2件目以降は常にロック」という想定から訂正。
- [X] T015 [US2] 衝突検出時点で新規側の参加者数が未確定な場合、
  `download_standings()` 完了まで本登録が遅延されることを検証する統合
  テストを `scripts/test/test_download.py` に追加する(FR-003)。

**Checkpoint**: 通常のクロールにおける衝突解決がFR-001〜FR-007を完全に
満たす。

---

## Phase 4: User Story 3 - 既に発生している未検出の重複を洗い出せる (Priority: P3)

**Goal**: `tournaments.jsonl` 全体を走査し、既に発生している(本フィーチャー
導入前の)未検出の衝突を一覧できる監査ツールを提供する。

**Independent Test**: 意図的に衝突を再現したテストデータに対して監査を
実行し、その組み合わせが一覧に出力されること、衝突が無いデータでは何も
報告されないことを確認する。

### Implementation for User Story 3

- [X] T016 [US3] `scripts/fix/find_path_collisions.py` を新規作成する
  (`tournaments.jsonl` を読み込み、全イベントの `path` でグルーピングし、
  同一 `path` に異なる `tournament_id` が2件以上紐づく組み合わせを標準
  出力に一覧表示する。read-only、API呼び出し無し。`research.md` Decision 5)。
- [X] T017 [P] [US3] `scripts/test/test_find_path_collisions.py` を新規
  作成し、衝突を再現したテストデータで衝突が報告されること、衝突が無い
  データでは何も報告されないことを検証する。

**Checkpoint**: 既存データ全体の衝突監査ができる。

---

## Phase 5: User Story 4 - 検出された衝突を、人手の確認のもとで修復できる (Priority: P4)

**Goal**: User Story 3で検出された衝突を、実行前確認を経た上で分離・修復
する専用ツールを提供する。

**Independent Test**: 検出された衝突1件を対象にツールを実行し、2つの
イベントがそれぞれ重複しない名前の別ディレクトリに再取得され、
`tournaments.jsonl` が両方の実際のパスを正しく反映していることを確認する。

### Implementation for User Story 4

- [X] T018 [US4] `scripts/fix/fix_path_collision.py` を新規作成する。
  対象2件**以上**の `--event-id <id1> <id2> [<id3> ...]` を受け取り、
  `--yes` 無しのデフォルト実行では対象イベント全員・現在の状態(各
  `attr.json`の`num_entrants`)・実行後の見込みを表示するのみで、実際の
  変更は一切行わない(既存の `redownload_event.py` の `--dry-run` 既定
  動作と同じパターン。`research.md` Decision 6)。対象データは全て既に
  ディスク上に存在するため`--token`(API呼び出し)は不要とした
  (実装時の判断。下記T019参照)。
- [X] T019 [US4] `--yes` 指定時の実行パスを `scripts/fix/fix_path_collision.py`
  に実装する。T009の `resolve_path_collision()` と同じ判定基準(FR-011)を
  用いるが、コマンドラインで指定された対象event_id群は互いに対して
  `settled_tournament_ids` に含めず(=指定された全員を「同一の取得処理
  内」として扱う)、2件ずつの比較を順に適用して全員の最終的な保存先を
  決定する(3件以上でも参加者数最多の1件のみ元の名前を維持する。
  `research.md` Decision 3・Decision 6)。対象データは全て既にディスク上
  に存在するため、start.gg への再取得は行わず、各対象の`attr.json`から
  再計算した本来の(衝突していない)保存先へ既存ディレクトリを移動する
  だけで分離する(不要なAPI呼び出しを避ける。憲法Principle V)。
  `tournaments.jsonl` を更新する。
- [X] T020 [P] [US4] `scripts/test/test_fix_path_collision.py` を新規
  作成し、`--yes` 無しでは一切変更が発生しないこと、`--yes` 付きでは
  参加者数が最多の1件の保存先名が変更されず残り全員が別ディレクトリに
  分離されること(2件・3件以上の両方のケースを含む)、`tournaments.jsonl`
  が全員の実際のパスを反映することを検証する。

**Checkpoint**: 既存の衝突を、人手の確認のもとで安全に修復できる。

---

## Phase 6: User Story 5 - 個別イベント再取得でも既存の別イベントを巻き込まない (Priority: P5)

**Goal**: `redownload_event.py` 単体でも、既に別event_idのデータが存在する
ディレクトリへ保存しようとした場合に、自分自身の保存先だけを重複しない
名前にずらす。

**Independent Test**: 既に別event_idのデータが存在するディレクトリと同じ
保存先に解決される、無関係なevent_idを `redownload_event.py` で再取得し、
既存のディレクトリの内容が変更されず、再取得した側だけが別ディレクトリに
保存されることを確認する。

### Implementation for User Story 5

- [X] T021 [US5] `path_occupied_by_different_event(event_dir, expected_event_id) -> bool`
  を `scripts/fetch/download.py` に実装する(ディスク上の対象ディレクトリの
  `attr.json`(読めない場合は他のデータファイルの存在)を確認し、
  `expected_event_id` と異なるevent_idのものであれば `True` を返す。
  `research.md` Decision 7)。
- [X] T022 [US5] `scripts/fix/redownload_event.py` の `redownload_event()`
  内、計算済みの `event_dir` が確定した時点(既存ディレクトリの探索・
  削除より前)でT021の関数を呼び出し、`True` の場合はT001の
  `disambiguate_event_name()` を用いて自分自身の保存先だけをずらす
  (相手側のディレクトリ・`tournaments.jsonl`エントリは一切変更しない)。
- [X] T023 [P] [US5] T021の単体テストを `scripts/test/test_download.py` に
  追加する(別event_idのデータが存在する場合に `True`、一致する場合や
  ディレクトリが存在しない場合に `False` を返すことを検証)。
- [X] T024 [P] [US5] `scripts/test/test_redownload_event.py` に統合テストを
  追加する。衝突するevent_idの再取得では既存ディレクトリが変更されず
  再取得側だけが調整後の名前で保存されること、衝突しないevent_idでは
  従来通りの挙動になること、同じevent_idへの繰り返し実行で調整後の保存先
  が一貫していることを検証する(FR-012)。

**Checkpoint**: `redownload_event.py` による個別再取得でも既存データの
巻き込み消失が発生しない。

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T025 [P] `docs/fix.md` に、通常のクロール(`download_all_tournaments`/
  `download_by_ids`)と `redownload_event.py` それぞれにおける保存先パス
  衝突回避の挙動、および新設した `find_path_collisions.py`/
  `fix_path_collision.py` の役割を追記する。
- [X] T026 `quickstart.md` の全6節(US1〜US5の手動検証手順+自動テスト)を
  実際に実行し、記載通りに動作することを確認する。
- [X] T027 `python3 -m unittest discover -s scripts/test` を実行し、
  リポジトリ全体のテストが通ることを確認する(憲法Principle III)。
- [X] T028 衝突解決によるディレクトリリネーム処理(T010の既存側リネーム、
  T019の修復ツールによる再配置、T022の`redownload_event.py`自己シフト)
  が処理途中で中断された場合でも、次回実行時に安全に再開・収束する
  ことを検証するテストを `scripts/test/test_download.py` /
  `scripts/test/test_fix_path_collision.py` / `scripts/test/test_redownload_event.py`
  に追加する(憲法Principle II、plan.md Constitution Check「実装時に
  要注意」への対応。`/speckit-analyze`指摘C1)。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: 依存なし。全User Storyをブロックする。
- **User Story 1 (Phase 2)**: Foundational完了後に開始可能。他Storyへの
  依存なし。
- **User Story 2 (Phase 3)**: Foundational完了後に開始可能だが、
  Phase 2(T004〜T006で作った統合ポイント)を置き換える形で実装するため、
  実質的にUser Story 1の後に行う。
- **User Story 3 (Phase 4)**: Foundational完了後、他Storyと独立に開始
  可能(`tournaments.jsonl`を読むだけで、書き込みロジックに依存しない)。
- **User Story 4 (Phase 5)**: T009(`resolve_path_collision()`、User Story 2)
  に依存する。
- **User Story 5 (Phase 6)**: Foundational(T001)にのみ依存し、User Story
  1〜4とは独立に実装・検証できる。
- **Polish (Phase 7)**: 実施した全User Storyの完了に依存する。

### User Story Dependencies

- **US1 (P1)**: Foundational完了後に開始。他Storyへの依存なし。
- **US2 (P2)**: Foundational完了後に開始可能だが、US1の統合ポイントを
  置き換えるため実質的にUS1に続けて実装する。
- **US3 (P3)**: Foundational完了後、US1/US2と独立に開始・検証可能。
- **US4 (P4)**: US2の `resolve_path_collision()` に依存(判定基準を再利用、
  FR-011)。
- **US5 (P5)**: Foundationalにのみ依存。US1〜US4とは独立に実装・検証可能。

### Within Each User Story

- 単体テストは対応する実装タスクの後に配置しているが、実装と同時に(先に
  書いて先に失敗させる形で)進めても構わない。
- `scripts/fetch/download.py` を編集するタスク同士(同一ファイル)は直列に
  実行する。
- 新規スクリプトファイル(`find_path_collisions.py`/`fix_path_collision.py`)
  とそれぞれのテストファイルは、実装後にテストを書く通常の順序で進める。

### Parallel Opportunities

- Foundational完了後、US1・US3・US5は互いに独立して並行着手できる
  (US2はUS1の後、US4はUS2の後)。
- 各Storyのテストタスク([P]付き)は、同一Story内の実装ファイルとは別
  ファイルであるため、実装が固まり次第並行して書き進められる。
- T025(docs更新)は他のPolishタスクと並行して進められる。

---

## Parallel Example: User Story 1

```bash
# T004〜T006(scripts/fetch/download.py)は直列。
# T007(単体テスト)はT004〜T006と別ファイルのため、関数シグネチャが
# 固まった時点で並行して書き進められる:
Task: "collision-detection unit tests in scripts/test/test_download.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Foundational を完了する。
2. Phase 2: User Story 1 を完了する。
3. **STOP and VALIDATE**: `quickstart.md` §1 でUser Story 1単独の挙動を
   確認する。
4. この時点で「衝突によるデータ破損の防止」というMVP価値は既に提供
   されている(どちら側が調整されるかはまだ未定)。

### Incremental Delivery

1. Foundational → Foundation ready。
2. User Story 1 追加 → 単独で検証 → MVP。
3. User Story 2 追加 → 単独で検証(参加者数優先ルールが確定)。
4. User Story 3 追加 → 単独で検証(既存衝突の監査が可能に)。
5. User Story 4 追加 → 単独で検証(検出済み衝突を人手確認のもとで修復
   可能に)。
6. User Story 5 追加 → 単独で検証(`redownload_event.py`も安全に)。
7. Polish → ドキュメント更新・全体テスト。

---

## Notes

- [P] = 別ファイル・依存タスク無し。
- [Story] ラベルはトレーサビリティのため、User Storyフェーズのタスクにのみ
  付与する(Foundational/Polishには付けない)。
- 各User Storyは独立して完了・検証できることを意図しているが、US2はUS1の、
  US4はUS2の統合ポイントを前提とするため、実装順序としては優先度順
  (P1→P2→P3→P4→P5)に進めることを推奨する。
- コミットはタスクまたは論理的なまとまりごとに行う。
- 各チェックポイントで、そのStoryが単独で動作することを確認してから次に
  進む。
