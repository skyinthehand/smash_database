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

- [ ] T001 `disambiguate_event_name(tournament_name: str, tournament_id: int) -> str`
  を `scripts/fetch/download.py` に実装する(`research.md` Decision 4:
  `f"{tournament_name}_({tournament_id})"` に既存の空白/スラッシュ置換
  ルールを適用)。
- [ ] T002 `build_path_index(tournaments: dict) -> dict[str, tuple[int, int]]`
  を `scripts/fetch/download.py` に実装する(`path -> (tournament_id, event_id)`
  の逆引き辞書、`research.md` Decision 1)。
- [ ] T003 T001・T002の単体テストを `scripts/test/test_download.py` に追加する
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

- [ ] T004 [US1] `download_all_tournaments()` 内、`event_dir = get_event_directory(...)`
  直後(既存の `load_excluded_event_ids()` チェックと同じ挿入点)に、
  T002の `build_path_index()` を用いた衝突検出を `scripts/fetch/download.py`
  に追加する。
- [ ] T005 [US1] `download_by_ids()` にも同じ衝突検出を `scripts/fetch/download.py`
  に追加する。
- [ ] T006 [US1] 衝突が検出された場合、新たに見つかった側の保存先を
  T001の `disambiguate_event_name()` で調整してから
  `update_event_registration()` による登録を行うベースラインの分岐を
  `scripts/fetch/download.py` に実装する(参加者数比較はUS2で追加)。
- [ ] T007 [P] [US1] 衝突検出・ベースライン調整の単体テストを
  `scripts/test/test_download.py` に追加する(衝突時は新規側が調整され、
  衝突が無い場合は従来通り無調整であることを検証)。
- [ ] T008 [US1] `download_all_tournaments()`/`download_by_ids()` への統合
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

- [ ] T009 [US2] `resolve_path_collision(new_event_dir, new_num_entrants, existing_tournament_id, existing_event, tournaments)`
  を `scripts/fetch/download.py` に実装する(既存側の参加者数は
  `existing_event["path"]/attr.json` の `num_entrants` から読み取り、
  読めない場合は `0` 扱い。参加者数が多い方は無調整、同数の場合は
  `tournament_id` が大きい方を調整対象とする決定的なタイブレーク。
  `research.md` Decision 3)。
- [ ] T010 [US2] T009の関数内、新規側ではなく既存側が調整対象になる場合の
  処理を `scripts/fetch/download.py` に実装する(既存イベントの
  ディレクトリを実際にリネームし、`tournaments` 辞書内の該当エントリの
  `path` を更新する。既存の安全なリロケーションパターン
  (`cleanup_relocated_directory()`)を踏襲)。
- [ ] T011 [US2] `download_all_tournaments()`/`download_by_ids()` を、
  衝突検出時に早期の `update_event_registration()` 呼び出しをスキップし、
  計算上の(衝突しうる)`event_dir` へ `download_standings()` を実行した
  上でその戻り値(`len(user_data)`)を使ってT009の
  `resolve_path_collision()` を呼び出し、その結果で本登録するよう
  `scripts/fetch/download.py` を変更する(`research.md` Decision 2、
  参加者数が未確定な場合の最終確定の遅延)。
- [ ] T012 [US2] Phase 2(US1)のベースライン分岐(T006)を
  `resolve_path_collision()` の呼び出しに置き換え、T004・T005の両方の
  統合ポイントに反映する(`scripts/fetch/download.py`)。
- [ ] T013 [P] [US2] `resolve_path_collision()` の単体テストを
  `scripts/test/test_download.py` に追加する(参加者数が多い方の維持、
  同数時のタイブレーク、既存側リネームの正しさ、`attr.json` が
  読めない場合に `0` 扱いとなり新規側が優先されることを検証)。
- [ ] T014 [US2] 確定・保存済みの衝突解決が、後から現れたより参加者数の
  多い3件目の同日同名イベントによって再度変更されないことを検証する
  テストを `scripts/test/test_download.py` に追加する(FR-005)。
- [ ] T015 [US2] 衝突検出時点で新規側の参加者数が未確定な場合、
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

- [ ] T016 [US3] `scripts/fix/find_path_collisions.py` を新規作成する
  (`tournaments.jsonl` を読み込み、全イベントの `path` でグルーピングし、
  同一 `path` に異なる `tournament_id` が2件以上紐づく組み合わせを標準
  出力に一覧表示する。read-only、API呼び出し無し。`research.md` Decision 5)。
- [ ] T017 [P] [US3] `scripts/test/test_find_path_collisions.py` を新規
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

- [ ] T018 [US4] `scripts/fix/fix_path_collision.py` を新規作成する。
  `--token`・対象2件の `--event-id <A> <B>` を受け取り、`--yes` 無しの
  デフォルト実行では対象イベント・現在の状態(各`attr.json`の
  `num_entrants`)・実行後の見込みを表示するのみで、実際の変更は一切
  行わない(既存の `redownload_event.py` の `--dry-run` 既定動作と同じ
  パターン。`research.md` Decision 6)。
- [ ] T019 [US4] `--yes` 指定時の実行パスを `scripts/fix/fix_path_collision.py`
  に実装する。T009の `resolve_path_collision()` と同じ判定基準(FR-011)を
  用いて両者の最終的な保存先を決定し、`redownload_event.py` が使っている
  のと同じ取得用の関数群(`download_standings`/`download_seeds`/
  `download_all_set`/`write_event_attributes`)を再利用してそれぞれを
  個別に再取得し、`tournaments.jsonl` を更新する。
- [ ] T020 [P] [US4] `scripts/test/test_fix_path_collision.py` を新規
  作成し、`--yes` 無しでは一切変更が発生しないこと、`--yes` 付きでは
  参加者数が多い方の保存先名が変更されず両者が別ディレクトリに分離
  されること、`tournaments.jsonl` が両方の実際のパスを反映することを
  検証する。

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

- [ ] T021 [US5] `path_occupied_by_different_event(event_dir, expected_event_id) -> bool`
  を `scripts/fetch/download.py` に実装する(ディスク上の対象ディレクトリの
  `attr.json`(読めない場合は他のデータファイルの存在)を確認し、
  `expected_event_id` と異なるevent_idのものであれば `True` を返す。
  `research.md` Decision 7)。
- [ ] T022 [US5] `scripts/fix/redownload_event.py` の `redownload_event()`
  内、計算済みの `event_dir` が確定した時点(既存ディレクトリの探索・
  削除より前)でT021の関数を呼び出し、`True` の場合はT001の
  `disambiguate_event_name()` を用いて自分自身の保存先だけをずらす
  (相手側のディレクトリ・`tournaments.jsonl`エントリは一切変更しない)。
- [ ] T023 [P] [US5] T021の単体テストを `scripts/test/test_download.py` に
  追加する(別event_idのデータが存在する場合に `True`、一致する場合や
  ディレクトリが存在しない場合に `False` を返すことを検証)。
- [ ] T024 [P] [US5] `scripts/test/test_redownload_event.py` に統合テストを
  追加する。衝突するevent_idの再取得では既存ディレクトリが変更されず
  再取得側だけが調整後の名前で保存されること、衝突しないevent_idでは
  従来通りの挙動になること、同じevent_idへの繰り返し実行で調整後の保存先
  が一貫していることを検証する(FR-012)。

**Checkpoint**: `redownload_event.py` による個別再取得でも既存データの
巻き込み消失が発生しない。

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T025 [P] `docs/fix.md` に、通常のクロール(`download_all_tournaments`/
  `download_by_ids`)と `redownload_event.py` それぞれにおける保存先パス
  衝突回避の挙動、および新設した `find_path_collisions.py`/
  `fix_path_collision.py` の役割を追記する。
- [ ] T026 `quickstart.md` の全6節(US1〜US5の手動検証手順+自動テスト)を
  実際に実行し、記載通りに動作することを確認する。
- [ ] T027 `python3 -m unittest discover -s scripts/test` を実行し、
  リポジトリ全体のテストが通ることを確認する(憲法Principle III)。

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
