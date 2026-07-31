---

description: "Task list for 003-eligibility-restricted-labeling"
---

# Tasks: 大会属性判定ロジックの内製化(参加資格制限大会ラベル)

**Input**: Design documents from `/specs/003-eligibility-restricted-labeling/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: Constitution Principle III(検証ゲート、NON-NEGOTIABLE)により、新規ロジックには
テストを追加する。テストタスクを含む。

**Organization**: タスクはユーザーストーリー(spec.md の User Story 1〜2)ごとにグループ化。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並列実行可能(別ファイル・依存なし)
- **[Story]**: 対応するユーザーストーリー(US1, US2)
- ファイルパスは実際のリポジトリパスを明記

## Path Conventions

単一プロジェクト構成。`scripts/`, `docs/` を使用(plan.md の Project Structure 参照)。

---

## Phase 1: Setup

**Purpose**: 新規ファイルの骨格を用意する

- [ ] T001 `scripts/label_rules.py` を新規作成し、空の
      `REGISTRATION_RESTRICTED_KEYWORDS: list[str] = []` と、ロジック未実装の
      `is_registration_restricted()` 関数スタブを用意する
- [ ] T002 [P] `scripts/test/test_label_rules.py` を作成し、
      `scripts.label_rules` を import するだけの空テストケースを用意する
- [ ] T003 [P] `scripts/test/test_apply_registration_restricted_label.py` を作成し、
      (まだ存在しない)`scripts.fix.apply_registration_restricted_label` を
      import するだけの空テストケースを用意する

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: US1・US2 の両方が依存する判定ロジック本体

**⚠️ CRITICAL**: このフェーズが完了するまで、いずれのユーザーストーリーの実装も開始しない

- [ ] T004 `scripts/label_rules.py` の `is_registration_restricted(tournament_name, event_name)`
      を実装する。`tournament_name`/`event_name` のいずれかに
      `REGISTRATION_RESTRICTED_KEYWORDS` のいずれかが部分一致で含まれていれば
      `True` を返す。大文字小文字・全角半角の正規化は行わない(単純な `in` 判定)。
      値が `None`/空文字列でも例外を出さず `False` を返す
- [ ] T005 [P] `scripts/test/test_label_rules.py` に、以下を確認するテストを追加する:
      トーナメント名に一致するキーワードが含まれる場合に `True`、イベント名に
      含まれる場合に `True`、どちらにも含まれない場合に `False`、
      `tournament_name`/`event_name` が `None` や空文字列でも例外にならず `False`、
      `REGISTRATION_RESTRICTED_KEYWORDS` が空リストの場合は常に `False`

**Checkpoint**: 判定ロジック単体が完成・テスト済み。ここから各ユーザーストーリーの
実装に進める。

---

## Phase 3: User Story 1 - 新規取得イベントに参加資格制限ラベルを自動付与する (Priority: P1) 🎯 MVP

**Goal**: start.gg から新規にイベントデータを取得する際、`attr.json` の
`labels.registration_restricted` が自動的に設定され、既存の `labels` プロパティは
破壊されない。

**Independent Test**: `quickstart.md` 手順1(単体テスト実行)により、他のユーザー
ストーリーと独立に検証できる。

### Tests for User Story 1

- [ ] T006 [P] [US1] `scripts/test/test_download.py` に、`write_event_attributes()`
      が判定キーワードに一致する `tournament_name` を与えられたとき
      `attr.json` の `labels.registration_restricted` に `true` を書き込み、
      かつ呼び出し時に渡した既存の `labels` プロパティ(例: `registration_type`)を
      保持したまま追加することを確認するテストを追加する

### Implementation for User Story 1

- [ ] T007 [US1] `scripts/fetch/download.py` の `write_event_attributes()` を変更し、
      内部で `labels = {**(labels or {}), "registration_restricted": is_registration_restricted(tournament_name, event_name)}`
      のように非破壊マージしてから `json_data["labels"]` に設定する(呼び出し元
      2箇所のシグネチャ変更は不要)
- [ ] T008 [US1] `scripts/fetch/download_specific_event.py` の
      `write_event_attributes()`(独自実装)にも同様の変更を行う(T007 と同一内容、
      別実装への反映。既存のテストが無いモジュールのため、
      `python -m py_compile` と手動での動作確認で担保する)
- [ ] T009 [P] [US1] `docs/data_model.md` の `attr.json` の `labels` サンプルに
      `registration_restricted` を追記し、判定文字列リストが
      `scripts/label_rules.py` で管理される旨を「注意点」セクションに追記する
      (data-model.md の「`docs/data_model.md` への追記内容」参照)

**Checkpoint**: User Story 1 は独立に動作・検証可能(`quickstart.md` 手順1)。

---

## Phase 4: User Story 2 - 既存の全イベントデータに判定を一括適用する (Priority: P1)

**Goal**: start.gg への再アクセスなしに、既存の全イベントディレクトリの
`attr.json` の `labels.registration_restricted` を、現在の判定文字列リストに
基づいて再計算・更新する手動実行ツールを提供する。

**Independent Test**: `quickstart.md` 手順2(一時ディレクトリでの実行)により、
他のユーザーストーリーと独立に検証できる。

### Tests for User Story 2

- [ ] T010 [P] [US2] `scripts/test/test_apply_registration_restricted_label.py` に、
      判定キーワードに一致するイベントの `labels.registration_restricted` が
      `true` に更新されることを確認するテストを追加する
- [ ] T011 [P] [US2] 同ファイルに、`labels` に既存の他プロパティを持つイベントを
      処理しても、そのプロパティが変化しないことを確認するテストを追加する
- [ ] T012 [P] [US2] 同ファイルに、`attr.json` が存在しない/JSONとして壊れている
      イベントディレクトリに遭遇しても処理全体が停止せず、残りのディレクトリを
      処理し続けることを確認するテストを追加する
- [ ] T013 [P] [US2] 同ファイルに、同じ入力に対してツールを2回実行しても
      2回目で余計な変更が発生しない(冪等)ことを確認するテストと、
      実行中に `scripts.utils.fetch_data_with_retries` 等のAPI関連関数が
      一切呼び出されない(importもしていない)ことを確認する静的チェックの
      テストを追加する

### Implementation for User Story 2

- [ ] T014 [US2] `scripts/fix/apply_registration_restricted_label.py` に、
      `--events_root` 以下の `attr.json` を列挙し、各ファイルを読み込んで
      `is_registration_restricted()` で再判定し、`labels` を非破壊マージした
      うえで、値が変化した場合のみ書き戻すロジックを実装する
      (`data-model.md` の処理フロー参照)。壊れた/存在しない `attr.json` は
      スキップして処理を継続する(T012 に対応)
- [ ] T015 [US2] 同ファイルに、`contracts/cli.md` に定義された引数
      (`--events_root`, `--indent_num`)を処理する `main()` と、終了時の要約行
      (`Done. updated=X unchanged=Y skipped=Z`)の出力を実装する(T014 に依存)

**Checkpoint**: User Story 2 は独立に動作・検証可能(`quickstart.md` 手順2〜3)。

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T016 [P] `python -m unittest scripts.test.test_label_rules`,
      `scripts.test.test_apply_registration_restricted_label`,
      `scripts.test.test_download`, `scripts.test.test_validate_data` を実行し、
      既存の全テストスイートも含めてすべてパスすることを確認する
- [ ] T017 `quickstart.md` の手順2・3(一時ディレクトリでの実行、実データに対する
      `git diff` での事前確認)を実際に行い、結果を確認する
      (start.gg トークン・ネットワーク不要のため、この機能はローカルで
      完全に検証可能)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし、即着手可能
- **Foundational (Phase 2)**: Setup 完了後。全ユーザーストーリーをブロックする
- **User Story 1 (Phase 3)**: Foundational 完了後。User Story 2 への依存なし
- **User Story 2 (Phase 4)**: Foundational 完了後。User Story 1 への依存なし
  (判定ロジックを共有するのみで、実装は独立)
- **Polish (Phase 5)**: 実施したいユーザーストーリーすべての完了後

### User Story Dependencies

- **US1 (P1)**: Foundational 完了後に着手可能。US2 に依存しない
- **US2 (P1)**: Foundational 完了後に着手可能。US1 に依存しない
  (両者とも `scripts/label_rules.py` の関数を呼ぶだけで、互いのファイルには
  触れない)

### Parallel Opportunities

- Setup の T002・T003 は並列実行可能
- Foundational の T005 は T004 完了後に実行
- US1 の T006・T009 は並列実行可能。T007・T008 は同じ関数パターンを別ファイルに
  適用するため独立して並列実行可能
- US2 の T010〜T013 は並列実行可能
- Foundational 完了後は、US1(T006〜T009)と US2(T010〜T015)を並行して
  進めることができる(ファイルが重複しないため)

---

## Parallel Example: Foundational 完了後

```bash
# US1 と US2 を同時に着手できる:
Task: "write_event_attributes() に labels.registration_restricted の非破壊マージを実装 (US1)"
Task: "apply_registration_restricted_label.py の走査・更新ロジックを実装 (US2)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup を完了
2. Phase 2: Foundational を完了(判定ロジック)
3. Phase 3: User Story 1 を完了
4. **STOP and VALIDATE**: `quickstart.md` 手順1で US1 を単独検証
5. この時点で「新規取得データへの自動ラベル付与」は実用可能(MVP)

### Incremental Delivery

1. Setup + Foundational → 判定ロジック完成
2. US1 追加 → 単独検証 → 新規取得分から反映開始(MVP)
3. US2 追加 → 単独検証 → 既存の全データへ一括反映
4. Polish → 全体テスト・実データでの最終確認

---

## Notes

- [P] タスク = 別ファイル・依存なし
- US1・US2 は同じ判定ロジック(`scripts/label_rules.py`)を共有するが、
  ファイルは重複しないため独立して並行実装できる
- テストは実装前に書き、失敗することを確認してから実装に進む
- 各チェックポイントで、そのユーザーストーリーが単独で検証可能であることを確認する
