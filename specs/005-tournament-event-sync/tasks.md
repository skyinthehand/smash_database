---

description: "Task list for 005-tournament-event-sync"
---

# Tasks: 空イベントディレクトリの整理

**⚠️ 2026-08-18 再スコープ**: 実データ検証の結果、Phase 2(User Story 1、旧称
「トーナメント単位でのイベント作り直し検知」)は誤った前提(同一tournament_id内での
event_id作り直し)に基づいていたことが判明したため**撤回**した。真の原因は
`tournaments.jsonl` への記録タイミングの遅さであり、`004-fix-duplicate-events` の
延長として `scripts/fetch/download.py` を直接修正した(T029-T031、本ファイル末尾)。
Phase 2 の実装(`scripts/fetch/backfill_tournament_events.py` 等)は削除済み(T032)。
Phase 3(空イベントディレクトリの整理)は撤回の影響を受けず、そのまま有効。
経緯は spec.md の User Scenarios / Clarifications を参照。

**Input**: Design documents from `/specs/005-tournament-event-sync/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/empty-event-cleanup.md, quickstart.md
(`contracts/tournament-event-discovery.md` は撤回済み、経緯の記録として保持)

**Tests**: Constitution Principle III(検証ゲート、NON-NEGOTIABLE)により、新規ロジックには
テストを追加する。テストタスクを含む。

**Organization**: タスクは spec.md の(旧)User Story 1・2 ごとにグループ化(Phase 2 は撤回済み)。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並列実行可能(別ファイル、または同一ファイルでも独立した追記でロジック依存なし)
- **[Story]**: 対応するユーザーストーリー(US1, US2)
- ファイルパスは実際のリポジトリパスを明記

## Path Conventions

単一プロジェクト構成。`scripts/`, `.github/workflows/` を使用(plan.md の Project
Structure 参照)。既存ファイル(`download.py`, `backfill_schema_version.py`)は変更しない。

---

## Phase 1: Setup

**Purpose**: 変更前の基準状態を確認する

- [X] T001 `python -m unittest discover -s scripts/test -p "test_*.py"` を実行し、
      変更前の時点で全てパスすることを確認する(以降のタスクの差分検証の基準にする)(59 tests, OK)

**Note**: 本機能は完全に新規のファイル(`scripts/fetch/backfill_tournament_events.py`,
`scripts/fix/prune_empty_events.py`)として実装し、既存ファイルへの変更を伴わないため、
独立した Foundational フェーズは設けない。User Story 1・2 は互いに異なるファイル・
異なる関心事(API取得 / ローカル削除)であり、完全に独立して実装・検証できる。

---

## Phase 2: User Story 1(撤回) - トーナメント単位でイベントの作り直しを検知し、新しいイベントを取得する

**⚠️ 撤回(2026-08-18)**: 以下のT002-T013は実装・全テストパス済みだったが、実データ検証で
前提(同一tournament_id内でのevent_id作り直し)が誤りと判明したため撤回した。
`scripts/fetch/backfill_tournament_events.py` と `scripts/test/test_backfill_tournament_events.py`
は削除済み(T032)。タスクの記録は経緯を残すためチェック状態を含めそのまま保持する。

**Goal**(撤回前の計画): `tournaments.jsonl` に記録済みの各トーナメント(記録イベント数0件を含む)について、
start.gg側の現在のイベント一覧を再取得し、記録に無い新しい event_id を発見して通常の
取得手順で保存する。

**Independent Test**: `quickstart.md` 手順1(単体テスト実行)+ 手順2前半(第7回チバスマ
交流会で event_id=1533881 が新規取得されることの実データ確認)により、User Story 2 と
独立に検証できる。

### Tests for User Story 1

- [X] T002 [P] [US1] `scripts/test/test_backfill_tournament_events.py` を新規作成し、
      `iter_tournament_ids()` が記録イベント数0件のトーナメントも含めて返すことを
      確認するテストを追加する
- [X] T003 [P] [US1] 同ファイルに、`find_new_event_ids()` が `fetch_event_ids_from_tournament()`
      の結果から、記録済みの event_id 集合に含まれないものだけを返すことを確認する
      テストを追加する
- [X] T004 [P] [US1] 同ファイルに、`fetch_event_ids_from_tournament()` が `FetchError` を
      送出した場合、`find_new_event_ids()` が例外を伝播させず空リストを返すことを確認する
      テストを追加する
- [X] T005 [P] [US1] 同ファイルに、`save_new_event()` が新しい event_id の詳細を取得し、
      `attr.json` を含む一式を新規ディレクトリに書き込み、`tournaments` 辞書の該当
      トーナメントの `events` に新しいエントリを追加することを確認するテストを追加する
- [X] T006 [P] [US1] 同ファイルに、`save_new_event()` が取得失敗時に例外を送出せず
      `False` を返すことを確認するテストを追加する
- [X] T007 [P] [US1] 同ファイルに、`run_tournament_event_sync()` がカーソルファイルを
      使って複数回の実行にまたがって異なるトーナメントを処理し、一周したら先頭に
      戻ることを確認するテストを追加する(`test_backfill_schema_version.py` の
      カーソルテストと同様のパターン)
- [X] T008 [P] [US1] 同ファイルに、新しいイベントが1件も見つからなかった場合は
      `tournaments.jsonl` への書き込みが発生しないことを確認するテストを追加する

### Implementation for User Story 1

- [X] T009 [US1] `scripts/fetch/backfill_tournament_events.py` を新規作成し、
      `scripts.fetch.backfill_schema_version` から `read_cursor()` / `write_cursor()` を
      再利用し、`iter_tournament_ids(tournaments)` を実装する(`tournaments.jsonl` の
      全 `tournament_id` を安定ソート順で返す。イベント数0件のトーナメントも含む)
- [X] T010 [US1] 同ファイルに、`fetch_event_details(event_id)` / `build_place_dict(tournament)`
      を実装する(`scripts/fetch/backfill_schema_version.py` と同一パターン、
      `event(id: $eventId)` を直接叩く)。あわせて `find_new_event_ids(tournament_id,
      game_id, recorded_event_ids)` を実装し、`fetch_event_ids_from_tournament()` の
      `FetchError` を捕捉して空リストを返すようにする
- [X] T011 [US1] 同ファイルに `save_new_event(tournament_id, tournament_name, event_id,
      country_code, startgg_dir, tournaments, users, users_file_path)` を実装する。
      `fetch_event_details()` → `get_date_parts()` + `get_event_directory()` →
      `download_standings()` → `download_seeds()` → `extend_user_info()` →
      `download_all_set()` → `write_event_attributes()` の順で新規保存し、成功したら
      `tournaments[tournament_id]["events"]` に追記して `True` を返す(T010 に依存)
- [X] T012 [US1] 同ファイルに `run_tournament_event_sync(tournament_file_path,
      cursor_path, startgg_dir, users_file_path, game_id, max_tournaments)` を実装する。
      `iter_tournament_ids()` でカーソルベースの循環スキャンを行い、各トーナメントに
      `find_new_event_ids()` を適用し、見つかった event_id ごとに `save_new_event()` を
      呼ぶ。新規イベントを1件以上保存した場合のみ `write_jsonl()` で `tournaments.jsonl`
      を書き戻す(T009, T011 に依存)
- [X] T013 [US1] 同ファイルに `main()` CLI エントリポイントを実装する(`--token`,
      `--tournament_file_path`, `--cursor_path`, `--events_root`, `--users_file_path`,
      `--game_id`, `--max_tournaments`, 既存スクリプトと同様の `--url`/`--max_retries`/
      `--retry_delay`/`--indent_num` を含む)(T012 に依存)

**Checkpoint**: start.gg側でイベントが作り直されたトーナメントが、次回のトーナメント単位
スキャン実行サイクルから自動的に新しいイベントを発見・保存できるようになる。ここまでで
`quickstart.md` 手順1・手順2前半が独立に検証可能。

---

## Phase 3: User Story 2 - 実データの無い空のイベントディレクトリを整理する (Priority: P2)

**Goal**: `standings.json` と `matches.json` が両方とも空のイベントディレクトリを検出し、
削除する。あわせて `tournaments.jsonl` の対応する記録も取り除く。

**Independent Test**: `standings.json`/`matches.json` がどちらも空のイベントディレクトリを
用意し、整理処理を1回実行して、そのディレクトリが削除され `tournaments.jsonl` の記録も
削除されることを確認する(`quickstart.md` 手順2後半)。

### Tests for User Story 2

- [X] T014 [P] [US2] `scripts/test/test_prune_empty_events.py` を新規作成し、
      `count_data_entries()` がファイル欠落・空の `data` 配列のどちらでも `0` を返し、
      例外を送出しないことを確認するテストを追加する
- [X] T015 [P] [US2] 同ファイルに、`is_empty_event()` が `standings.json` と
      `matches.json` の両方が空の場合に `True` を返すことを確認するテストを追加する
- [X] T016 [P] [US2] 同ファイルに、`is_empty_event()` が `standings.json` または
      `matches.json` のいずれかにデータがあれば `False` を返すことを確認するテストを
      追加する(FR-005 の確認)
- [X] T017 [P] [US2] 同ファイルに、`find_empty_event_dirs()` が複数のディレクトリ
      (空・非空混在)の中から空のものだけを返すことを確認するテストを追加する
- [X] T018 [P] [US2] 同ファイルに、`prune_empty_events(apply=False)` がファイル
      システム・`tournaments.jsonl` のどちらも変更しないことを確認するテストを追加する
      (dry-run のデフォルト動作)
- [X] T019 [P] [US2] 同ファイルに、`prune_empty_events(apply=True)` が空のディレクトリを
      削除し、`tournaments.jsonl` から対応するイベント記録を取り除いて書き戻すことを
      確認するテストを追加する
- [X] T020 [P] [US2] 同ファイルに、`prune_empty_events(apply=True)` が非空のディレクトリと
      その `tournaments.jsonl` の記録には一切手を出さないことを確認するテストを追加する

### Implementation for User Story 2

- [X] T021 [US2] `scripts/fix/prune_empty_events.py` を新規作成し、
      `count_data_entries(path)` と `is_empty_event(event_dir)` を実装する
      (`scripts/fix/redownload_event.py::count_data_entries()` と同一パターン)
- [X] T022 [US2] 同ファイルに `find_empty_event_dirs(events_root)` を実装する
      (`standings.json` または `matches.json` を持つ全ディレクトリを走査し、
      `is_empty_event()` が `True` のものを返す)(T021 に依存)
- [X] T023 [US2] 同ファイルに `prune_empty_events(events_root, tournament_file_path,
      apply)` を実装する。`apply=True` の場合のみ `shutil.rmtree()` で削除し、
      `read_tournaments_jsonl()` → 該当 `path` を持つイベント記録を除去 →
      `write_jsonl()` で1回だけ書き戻す(T022 に依存)
- [X] T024 [US2] 同ファイルに `main()` CLI エントリポイントを実装する(`--events_root`,
      `--tournament_file_path`, `--apply`、`--apply` 省略時は dry-run でレポートのみ)
      (T023 に依存)

**Checkpoint**: 実データの無いイベントディレクトリが、次回の整理処理実行サイクルから
自動的に削除されるようになる。ここまでで `quickstart.md` 手順2後半が独立に検証可能。

---

## Phase 4: Polish & Cross-Cutting Concerns

- [X]~~T025~~ [P] (撤回) `.github/workflows/tournament_event_sync.yml` を新規作成する。
      → **削除済み(T032)**。空イベント整理のみを行う `.github/workflows/prune_empty_events.yml`
      に置き換えた(STARTGG_TOKEN不要、`cron: "0 12 * * 0"` は維持)。
- [X] T026 [P] `python -m unittest discover -s scripts/test -p "test_*.py"` を実行し、
      本機能で追加したテストを含む全テストスイートがパスすることを確認する(74 tests, OK)
      (Phase 2 撤回後の現在は68 tests、T031参照)
- [X]~~T028~~ (計画外・T027の実データ検証中に発見、後に撤回) `run_tournament_event_sync()` に
      `sync_specific_tournaments()` と `--tournament_ids` オプションを追加した。
      → `backfill_tournament_events.py` 自体の削除(T032)に伴い、この追加も撤回された。
- [X] T027 `quickstart.md` 手順2(第7回チバスマ交流会での実データ検証)を実施した結果、
      当初の想定(`backfill_tournament_events.py` による自動発見)とは異なる形で判明・解決した:
      - event_id=1533881(tournament_id=867504、旧811466とは別レコード)は
        `scripts/fix/redownload_event.py --event-id 1533881 --yes` で手動取得済み、
        `attr.json` 作成済み(この過程で真の原因=記録タイミング問題を発見、T029-T031で修正)
      - event_id=1423946(tournament_id=811466、実データ無し)のディレクトリ削除は
        `scripts/fix/prune_empty_events.py --apply` の実行待ち(**未実施**、実環境での
        人手実行が必要)

---

## 事後修正: `tournaments.jsonl` への記録タイミングの是正(2026-08-18)

実データ検証により判明した真の根本原因(`download_all_tournaments()`/`download_by_ids()`が
`tournaments.jsonl`への記録を取得パイプライン完了後まで遅延させていたこと)への対応。
`004-fix-duplicate-events`で実装した`record_event_path()`を、取得処理の**前**に
呼び出すよう変更した。

- [X] T029 `scripts/test/test_download.py` に、`download_all_tournaments()`が
      大規模イベント処理(matches取得)の失敗後も、event_idと保存先パスの対応関係が
      `tournaments.jsonl`に記録され続けることを確認するテストを追加(
      `test_download_all_tournaments_records_event_path_before_fetch_even_if_later_step_fails`)。
      あわせて`download_by_ids()`版も追加(
      `test_download_by_ids_records_event_path_before_fetch_even_if_standings_fails`)
- [X] T030 `scripts/fetch/download.py`の`download_all_tournaments()`・`download_by_ids()`
      の両方で、`record_event_path()`呼び出しを`event_dir`確定直後(取得処理を開始する前)に
      移動。既存の(取得完了後の)呼び出しはそのまま残し、延期による再配置(`004`の
      関心事)の完了検知に使う(2回目の呼び出しは新規イベントに対しては no-op)
- [X] T031 全テストスイート実行、38 tests (test_download.py), 68 tests (discover全体), OK

## 事後整理: 撤回された成果物の削除(2026-08-18)

- [X] T032 `scripts/fetch/backfill_tournament_events.py`、
      `scripts/test/test_backfill_tournament_events.py`、
      `.github/workflows/tournament_event_sync.yml`、孤児化したカーソルファイル
      `data/startgg/tournament_event_sync_cursor.txt` を削除。
      `.github/workflows/prune_empty_events.yml`(空イベント整理のみ、STARTGG_TOKEN不要)を
      新規作成して置き換えた

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし、即着手可能
- **User Story 1 (Phase 2)**: Setup 完了後。他のユーザーストーリーへの依存なし
- **User Story 2 (Phase 3)**: Setup 完了後に着手可能。US1 に依存しない(別ファイル・
  別関心事、API呼び出しの有無も異なる)
- **Polish (Phase 4)**: 実施したいユーザーストーリーすべての完了後
  (T025 のワークフローは US1・US2 両方のスクリプトを呼ぶため、両方の実装完了後に作成する)

### User Story Dependencies

- **US1 (P1)**: Setup 完了後に着手可能。他ストーリーに依存しない
- **US2 (P2)**: Setup 完了後に着手可能。US1 に依存しない

### Parallel Opportunities

- US1 のテスト T002〜T008 は並列実行可能
- US1 の実装は T009 の後、T010 が続き(T011 が依存)、T012・T013 は逐次(同一ファイルの
  積み上げのため)
- US2 は US1 と並行して着手可能(別ファイル)。US2 内のテスト T014〜T020 は並列実行可能。
  実装 T021〜T024 は同一ファイル内で前のタスクに依存するため逐次実行
- Polish の T025・T026 は並列実行可能(別ファイル)

---

## Parallel Example: User Story 1 と User Story 2

```bash
# US1とUS2は別ファイル・別関心事のため、Setup完了後は並行して着手できる:
Task: "scripts/fetch/backfill_tournament_events.py の実装(US1)"
Task: "scripts/fix/prune_empty_events.py の実装(US2)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup を完了
2. Phase 2: User Story 1 を完了
3. **STOP and VALIDATE**: `quickstart.md` 手順1・手順2前半で US1 を単独検証
4. この時点で「作り直されたイベントが自動的に発見・取得される」機能は実用可能な状態に
   なる(MVP)。空になった古いディレクトリの整理はまだ行われない

### Incremental Delivery

1. Setup → 基準状態確認
2. US1 追加 → 単独検証 → MVPとしてデプロイ可能(新イベント発見)
3. US2 追加 → 単独検証 → 空イベントディレクトリの自動整理が開始する
4. Polish → 新規ワークフロー作成・全体テスト・実環境での目視検証

---

## Notes

- [P] タスク = 別ファイル、または同一ファイルでも独立した追記でロジック依存なし
- テストは実装前に書き、失敗することを確認してから実装に進む
- 各チェックポイントで、そのユーザーストーリーが単独で検証可能であることを確認する
- 既存ファイル(`download.py`, `backfill_schema_version.py`)への変更は本機能のスコープ外
