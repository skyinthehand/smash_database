---

description: "Task list for 002-incremental-schema-backfill"
---

# Tasks: 既存イベントへのスキーマ追加フィールドの段階的バックフィル

**Input**: Design documents from `/specs/002-incremental-schema-backfill/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: Constitution Principle III(検証ゲート、NON-NEGOTIABLE)により、新規ロジックには
テストを追加する。テストタスクを含む。

**Organization**: タスクはユーザーストーリー(spec.md の User Story 1〜3)ごとにグループ化。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並列実行可能(別ファイル・依存なし)
- **[Story]**: 対応するユーザーストーリー(US1, US2, US3)
- ファイルパスは実際のリポジトリパスを明記

## Path Conventions

単一プロジェクト構成。`scripts/`, `.github/workflows/`, `docs/`, `data/startgg/` を使用
(plan.md の Project Structure 参照)。

---

## Phase 1: Setup

**Purpose**: 新規ファイルの骨格を用意する

- [ ] T001 `scripts/fetch/backfill_schema_version.py` に空の argparse スケルトン
      (`contracts/cli.md` の引数一覧を反映した `main()` のみ、ロジックは未実装)を作成する
- [ ] T002 [P] `scripts/test/test_backfill_schema_version.py` を作成し、
      `scripts.fetch.backfill_schema_version` を import するだけの空テストケースを用意する

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: すべてのユーザーストーリーが依存する土台(バージョン定数と書き込みロジック)

**⚠️ CRITICAL**: このフェーズが完了するまで、いずれのユーザーストーリーの実装も開始しない

- [ ] T003 `scripts/utils.py` に `EVENT_DATA_VERSION = 1` 定数を、既存の `JSON_VERSION`
      の直後に追加する
- [ ] T004 [P] `scripts/fetch/download.py` の `write_event_attributes()` を変更し、
      呼び出しのたびに `scripts.utils.EVENT_DATA_VERSION` の値を `attr.json` の
      `event_data_version` フィールドとして常に書き込むようにする(新規引数は追加せず、
      関数内部で定数を直接参照する。これにより呼び出し元 `redownload_event.py` /
      `backfill_events.py` の呼び出しシグネチャは変更不要)
- [ ] T005 [P] `scripts/fetch/download_specific_event.py` の `write_event_attributes()`
      にも同様の変更を行う(T004 と同一内容、別実装への反映)
- [ ] T006 [P] `docs/data_model.md` の `attr.json` サンプルに `event_data_version` を
      追記し、「注意点」セクションに既存の `version` フィールドとは別物である旨を追記する
      (data-model.md の「`docs/data_model.md` への追記内容」参照)
- [ ] T007 [P] `scripts/test/test_validate_data.py` に、`event_data_version` を含まない
      `attr.json` でも `validate_event_dir()` が必須フィールドエラーを出さないことを
      確認する回帰テストを追加する(`ATTR_REQUIRED_FIELDS` に追加していないことの保証)

**Checkpoint**: 新規・再取得されるすべてのイベントが自動的に `event_data_version` を
持つようになる。ここから各ユーザーストーリーの実装に進める。

---

## Phase 3: User Story 1 - スケジュール処理で段階的にバックフィルする (Priority: P1) 🎯 MVP

**Goal**: 既存イベントのうち `event_data_version` が古いものを、安定ソート順の循環スキャンと
永続化カーソルにより、1回の実行につき上限件数まで自動的に再取得・更新する。

**Independent Test**: `quickstart.md` の手順1・2(単体テスト実行 + 一時ディレクトリでの
少数実行)により、他のユーザーストーリーと独立に検証できる。

### Tests for User Story 1

- [ ] T008 [P] [US1] `scripts/test/test_backfill_schema_version.py` に、
      `event_data_version` が無い/現在の `EVENT_DATA_VERSION` より低いイベント
      ディレクトリが対象として検出されるテストを追加する
- [ ] T009 [P] [US1] 同ファイルに、カーソルファイルを使って2回実行した際、
      1回目で処理した分を2回目でスキップし、続きから処理されることを確認するテストを
      追加する
- [ ] T010 [P] [US1] 同ファイルに、`event_data_version` が既に最新のイベントは
      再取得関数(モック)を一切呼び出さずスキップされることを確認するテストを追加する
- [ ] T011 [P] [US1] 同ファイルに、対象が1件もない状態で実行すると、
      再取得関数を呼ばずに終了コード0で正常終了する(FR-010)ことを確認するテストと、
      全ディレクトリを一周した場合にカーソルが先頭に戻ることを確認するテストを追加する

### Implementation for User Story 1

- [ ] T012 [US1] `scripts/fetch/backfill_schema_version.py` に、イベントディレクトリの
      安定ソート順列挙(`pathlib.Path.rglob("attr.json")` の結果をパス文字列でソート)と、
      カーソルファイル(`--cursor_path`)の読み込み/開始位置決定ロジックを実装する
- [ ] T013 [US1] 同ファイルに、各ディレクトリの `attr.json` から `event_data_version`
      を読み(無ければ0扱い)、目標バージョン未満のものだけを処理対象とし、
      `--max_events` に達するか一周するまでスキャンを続けるループを実装する
      (T012 に依存)
- [ ] T014 [US1] 同ファイルに、対象イベントの実際の再取得処理
      (`scripts.fetch.download` の `download_standings` / `download_seeds` /
      `download_all_set` / `extend_user_info` / `write_event_attributes` を、
      `scripts/fix/redownload_event.py` と同様の呼び出しパターンで使用)を実装する
      (T013 に依存)
- [ ] T015 [US1] 同ファイルに、`contracts/cli.md` に定義された引数
      (`--token`, `--events_root`, `--users_file_path`, `--cursor_path`, `--max_events`,
      `--max_retries`, `--retry_delay`, `--indent_num`, `--url`)を処理する `main()` と、
      終了時のカーソル書き込み、および要約行
      (`Done. processed=X skipped=Y wrapped_around=Z`)の出力を実装する(T014 に依存)
- [ ] T016 [US1] `.github/workflows/schema_backfill.yml` を新規作成し、
      `schedule`(日次 cron、初期値)と `workflow_dispatch` のトリガー、
      checkout / setup-python / install の各ステップ、および
      `scripts/fetch/backfill_schema_version.py` を実行するステップを、
      `update_tournament.yml` の構成に倣って実装する(T015 に依存)

**Checkpoint**: User Story 1 は独立に動作・検証可能(`quickstart.md` 手順1〜3)。

---

## Phase 4: User Story 2 - 将来追加されるフィールドにも同じ仕組みを再利用する (Priority: P2)

**Goal**: 新フィールド追加時に `EVENT_DATA_VERSION` を1つ上げるだけで、
`backfill_schema_version.py` 自体を変更せずに対象イベントが再検出されることを保証する。

**Independent Test**: `EVENT_DATA_VERSION` を一時的に +1 した状態でテストを実行し、
既存の「最新」イベントが再び対象になることを確認する。

### Tests for User Story 2

- [ ] T017 [P] [US2] `scripts/test/test_backfill_schema_version.py` に、
      `scripts.utils.EVENT_DATA_VERSION` を monkeypatch で +1 し、
      それまで「最新」だったイベント(旧バージョンの `event_data_version` を持つ)が
      再び対象として検出されることを確認するテストを追加する(スキャン・カーソル
      ロジック自体には一切手を加えない)

### Implementation for User Story 2

- [ ] T018 [US2] `scripts/utils.py` の `EVENT_DATA_VERSION` 定義箇所に、
      「新フィールドを追加する際はこの値を1つ上げ、対応する取得・保存ロジックの変更と
      `docs/data_model.md` の更新を同一PRに含める」という運用ルールをコメントとして
      記載する(T003 に依存)

**Checkpoint**: 新フィールド追加が「定数を1つ上げる + 取得ロジック実装」だけで
バックフィル対象に組み込まれることが T017 で保証される。

---

## Phase 5: User Story 3 - 既存の取得基盤・運用ルールと衝突しない (Priority: P2)

**Goal**: 本機能のワークフローが `chore-update` ブランチ規律・concurrency グループ・
既存のAPIリトライ基盤と衝突しないことを保証する。

**Independent Test**: ワークフローYAMLのレビューと、`scripts/fetch/backfill_schema_version.py`
が独自のAPI実装を持たないことの静的確認。

### Implementation for User Story 3

- [ ] T019 [US3] `.github/workflows/schema_backfill.yml` に
      `concurrency: { group: chore-update-branch, cancel-in-progress: true }` を追加する
      (T016 に依存)
- [ ] T020 [US3] 同ワークフローに、`chore-update` ブランチの準備・コミット・
      push(失敗時は `git pull --rebase` してリトライ)の各ステップを、
      `update_tournament.yml` と同一パターンで追加する(`main` へ直接pushしない)
      (T019 に依存)
- [ ] T021 [US3] 同ワークフローに、「`chore-update` → `main` のオープンPRが無ければ
      作成する」ステップを `update_tournament.yml` から流用して追加する(T020 に依存)

### Tests for User Story 3

- [ ] T022 [P] [US3] `scripts/test/test_backfill_schema_version.py` に、
      `scripts/fetch/backfill_schema_version.py` が `scripts.utils.fetch_data_with_retries`
      / `fetch_all_nodes` 経由でのみAPIアクセスし、`requests`/`urllib` を直接importして
      いないことを確認する静的チェックのテストを追加する

**Checkpoint**: ワークフローが既存の日次更新群と同一の concurrency グループ・
ブランチ規律を共有し、独自のAPIアクセス経路を持たないことが保証される。

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T023 [P] `python -m unittest scripts.test.test_backfill_schema_version` と
      `python -m unittest scripts.test.test_validate_data` を実行し、
      すべてパスすることを確認する
- [ ] T024 `quickstart.md` の手順2(一時ディレクトリでの少数実行)と手順3
      (`gh workflow run schema_backfill.yml` による手動実行)を実際に行い、結果を確認する
- [ ] T025 [P] `docs/githubAction.md` に `schema_backfill.yml` の説明を追記し、
      既存の日次ワークフロー一覧に追加する

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし、即着手可能
- **Foundational (Phase 2)**: Setup 完了後。全ユーザーストーリーをブロックする
- **User Story 1 (Phase 3)**: Foundational 完了後。他のユーザーストーリーへの依存なし
- **User Story 2 (Phase 4)**: Foundational 完了後。US1 の `backfill_schema_version.py`
  (T012〜T015)が存在することを前提にテストする(スキャンロジックの検証のため)
- **User Story 3 (Phase 5)**: Foundational 完了後。US1 の `schema_backfill.yml`
  (T016)が存在することを前提に拡張する
- **Polish (Phase 6)**: 実施したいユーザーストーリーすべての完了後

### User Story Dependencies

- **US1 (P1)**: Foundational 完了後に着手可能。他ストーリーに依存しない
- **US2 (P2)**: Foundational 完了後に着手可能だが、US1 のスキャンロジック実装(T012〜T013)
  がないとテスト対象が存在しないため、実質的に US1 の後に実施する
- **US3 (P2)**: Foundational 完了後に着手可能だが、US1 のワークフロー(T016)を拡張する
  形のため、実質的に US1 の後に実施する

### Parallel Opportunities

- Setup の T001・T002 は並列実行可能
- Foundational の T004・T005・T006・T007 は並列実行可能(T003 完了後)
- US1 のテスト T008〜T011 は並列実行可能
- US1 の実装 T012〜T016 は逐次(同一ファイルへの積み上げのため)
- US2 の T017、US3 の T022 は他の並列タスクと同時に実行可能

---

## Parallel Example: Foundational Phase

```bash
# T003 完了後、以下を並列実行できる:
Task: "scripts/fetch/download.py の write_event_attributes() に event_data_version 書き込みを追加"
Task: "scripts/fetch/download_specific_event.py の write_event_attributes() に同様の変更"
Task: "docs/data_model.md に event_data_version を追記"
Task: "scripts/test/test_validate_data.py に後方互換の回帰テストを追加"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup を完了
2. Phase 2: Foundational を完了(全ストーリーの前提)
3. Phase 3: User Story 1 を完了
4. **STOP and VALIDATE**: `quickstart.md` 手順1〜3で US1 を単独検証
5. この時点で「手動 `workflow_dispatch` によるスケジュール的バックフィル」は
   実用可能な状態になる(MVP)

### Incremental Delivery

1. Setup + Foundational → 基盤完成
2. US1 追加 → 単独検証 → MVPとしてデプロイ可能
3. US2 追加 → 拡張性を保証するテストを追加(実装変更は最小限)
4. US3 追加 → ワークフローの運用安全性を強化
5. Polish → ドキュメント整備・最終確認

---

## Notes

- [P] タスク = 別ファイル・依存なし
- US2・US3 は独立した新規機能というより、US1で実装する単一の仕組みに対する
  「拡張性」「運用安全性」という品質特性を検証・保証するタスク群である
- テストは実装前に書き、失敗することを確認してから実装に進む
- 各チェックポイントで、そのユーザーストーリーが単独で検証可能であることを確認する
