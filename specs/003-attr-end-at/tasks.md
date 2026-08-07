---

description: "Task list for 003-attr-end-at"
---

# Tasks: イベント記録への大会終了日時(end_at)の保存

**Input**: Design documents from `/specs/003-attr-end-at/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/attr-json.md, quickstart.md

**Tests**: Constitution Principle III(検証ゲート、NON-NEGOTIABLE)により、新規ロジックには
テストを追加する。テストタスクを含む。

**Organization**: タスクは spec.md の User Story 1・2 ごとにグループ化。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並列実行可能(別ファイル、または同一ファイルでも独立した追記でロジック依存なし)
- **[Story]**: 対応するユーザーストーリー(US1, US2)
- ファイルパスは実際のリポジトリパスを明記

## Path Conventions

単一プロジェクト構成。`scripts/`, `docs/` を使用(plan.md の Project Structure 参照)。
新規ファイル・新規ワークフローは作成しない。

---

## Phase 1: Setup

**Purpose**: 変更前の基準状態を確認する

- [ ] T001 `python -m unittest scripts.test.test_download scripts.test.test_backfill_schema_version scripts.test.test_validate_data` を実行し、変更前の時点で全てパスすることを確認する(以降のタスクの差分検証の基準にする)

**Note**: 本機能は既存ファイルの局所的な変更のみで完結し、複数ユーザーストーリーが
共有する新規インフラ(DBスキーマ・認証基盤等)を必要としないため、独立した
Foundational フェーズは設けない。US2 は US1 の実装(特に T013)を前提に検証する
(詳細は Dependencies 参照)。

---

## Phase 2: User Story 1 - 新規・再取得イベントに終了日時を保存する (Priority: P1) 🎯 MVP

**Goal**: 大会一覧の一括取得・大会ID指定取得・スラッグ指定の個別取得・バックフィルによる
再取得の4経路すべてで、新規に書き込まれる `attr.json` に大会の終了日時(`end_at`)が
含まれるようにする。

**Independent Test**: `quickstart.md` 手順1・2(単体テスト実行 + 一括スキャン経路での
小規模実行)により、他のユーザーストーリーと独立に検証できる。

### Tests for User Story 1

- [ ] T002 [P] [US1] `scripts/test/test_download.py` に、`write_event_attributes()` へ
      `end_at` を渡すと `attr.json` の `end_at` フィールドにその値がそのまま書き込まれる
      ことを確認するテストを追加する(既存の
      `test_write_event_attributes_includes_version_and_guest_count` に倣う)
- [ ] T003 [P] [US1] 同ファイルに、`end_at` を渡さない(または `None` を渡す)場合、
      `attr.json` の `end_at` が `null` になり例外が発生しないことを確認するテストを
      追加する(FR-003 の後方互換確認)
- [ ] T004 [P] [US1] `scripts/test/test_backfill_schema_version.py` に、
      `fetch_event_details()` のレスポンスに含まれる `tournament.endAt` が
      `backfill_one_event()` を通じて `write_event_attributes()` に渡され、結果として
      `attr.json` の `end_at` に反映されることを確認するテストを追加する
- [ ] T005 [P] [US1] `scripts/test/test_validate_data.py` に、`end_at` を含まない
      (移行前形式の)`attr.json` でも `validate_event_dir()` が必須フィールドエラーを
      出さないことを確認する回帰テストを追加する(`end_at` を `ATTR_REQUIRED_FIELDS` に
      追加していないことの保証)

### Implementation for User Story 1

- [ ] T006 [P] [US1] `scripts/fetch/download.py` の `write_event_attributes()` に
      `end_at=None` 引数を追加し、`json_data["end_at"]` として書き込むようにする
- [ ] T007 [P] [US1] `scripts/fetch/download_specific_event.py` の独立定義された
      `write_event_attributes()` にも同様の変更を行う(T006 と同一内容、別実装への反映)
- [ ] T008 [US1] `scripts/fetch/download.py` の `download_all_tournaments()` 内の
      `write_event_attributes(...)` 呼び出しに、既存の `end_timestamp` 変数を
      `end_at=end_timestamp` として渡す(T006 に依存)
- [ ] T009 [US1] 同ファイルの `download_by_ids()` 内の `write_event_attributes(...)`
      呼び出しにも、既存の `end_timestamp` 変数を `end_at=end_timestamp` として渡す
      (T006 に依存)
- [ ] T010 [P] [US1] `scripts/queries.py` の `get_event_details_by_tournament_query()` の
      `tournament` ブロックに `endAt` フィールドを追加する
- [ ] T011 [US1] `scripts/fetch/download_specific_event.py` の
      `fetch_event_details_by_slug()` が返す統合辞書の `tournament` に
      `"endAt": tournament_data.get("endAt")` を追加する(T010 に依存)
- [ ] T012 [US1] 同ファイルの `download_specific_event()` に、
      `tournament_info.get("endAt")` を取り出して `write_event_attributes(...)` 呼び出しへ
      `end_at=` として渡す処理を追加する(T007, T011 に依存)
- [ ] T013 [US1] `scripts/fetch/backfill_schema_version.py` の `backfill_one_event()` に、
      `tournament.get("endAt")` を取り出して `write_event_attributes(...)` 呼び出しへ
      `end_at=` として渡す処理を追加する(T006 に依存)
- [ ] T014 [P] [US1] `docs/data_model.md` の `attr.json` スキーマ例に `end_at`
      フィールド(型・意味・`timestamp` との関係)を追記する

**Checkpoint**: 新規取得・スラッグ指定取得・バックフィルによる再取得のいずれの経路でも、
新しく書き込まれる `attr.json` に `end_at` が含まれるようになる。ここまでで
`quickstart.md` 手順1・2が独立に検証可能。

---

## Phase 3: User Story 2 - 既存の全イベントにも段階的に行き渡らせる (Priority: P2)

**Goal**: 新規のバックフィル専用スクリプトを追加せず、`EVENT_DATA_VERSION` を1つ上げる
だけで、既存の `event_data_version < 3` のイベントが `schema_backfill.yml` の通常の実行
サイクルの中で自動的に再取得対象として検出され、`end_at` を獲得できるようにする。

**Independent Test**: `end_at` を持たない(`event_data_version=2` の)イベント
ディレクトリを用意し、`backfill_schema_version.py` を1回実行して `end_at` と
`event_data_version=3` が追加されることを確認する(`quickstart.md` 手順3)。

### Tests for User Story 2

- [ ] T015 [P] [US2] `scripts/test/test_backfill_schema_version.py` に、
      `event_data_version=2`(`end_at` を持たない)の `attr.json` を用意した状態で
      バックフィルを実行すると、そのイベントが再取得対象として検出され、実行後に
      `attr.json` の `end_at` と `event_data_version=3` が更新されていることを確認する
      テストを追加する(既存の `002-incremental-schema-backfill` のバージョン比較
      ロジック自体は変更しないことの回帰確認を兼ねる)

### Implementation for User Story 2

- [ ] T016 [US2] `scripts/utils.py` の `EVENT_DATA_VERSION` を `2` から `3` に変更する
      (T013 が完了しており、バックフィル実行時に実際に `end_at` が反映されることが
      前提)

**Checkpoint**: 既存の `schema_backfill.yml`(`chore-update` ブランチへの定期コミット、
新規ワークフロー不要)が、次回実行から自動的に `end_at` を持たない既存イベントを
再取得対象に含めるようになる。

---

## Phase 4: Polish & Cross-Cutting Concerns

- [ ] T017 [P] `python -m unittest discover -s scripts/test -p "test_*.py"` を実行し、
      本機能で追加・変更したテストを含む全テストスイートがパスすることを確認する
- [ ] T018 `quickstart.md` 手順2(一括スキャン経路の小規模実行)と手順3
      (バックフィル経路の小規模実行)を実際の `STARTGG_TOKEN` で行い、生成された
      `attr.json` に `end_at` が正しく含まれることを目視確認する

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし、即着手可能
- **User Story 1 (Phase 2)**: Setup 完了後。他のユーザーストーリーへの依存なし
- **User Story 2 (Phase 3)**: Setup 完了後に着手可能だが、`backfill_one_event()` が
  `end_at` を渡すようになっていないと Independent Test が意味を持たないため、
  実質的に US1(特に T013)の後に実施する
- **Polish (Phase 4)**: 実施したいユーザーストーリーすべての完了後

### User Story Dependencies

- **US1 (P1)**: Setup 完了後に着手可能。他ストーリーに依存しない
- **US2 (P2)**: Setup 完了後に着手可能だが、US1 の T013(バックフィル経路での
  `end_at` 反映)がないと「既存イベントが `end_at` を獲得できる」ことを検証できない
  ため、実質的に US1 の後に実施する

### Parallel Opportunities

- US1 のテスト T002〜T005 は並列実行可能
- US1 の実装のうち T006・T007・T010・T014 は並列実行可能。T008・T009 は T006 に、
  T011・T012 は T010/T007 に、T013 は T006 に、それぞれ依存するため逐次実行
- US2 の T015・T016 は US1 完了後に実施(T016 は T013 に依存)
- Polish の T017 は単独で並列実行可能

---

## Parallel Example: User Story 1 実装

```bash
# T006, T007, T010, T014 は互いに独立ファイル(または独立追記)のため並列実行できる:
Task: "download.py の write_event_attributes() に end_at 引数を追加"
Task: "download_specific_event.py の write_event_attributes() に同様の変更"
Task: "queries.py の get_event_details_by_tournament_query() に endAt を追加"
Task: "docs/data_model.md に end_at を追記"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup を完了
2. Phase 2: User Story 1 を完了
3. **STOP and VALIDATE**: `quickstart.md` 手順1・2で US1 を単独検証
4. この時点で「新規取得・再取得されるイベントに `end_at` が保存される」機能は
   実用可能な状態になる(MVP)。既存イベントへの反映はまだ行われない

### Incremental Delivery

1. Setup → 基準状態確認
2. US1 追加 → 単独検証 → MVPとしてデプロイ可能
3. US2 追加(`EVENT_DATA_VERSION` バンプ) → 既存イベントへの段階的反映が開始する
4. Polish → 全体テスト・手動検証

---

## Notes

- [P] タスク = 別ファイル、または同一ファイルでも独立した追記でロジック依存なし
- US2 は独立した新規機能というより、US1 で実装した書き込みロジックを既存データへ
  波及させる「トリガー(バージョン定数)」の追加であり、既存の
  `002-incremental-schema-backfill` の仕組みをそのまま再利用する
- テストは実装前に書き、失敗することを確認してから実装に進む
- 各チェックポイントで、そのユーザーストーリーが単独で検証可能であることを確認する
