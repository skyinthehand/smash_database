# Tasks: 取得対象からのイベント除外

**Input**: Design documents from `/specs/007-exclude-events/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: 本プロジェクトの憲法(Principle III「マージ前の検証ゲート」)により、
新しいデータ形状・挙動を追加する場合は対応するテストが MUST。そのため、
以下の各タスクにテストタスクを含める(一般的なテンプレートでは省略可能
だが、本フィーチャーでは必須)。

**Organization**: `spec.md`のUser Story(P1/P2/P3)ごとにグループ化。

## Path Conventions

既存のリポジトリ構成(`scripts/fetch/`・`scripts/fix/`・`scripts/test/`・
`docs/`・`data/startgg/`)にそのまま従う。`plan.md`のProject Structure参照。

---

## Phase 1: Setup

**Purpose**: 除外リストファイルのリネーム(コード変更に先立つ準備)

- [X] T001 `data/startgg/excluded_phases.json` を `data/startgg/excluded_events.json`
  へ `git mv` でリネームする(既存のphase単位除外エントリはそのまま
  引き継がれる。`research.md` Decision 1)。

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 全User Storyが依存する、除外リストの読み込みロジック

**⚠️ CRITICAL**: このフェーズが完了するまで、どのUser Storyの実装にも
着手できない。

- [X] T002 `scripts/fetch/download.py` の定数 `EXCLUDED_PHASES_PATH` を
  `EXCLUDED_EVENTS_PATH = "data/startgg/excluded_events.json"` へ
  リネームする(`load_excluded_phase_ids()`のデフォルト引数を含む)。
- [X] T003 `scripts/fetch/download.py` の `load_excluded_phase_ids()` を
  修正し、値が配列(`list`)形状のエントリのみを対象にする(`dict`形状
  = イベント全体除外エントリは黙ってスキップする)ガードを追加する
  (依存: T002)。
- [X] T004 `scripts/fetch/download.py` に新規関数 `load_excluded_event_ids(path=EXCLUDED_EVENTS_PATH)`
  を追加する。ファイルを読み込み、値が`dict`かつ`"reason"`キーを直下に
  持つエントリのみを対象に、`{event_id(int): {"reason": str}}` を返す
  (ファイル未存在/不正な場合は空辞書。`load_excluded_phase_ids()`と
  同じtry/exceptパターンを踏襲)(依存: T002)。
- [X] T005 `scripts/test/test_download.py` に、T003・T004の単体テストを
  追加する: (a) `load_excluded_phase_ids()`が、統合後ファイルに混在する
  イベント全体除外エントリ(dict形状)を無視し、従来通りphase単位の
  エントリのみを返すこと、(b) `load_excluded_event_ids()`が、dict形状の
  イベント全体除外エントリのみを返し、配列形状のphase除外エントリを
  無視すること、(c) いずれもファイル未存在時は空辞書を返すこと、
  (d) 【FR-008回帰テスト】あるevent_idのエントリをファイルから削除した
  状態で`load_excluded_event_ids()`を呼び直すと、そのevent_idがもはや
  結果に含まれないこと(除外解除がエントリ削除のみで即座に反映される
  ことの確認。`/speckit-analyze`指摘 U1)(依存: T003, T004)。

**Checkpoint**: この時点で `load_excluded_event_ids()` が正しく動作し、
以降のUser Storyから利用できる状態になっている。

---

## Phase 3: User Story 1 - 問題のあるイベントを自動取得から除外する (Priority: P1) 🎯 MVP

**Goal**: 通常のクロール処理(`download_all_tournaments`/`download_by_ids`)
が、除外リストに登録されたevent_idのディレクトリを作成せず、
`tournaments.jsonl`にも記載しない。

**Independent Test**: あるevent_idを除外リストに登録した状態で通常の
クロールを実行し、そのevent_idに対応するディレクトリが作成されず、
`tournaments.jsonl`にも一切記載されないことを確認する。

### Implementation for User Story 1

- [X] T006 [US1] `scripts/fetch/download.py` の `download_all_tournaments()`
  内、`event_dir = get_event_directory(...)` の直後に、
  `load_excluded_event_ids()` を用いた除外チェックを追加する。
  除外対象であれば、そのイベントの `update_event_registration()` 呼び出し・
  ディレクトリ作成・データ取得を一切行わずスキップし、既存の他の
  スキップ理由(`already downloaded`等)と同様の1行ログを出力する
  (FR-003, FR-004, FR-004a)(依存: T004)。
- [X] T007 [US1] `scripts/fetch/download.py` の `download_by_ids()` 内、
  同様に `event_dir = get_event_directory(...)` の直後に除外チェックを
  追加し、除外対象であればスキップしてログを出力する(FR-003, FR-004,
  FR-004a)(依存: T004。T006と同一ファイルのため順序を空けて実施)。
- [X] T008 [US1] `scripts/test/test_download.py` に、T006・T007の統合
  テストを追加する: 除外リストに登録済みのevent_idを含むトーナメントに
  対して `download_all_tournaments()`/`download_by_ids()` を実行し、
  (a) そのevent_idのディレクトリが作成されないこと、(b) `tournaments.jsonl`
  にそのevent_idが記載されないこと、(c) 除外の旨のログが出力される
  こと、(d) 除外リストに無い他のevent_idは従来通り取得・登録される
  こと、を検証する(依存: T006, T007)。

**Checkpoint**: 通常のクロール経路での除外がここまでで機能する
(MVP達成)。

---

## Phase 4: User Story 2 - 除外理由を後から確認できる (Priority: P2)

**Goal**: 除外リストファイルおよびドキュメントを見れば、追加のツール無しに
除外理由が分かる状態にする。

**Independent Test**: 除外リストにevent_idを1件追加し、そのファイルを
直接開くことで、event_id・除外理由の2項目が記録されていることを確認する。

**Note**: 本User Storyの主要な要求(ファイル単体で読める)は、Phase 1
(リネーム)・Phase 2(スキーマ確定)により既に満たされている。ここでは
Constitution Principle Iに従ったドキュメント更新のみを行う。

### Implementation for User Story 2

- [X] T009 [P] [US2] `docs/data_model.md` の「管理ファイル」節に、
  `data/startgg/excluded_events.json` の説明(2種類のエントリ形状
  ——配列=phase単位除外、`reason`直下のオブジェクト=イベント全体除外
  ——と、除外日時をフィールドとして持たない旨)を追加する(`data-model.md`
  の内容を転記・要約する)。
- [X] T010 [P] [US2] `docs/fix.md` の `excluded_phases.json` への
  言及箇所を `excluded_events.json` に更新する。
- [X] T011 [P] [US2] `docs/startgg_design.md` の `excluded_phases.json`
  への言及箇所を `excluded_events.json` に更新する。

**Checkpoint**: 除外リストの内容・スキーマがドキュメントからも追跡できる。

---

## Phase 5: User Story 3 - どの取得経路から実行しても除外が有効である (Priority: P3)

**Goal**: 個別イベント手動取得ツール、および`tournaments.jsonl`の抜け
補完・検証系ツール(計4ツール)も、除外リストに登録されたevent_idを
スキップする。

**Independent Test**: 除外リストに登録済みのevent_idを、個別イベント
取得ツールに明示的に指定して実行し、そのツールが除外されていることを
検知して取得をスキップすることを確認する。

**Note**: `check_events_in_tournaments.py`・`fix_missing_tournaments.py`
は、`/speckit-analyze`によるレビュー(指摘U2)で対象に追加された
(Assumptions参照: これらを対象外のままにすると、除外後もディレクトリが
残存する既存イベントが誤って`tournaments.jsonl`へ再登録されうる)。

### Implementation for User Story 3

- [X] T012 [P] [US3] `scripts/fix/redownload_event.py` の
  `redownload_event()` 内、`find_existing_event_dir()` 呼び出しの直後に、
  `load_excluded_event_ids()`(`scripts.fetch.download`からimport)を
  用いた除外チェックを追加する。除外対象であれば、削除・再取得を一切
  行わずスキップし、既存の`print(f"[{event_id}] ...")`スタイルで除外の
  旨を報告する(FR-006)(依存: T004)。
- [X] T013 [P] [US3] `scripts/fix/backfill_tournament_index.py` の
  `scan_and_fill()` 内、`os.path.isdir(event_dir)` チェックの近くに、
  同様の除外チェックを追加する。除外対象であれば、そのevent_idを
  `tournaments`辞書への追加対象から除外し、既存の`print(f"[ADD] ...")`
  に倣ったスタイルで除外の旨を報告する(FR-006)(依存: T004)。
- [X] T014 [P] [US3] `scripts/fix/check_events_in_tournaments.py` の
  `main()` 内、`event_id = attr.get("event_id")` で event_id が判明した
  直後に、同様の除外チェックを追加する。除外対象であれば、
  `missing_events` への追加を行わずスキップし、既存の
  `print(f"[SKIP] ...")` に倣って `print(f"[SKIP-EXCLUDED] {event_dir}: ...")`
  のような1行を出力する(FR-006)(依存: T004)。
- [X] T015 [P] [US3] `scripts/fix/fix_missing_tournaments.py` の
  `clean_tournaments()` を修正し、`excluded_event_ids`(集合)を引数に
  追加する。`for event in events:` ループ内、`check_event()` 呼び出しの
  前に、`event.get("event_id")` が除外対象かどうかを確認し、除外対象で
  あれば `check_event()` を呼ばずそのまま `kept_events` に含める(検証・
  削除判定の対象から除外する)。既存の `report_lines.append(f"[OK] ...")`/
  `f"[REMOVE] ...")` に倣って `report_lines.append(f"[EXCLUDED] ...")` を
  追加する。`main()` 側で `load_excluded_event_ids()` を呼び出し
  `clean_tournaments()` に渡すよう更新する(FR-006)(依存: T004)。
- [X] T016 [P] [US3] 新規ファイル `scripts/test/test_redownload_event.py`
  を作成し、T012の除外スキップ挙動(除外対象event_idに対して
  `redownload_event()` がAPI呼び出し・ディレクトリ削除/作成を一切
  行わないこと、除外の旨を報告すること)を検証するテストを追加する
  (依存: T012)。
- [X] T017 [P] [US3] `scripts/test/test_backfill_tournament_index.py` に、
  T013の除外スキップ挙動(除外対象event_idに対応するディレクトリが
  ローカルに存在していても、`tournaments`への追加対象として扱われない
  こと)を検証するテストを追加する(依存: T013)。
- [X] T018 [P] [US3] 新規ファイル `scripts/test/test_check_events_in_tournaments.py`
  を作成し、T014の除外スキップ挙動(除外対象event_idに対応するディレク
  トリ(attr.json含む)が存在していても、`missing_events`に含まれない
  こと)を検証するテストを追加する(依存: T014)。
- [X] T019 [P] [US3] 新規ファイル `scripts/test/test_fix_missing_tournaments.py`
  を作成し、T015の除外スキップ挙動(除外対象event_idのエントリが
  `tournaments.jsonl`に存在する場合、ファイル完全性チェックの対象になら
  ずそのまま`kept_events`に残ること)を検証するテストを追加する
  (依存: T015)。

**Checkpoint**: 全ての対象エントリポイント(通常クロール・個別手動取得・
`tournaments.jsonl`補完2種・`tournaments.jsonl`検証削除)で除外が
一貫して機能する。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 全体の整合性確認

- [X] T020 `python3 -m unittest discover -s scripts/test` を実行し、
  リポジトリ全体のテストが通ることを確認する(憲法Principle III)。
- [X] T021 `quickstart.md` の手順1〜7を通しで実施し、エンドツーエンドの
  動作(除外の追加・全4エントリポイントでのスキップ・可読性・解除・
  既存phase除外の回帰確認)を確認する。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし。即座に着手可能。
- **Foundational (Phase 2)**: Setup完了後に着手(T001完了後、T002〜T005)。
  全User Storyをブロックする。
- **User Story 1 (Phase 3)**: Foundational完了後に着手可能。他のUser
  Storyへの依存なし。
- **User Story 2 (Phase 4)**: Foundational完了後に着手可能(Phase 1で
  リネーム済み・Phase 2でスキーマ確定済みのため、実質的にドキュメント
  作業のみ)。User Story 1への依存なし。
- **User Story 3 (Phase 5)**: Foundational完了後に着手可能。User Story
  1・2への依存なし。
- **Polish (Phase 6)**: 実施した全User Storyの完了後。

### Within Each Phase

- Phase 2: T002 → T003 → T004(いずれも同一ファイルの近接箇所を編集する
  ため逐次)。T005はT003・T004の後。
- Phase 3: T006 → T007(同一ファイル)。T008は両方の後。
- Phase 4: T009・T010・T011は互いに独立(別ファイル)。
- Phase 5: T012・T013・T014・T015は互いに独立(いずれも別ファイル)。
  T016はT012の後、T017はT013の後、T018はT014の後、T019はT015の後
  (ただしT016〜T019自体は互いに独立)。

### Parallel Opportunities

- Phase 4のT009・T010・T011は並行実施可能。
- Phase 5のT012・T013・T014・T015(実装4件)は並行実施可能。それぞれの
  直後のテスト(T016〜T019)も、互いには並行実施可能。
- User Story 1・2・3は、Foundational完了後であれば互いに並行して着手
  可能(担当を分けられる場合)。

---

## Parallel Example: Phase 5 (User Story 3)

```bash
# T012〜T015は別ファイルのため並行実施可能:
Task: "redownload_event.py の redownload_event() に除外チェックを追加"
Task: "backfill_tournament_index.py の scan_and_fill() に除外チェックを追加"
Task: "check_events_in_tournaments.py の main() に除外チェックを追加"
Task: "fix_missing_tournaments.py の clean_tournaments() に除外チェックを追加"

# それぞれの完了後、対応するテストも並行実施可能:
Task: "test_redownload_event.py を新規作成し除外スキップのテストを追加"
Task: "test_backfill_tournament_index.py に除外スキップのテストを追加"
Task: "test_check_events_in_tournaments.py を新規作成し除外スキップのテストを追加"
Task: "test_fix_missing_tournaments.py を新規作成し除外スキップのテストを追加"
```

---

## Implementation Strategy

### MVP First (User Story 1 のみ)

1. Phase 1: Setup を完了
2. Phase 2: Foundational を完了(重要 — 全User Storyをブロックする)
3. Phase 3: User Story 1 を完了
4. **停止して検証**: `quickstart.md` 手順1〜2でUser Story 1単独の動作を確認
5. ここまでで、最も優先度の高い「通常クロールでの除外」がMVPとして機能する

### Incremental Delivery

1. Setup + Foundational → 基盤完成
2. User Story 1 追加 → 単独で検証 → MVP
3. User Story 2 追加(ドキュメント整備) → 単独で検証
4. User Story 3 追加(他ツール4種への適用) → 単独で検証
5. Polish(全体テスト・quickstart通し確認)

---

## Notes

- `[P]` タスク = 別ファイル・依存なし
- `[Story]` ラベルはUser Storyへのトレーサビリティのため
- 各User Storyは独立して完了・検証可能
- タスクごと、または論理的なまとまりごとにコミットする
- 各チェックポイントで、そのUser Storyが単独で動作することを確認してから
  次に進む
