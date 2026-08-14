---

description: "Task list for 004-fix-duplicate-events"
---

# Tasks: 大会延期による重複イベントディレクトリとattr.json欠落の解消

**Input**: Design documents from `/specs/004-fix-duplicate-events/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/tournament-relocation.md,
contracts/backfill-discovery.md, quickstart.md

**Tests**: Constitution Principle III(検証ゲート、NON-NEGOTIABLE)により、新規ロジックには
テストを追加する。テストタスクを含む。

**Organization**: タスクは spec.md の User Story 1・2・3 ごとにグループ化。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並列実行可能(別ファイル、または同一ファイルでも独立した追記でロジック依存なし)
- **[Story]**: 対応するユーザーストーリー(US1, US2, US3)
- ファイルパスは実際のリポジトリパスを明記

## Path Conventions

単一プロジェクト構成。`scripts/`, `docs/` を使用(plan.md の Project Structure 参照)。
新規ファイル・新規ワークフローは作成しない。

---

## Phase 1: Setup

**Purpose**: 変更前の基準状態を確認する

- [X] T001 `python -m unittest scripts.test.test_download scripts.test.test_backfill_schema_version scripts.test.test_validate_data` を実行し、変更前の時点で全てパスすることを確認する(以降のタスクの差分検証の基準にする)(38 tests, OK)

**Note**: 本機能は既存ファイル(`scripts/fetch/download.py`, `scripts/fetch/backfill_schema_version.py`)
の局所的な変更のみで完結し、複数ユーザーストーリーが共有する新規インフラを必要としないため、
独立した Foundational フェーズは設けない。ただし US3(P3)は US1(P1, 特に T010)で実装する
共有ヘルパー関数に依存する ── US3 は「そのヘルパーが `tournaments.jsonl` を正しく更新する」
ことを独立したユニットテストで検証する形で組み立てる(詳細は Dependencies 参照)。

---

## Phase 2: User Story 1 - 大会延期による重複ディレクトリを作らない・解消する (Priority: P1) 🎯 MVP

**Goal**: 大会の開催日が延期された場合に、通常の再取得(大会一覧の一括スキャン・トーナメント
ID指定取得の両経路)で自動的に新しい開催日のディレクトリへ一本化され、古いディレクトリが
残らないようにする。

**Independent Test**: `quickstart.md` 手順1(単体テスト実行)+ 手順2(第7回チバスマ交流会の
実データでの検証)により、他のユーザーストーリーと独立に検証できる。

### Tests for User Story 1

- [X] T002 [P] [US1] `scripts/test/test_download.py` に、記録済みイベントパスの開催日と
      `current_date_parts` で渡された現在の開催日が異なる場合、`should_skip_tournament()` が
      `False`(スキップしない)を返すことを確認するテストを追加する
- [X] T003 [P] [US1] 同ファイルに、開催日が一致する場合は `should_skip_tournament()` が従来通り
      `True` を返すことを確認する回帰テストを追加する(既存の完了判定ロジックが壊れていない
      ことの確認)
- [X] T004 [P] [US1] 同ファイルに、`download_all_tournaments()` が、既知の `event_id` を
      新しいパスで再取得し、その必須ファイル一式が揃った場合、旧ディレクトリを削除し
      `tournaments.jsonl` の記録パスを新しいパスに更新することを確認するテストを追加する
- [X] T005 [P] [US1] 同ファイルに、新しいパスへの書き込みが必須ファイル一式揃わないまま終了した
      場合(大規模イベント失敗等を模擬)、旧ディレクトリが削除されず、`tournaments.jsonl` の
      記録パスも更新されないことを確認するテストを追加する(FR-002 の回帰確認)
- [X] T006 [P] [US1] 同ファイルに、`download_by_ids()` 経由の再取得でも同じ統合ロジック
      (共有ヘルパー)が使われ、旧ディレクトリの削除・パス更新が行われることを確認するテストを
      追加する
- [X] T007 [P] [US1] 同ファイルに、`event_id` が異なる(たまたま大会名・イベント名が同じだけの)
      ディレクトリ同士は統合対象とみなされないことを確認するテストを追加する(FR-008 の確認)
      (あわせて、`/speckit-analyze` の G1 指摘に対応する回帰テスト
      `test_download_all_tournaments_does_not_touch_untracked_duplicate_directory` を追加:
      3件以上重複しているケースで `tournaments.jsonl` から参照されていない中間ディレクトリには
      手を出さないことを確認)

### Implementation for User Story 1

- [X] T008 [US1] `scripts/fetch/download.py` の `should_skip_tournament()` に
      `current_date_parts=None` 引数を追加し、指定されている場合は記録済みイベントパスの
      開催日と比較して不一致なら `False` を返すロジックを実装する
- [X] T009 [US1] `scripts/fetch/download.py` の `download_all_tournaments()` 内で、
      `should_skip_tournament()` 呼び出し前に `get_date_parts(timestamp)` を計算し、
      `current_date_parts=(year, month, day)` として渡すよう変更する(T008 に依存)
- [X] T010 [US1] `scripts/fetch/download.py` に、`tournaments[tournament_id]["events"]` の
      更新を担う共有ヘルパー関数(例: `record_event_path()`)を新規実装する。既存 `event_id` の
      エントリが無ければ追加、ある場合はパスが同じなら何もせず、パスが異なれば
      `event_files_complete(new_dir)` を確認した上でパス更新+(ディスク上に存在すれば)
      `shutil.rmtree()` で旧ディレクトリを削除する(未完成の場合は何もしない)。
      `import shutil` を追加する(T008 に依存)
- [X] T011 [US1] `scripts/fetch/download.py` の `download_all_tournaments()` 内の
      `existing_events` 追加専用ロジックを、T010 の共有ヘルパー呼び出しに置き換える
      (T010 に依存)
- [X] T012 [US1] `scripts/fetch/download.py` の `download_by_ids()` 内の同様の
      `existing_events` 追加専用ロジックも、T010 の共有ヘルパー呼び出しに置き換える
      (T010 に依存)

**Checkpoint**: 大会一覧の一括スキャン・トーナメントID指定取得のいずれの経路でも、延期された
大会が自動的に新しいディレクトリへ一本化されるようになる。ここまでで `quickstart.md` 手順1・2
が独立に検証可能。

---

## Phase 3: User Story 2 - attr.jsonが欠落したイベントを段階的バックフィルで確実に補完する (Priority: P2)

**Goal**: `attr.json` を欠くイベントディレクトリが、既存の段階的バックフィルの通常の実行
サイクルの中で発見され、`attr.json` が補完されるようにする。

**Independent Test**: `attr.json` を持たない(が `standings.json` は持つ)イベントディレクトリを
用意し、`backfill_schema_version.py` を1回実行して、そのディレクトリが検出され `attr.json` が
新規作成されることを確認する(`quickstart.md` 手順3)。

### Tests for User Story 2

- [X] T013 [P] [US2] `scripts/test/test_backfill_schema_version.py` に、`attr.json` を持たず
      `standings.json` のみ持つディレクトリが `iter_event_dirs()` の結果に含まれることを
      確認するテストを追加する
- [X] T014 [P] [US2] 同ファイルに、`attr.json` が存在しない(または `event_id` を読めない)
      ディレクトリでも、`tournaments.jsonl` に一致するパスの記録があれば `event_id` が
      復元され、`backfill_one_event()` が再取得を完了して `attr.json` を新規作成することを
      確認するテストを追加する
- [X] T015 [P] [US2] 同ファイルに、`attr.json` も `tournaments.jsonl` の記録も無い(`event_id`
      を特定できない)ディレクトリに対して、`backfill_one_event()` が例外を送出せず `[UNRESOLVED]`
      を出力して `False` を返すことを確認するテストを追加する
- [X] T016 [P] [US2] 同ファイルの既存テスト(`run_backfill()` の戻り値を辞書の完全一致で検証
      している箇所、例: `test_no_eligible_events_exits_cleanly`)を、新しい `unresolved` キーを
      含む形に更新する。あわせて `unresolved` カウントが正しく集計されることを確認するテストを
      追加する

### Implementation for User Story 2

- [X] T017 [US2] `scripts/fetch/backfill_schema_version.py` の `iter_event_dirs()` の走査対象に
      `events_root.rglob("standings.json")` を追加し、`attr.json` との和集合を返すようにする
      (既存の `attr.json` のみのテストフィクスチャとの後方互換性のため、単純な置き換えではなく
      和集合とした)
- [X] T018 [US2] 同ファイルの `backfill_one_event()` に `tournaments=None` 引数を追加し、
      `attr.json` が読めない/`event_id` が無い場合に `tournaments` から
      `events[].path == str(event_dir)` のエントリを探して `event_id` を復元するフォールバックを
      実装する。復元できない場合は `[UNRESOLVED] {event_dir}: event_id を特定できません` を
      標準エラー出力し `False` を返す(T017 の後に実施、同ファイルのため逐次)
- [X] T019 [US2] 同ファイルの `run_backfill()` で `tournaments.jsonl` を読み込み
      `backfill_one_event()` に渡すよう変更し、戻り値のサマリー辞書に `unresolved`(int)を
      追加して集計する(T018 に依存)
- [X] T020 [US2] 同ファイルの `main()` に `--tournament_file_path`
      (デフォルト `data/startgg/tournaments.jsonl`)引数を追加し、`run_backfill()` へ渡す
      (T019 に依存)

**Checkpoint**: `attr.json` 欠落イベントが、次回の `schema_backfill.yml` 実行サイクルから
自動的に発見・補完対象になる。ここまでで `quickstart.md` 手順3が独立に検証可能。

---

## Phase 4: User Story 3 - 再取得後もブックキーピングが実体と食い違わないようにする (Priority: P3)

**Goal**: T010 の共有ヘルパーが `tournaments.jsonl` の記録パスを正しく更新することを、
US1 の統合テストとは独立に、ヘルパー単体の振る舞いとして保証する。あわせて、本機能が
自動解消しない既知の残存ケース(Clarifications 参照)を `docs/fix.md` に記録する。

**Independent Test**: T010 の共有ヘルパーを直接呼び出し、既存エントリのパスが異なる場合に
新パス完成時のみ更新される(未完成時は更新されない)ことを、`download_all_tournaments()` /
`download_by_ids()` を経由せずに確認する。

### Tests for User Story 3

- [X] T021 [P] [US3] `scripts/test/test_download.py` に、T010 の共有ヘルパー関数単体のユニット
      テストを追加する:既存エントリのパスが異なり `event_files_complete(new_dir)` が `True` の
      場合は `path` が更新され旧ディレクトリ削除が行われること、`False` の場合はどちらも
      行われないことを、ヘルパー関数を直接呼び出して確認する
      (T010実装時に `test_record_event_path_relocates_when_new_directory_is_complete` /
      `test_record_event_path_keeps_old_directory_when_new_directory_incomplete` として実施済み)

### Implementation for User Story 3

- [X] T022 [P] [US3] `docs/fix.md` に、本機能が自動解消する範囲(`tournaments.jsonl` に記録
      された1件の旧パスとの統合のみ)と、既知の残存ケース(`tournaments.jsonl` から参照されて
      いない3件以上の重複ディレクトリ、例: 走利夜-SO-RYA_#2、
      L.S.C.T〜Love_Smash_Champion_Tournament〜)を記録する(FR-009、Clarifications 参照)

**Checkpoint**: 共有ヘルパーの正しさが US1 の統合テストとは別に保証され、本機能のスコープ
境界が `docs/fix.md` に明記される。

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T023 [P] `python -m unittest discover -s scripts/test -p "test_*.py"` を実行し、
      本機能で追加・変更したテストを含む全テストスイートがパスすることを確認する(58 tests, OK)
- [ ] T024 `quickstart.md` 手順2(第7回チバスマ交流会の重複解消)と手順3(attr.json欠落
      イベントの段階的補完)を実際の `STARTGG_TOKEN` で行い、重複が実際に解消されること・
      `attr.json` が実際に補完されることを目視確認する
      **未実施**: 本セッションのサンドボックス環境には実際の `STARTGG_TOKEN` / start.gg への
      実ネットワークアクセスが無いため実行不可。マージ前またはマージ後、実環境(ローカル or
      GitHub Actions の `workflow_dispatch` 手動実行)で人手による実施が必要
      (`003-attr-end-at` の T018 と同様の制約)。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし、即着手可能
- **User Story 1 (Phase 2)**: Setup 完了後。他のユーザーストーリーへの依存なし
- **User Story 2 (Phase 3)**: Setup 完了後に着手可能。US1 に依存しない(別ファイル・別関数)
- **User Story 3 (Phase 4)**: US1 の T010(共有ヘルパーの実装)に依存する。ヘルパーが
  存在しない状態では T021 のユニットテストが対象を持たないため
- **Polish (Phase 5)**: 実施したいユーザーストーリーすべての完了後

### User Story Dependencies

- **US1 (P1)**: Setup 完了後に着手可能。他ストーリーに依存しない
- **US2 (P2)**: Setup 完了後に着手可能。US1 に依存しない(`backfill_schema_version.py` のみを
  変更し、`download.py` には触れない)
- **US3 (P3)**: US1 の T010 に依存する(上記参照)。実質的に US1 の後に実施する

### Parallel Opportunities

- US1 のテスト T002〜T007 は並列実行可能
- US1 の実装のうち T008 の後、T009・T010 は並列実行可能。T011・T012 は T010 に依存するため
  T010 完了後に実施(T011・T012 は同一ファイルの別関数だが、共有ヘルパー呼び出しへの置き換え
  という同種の変更のため、コンフリクト回避の観点から逐次実行を推奨)
- US2 は US1 と並行して着手可能(別ファイル)。US2 内のテスト T013〜T016 は並列実行可能。
  実装 T017〜T020 は同一ファイル内で前のタスクに依存するため逐次実行
- US3 の T021・T022 は並列実行可能(T021はテストコード、T022はドキュメントで別ファイル)
- Polish の T023 は単独で並列実行可能

---

## Parallel Example: User Story 1 実装

```bash
# T008 完了後、T009・T010 は互いに独立(前者は呼び出し側、後者は新規ヘルパー関数)のため並列実行できる:
Task: "should_skip_tournament() 呼び出し箇所に current_date_parts を渡す"
Task: "tournaments[]['events'] 更新用の共有ヘルパー関数を新規実装する"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup を完了
2. Phase 2: User Story 1 を完了
3. **STOP and VALIDATE**: `quickstart.md` 手順1・2で US1 を単独検証
4. この時点で「延期による新規重複を作らない・第7回チバスマ交流会の重複を解消できる」機能は
   実用可能な状態になる(MVP)。`attr.json` 欠落問題(661件)への対応はまだ行われない

### Incremental Delivery

1. Setup → 基準状態確認
2. US1 追加 → 単独検証 → MVPとしてデプロイ可能(重複解消)
3. US2 追加 → 単独検証 → `attr.json` 欠落の段階的補完が開始する
4. US3 追加 → 共有ヘルパーの正しさを独立に保証 + 既知の制約を `docs/fix.md` に記録
5. Polish → 全体テスト・実環境での目視検証

---

## Notes

- [P] タスク = 別ファイル、または同一ファイルでも独立した追記でロジック依存なし
- US3 は独立した新規機能というより、US1 で実装した共有ヘルパーの正しさを保証する検証と、
  本機能のスコープ境界を明文化するドキュメント更新である
- テストは実装前に書き、失敗することを確認してから実装に進む
- 各チェックポイントで、そのユーザーストーリーが単独で検証可能であることを確認する
