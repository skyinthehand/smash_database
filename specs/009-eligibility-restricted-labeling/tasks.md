---

description: "Task list for 009-eligibility-restricted-labeling"
---

# Tasks: 汎用イベントラベリング機構(大会名・イベント名ルールベース判定)

**Input**: Design documents from `/specs/009-eligibility-restricted-labeling/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: Constitution Principle III(検証ゲート、NON-NEGOTIABLE)により、新規ロジックには
テストを追加する。テストタスクを含む。

**Organization**: タスクはユーザーストーリー(spec.md の User Story 1〜4)ごとにグループ化。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並列実行可能(別ファイル・依存なし)
- **[Story]**: 対応するユーザーストーリー(US1〜US4)
- ファイルパスは実際のリポジトリパスを明記

## Path Conventions

単一プロジェクト構成。`data/startgg/`, `scripts/`, `docs/` を使用
(plan.md の Project Structure 参照)。

---

## Phase 1: Setup

**Purpose**: 新規ファイルの骨格を用意する

- [ ] T001 `data/startgg/label_rules.json` を、最小限の有効なルールセット
      (`{"label_version": 1, "matches": []}`)として新規作成する。具体的な
      判定パターンの内容は本feature のスコープ外(spec.md Assumptions 参照)
- [ ] T002 [P] `scripts/labeling.py` を新規作成し、`DEFAULT_LABEL_RULES_PATH`・
      `LabelRuleError`・`CompiledLabelRule`/`CompiledLabelRuleSet`(dataclass)・
      各関数(`load_label_ruleset`, `compile_label_ruleset`, `compute_labels`,
      `merge_labels`, `compute_event_labels`)のシグネチャのみのスタブ
      (`raise NotImplementedError`)を用意する(data-model.md/contracts/cli.md 参照)
- [ ] T003 [P] `scripts/test/test_labeling.py` を作成し、`scripts.labeling` を
      import するだけの空テストケースを用意する
- [ ] T004 [P] `scripts/fix/apply_label_rules.py` を新規作成し、
      `contracts/cli.md` に定義された引数(`--events-root`, `--rules-file`,
      `--indent-num`, `--yes`)を受け取る `parse_args()` のみを実装する
      (処理ロジックは未実装)
- [ ] T005 [P] `scripts/test/test_apply_label_rules.py` を作成し、
      `scripts.fix.apply_label_rules` を import するだけの空テストケースを
      用意する

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: US1・US2・US3・US4 すべてが依存する判定エンジン本体
(`scripts/labeling.py`)

**⚠️ CRITICAL**: このフェーズが完了するまで、いずれのユーザーストーリーの
実装も開始しない

- [ ] T006 `scripts/labeling.py` に `load_label_ruleset(path)` と
      `compile_label_ruleset(ruleset)` を実装する。ファイル欠落・
      JSONデコードエラー・`label_version`欠落・`matches`が配列でない・
      各ルールの`label`欠落・`tournament_name_match`/`event_name_match`
      両方欠落・不正な正規表現、のいずれかを検出した場合、検出した問題点を
      すべて列挙した1つの`LabelRuleError`を送出する(research.md #3)。
      正規表現は前後を`/`で囲んだ記法(`/pattern/`)・囲まない記法どちらも
      受け付ける(research.md #2 のスラッシュ正規化ルール)
- [ ] T007 `scripts/labeling.py` に `compute_labels(compiled, tournament_name, event_name)`
      と `merge_labels(existing_labels, computed_labels, managed_label_names)`
      を実装する。マッチングは`re.search`相当の部分一致。
      `tournament_name_match`のみ/`event_name_match`のみ/両方(AND)の
      いずれの指定でも判定できる。同じ`label`への複数ルールはOR条件、
      異なる`label`同士は独立に複数同時成立する。`merge_labels`は
      `managed_label_names`に含まれない既存キーを保持し、含まれるキーは
      `computed_labels`で完全に置き換える(T006 に依存、同一ファイル)
- [ ] T008 `scripts/labeling.py` に `compute_event_labels(existing_labels, tournament_name, event_name, event_data_version, *, rules_path=DEFAULT_LABEL_RULES_PATH)`
      を実装する(この時点では`min_event_data_version`のゲート判定は行わず、
      常に`(merge_labels(...), ruleset["label_version"])`を返す。ゲート判定は
      Phase 6 (US4) で追加する)。`functools.lru_cache`でルールセットの
      読み込み・検証・コンパイル結果を`rules_path`ごとにプロセス内キャッシュする
      (T007 に依存、同一ファイル)
- [ ] T009 [P] `scripts/test/test_labeling.py` に、T006〜T008 を検証する
      テストを追加する: ルール定義ファイルの欠落/JSON不正/必須フィールド
      欠落/不正な正規表現がそれぞれ`LabelRuleError`になること、
      スラッシュ記法の有無どちらも同じ結果になること、
      `tournament_name_match`のみ/`event_name_match`のみ/両方(AND)の
      判定、同じ`label`への複数ルールのOR条件、異なる`label`が同時に
      `true`になること、`merge_labels`が管理対象外キーを保持しつつ
      管理対象キーを完全に置き換えること、`compute_event_labels`が
      `(merged_labels, label_version)`を返すこと、同一`rules_path`への
      複数回呼び出しでルールファイルの再読み込みが発生しない
      (キャッシュされる)こと

**Checkpoint**: 判定エンジンが完成・テスト済み。ここから各ユーザーストーリーの
実装に進める。

---

## Phase 3: User Story 1 - 新規取得イベントにルールベースでラベルを自動付与する (Priority: P1) 🎯 MVP

**Goal**: start.gg から新規にイベントデータを取得する際、`attr.json` の
`labels`にルール定義ファイルに基づく判定結果が自動的に設定され、
`label_version`が記録される。既存の`labels`内の他プロパティは破壊されない。

**Independent Test**: `quickstart.md` 手順1(`test_download`/
`test_download_specific_event`の実行)により、他のユーザーストーリーと
独立に検証できる。

### Tests for User Story 1

- [ ] T010 [P] [US1] `scripts/test/test_download.py` に、
      `write_event_attributes()` が(a) 一致するルールの`tournament_name`
      を与えられたとき`labels`に該当ラベルを`true`で設定し`label_version`を
      記録すること、(b) `tournament_name_match`と`event_name_match`両方
      指定のルールで片方しか満たさない場合はラベルが付与されないこと、
      (c) どの条件にも一致しない場合はラベルキー自体が存在しないが
      `label_version`は記録されること、(d) 呼び出し時に渡した既存の
      `labels`プロパティ(ルール管理対象外のキー)を保持したまま追加する
      こと、を確認するテストを追加する(spec.md User Story 1 Acceptance
      Scenarios 1〜5 に対応)
- [ ] T011 [P] [US1] `scripts/test/test_download_specific_event.py` に、
      T010 と同等のテストを追加する(独自実装への回帰確認)

### Implementation for User Story 1

- [ ] T012 [US1] `scripts/fetch/download.py` の `write_event_attributes()`
      を変更し、`json_data`組み立て直前に
      `labels, label_version = compute_event_labels(labels, tournament_name, event_name, EVENT_DATA_VERSION)`
      を呼び出し、`json_data["labels"] = labels`とし、`label_version`が
      `None`でなければ`json_data["label_version"] = label_version`を設定する
      (data-model.md 処理フロー参照。呼び出し元2箇所のシグネチャ変更は不要)
- [ ] T013 [US1] `scripts/fetch/download_specific_event.py` の
      `write_event_attributes()`(独自実装)にも T012 と同一内容の変更を
      適用する
- [ ] T014 [P] [US1] `docs/data_model.md` の `attr.json` スキーマ例に、
      ルール管理対象ラベルの例(`registration_restricted: true`等)と
      新規トップレベルフィールド`label_version`を追記し、「注意点」相当の
      セクションに、ラベル判定ルールは`data/startgg/label_rules.json`で
      管理され、判定エンジンは`scripts/labeling.py`である旨を追記する
      (data-model.md の「`docs/data_model.md`への追記内容」参照)

**Checkpoint**: User Story 1 は独立に動作・検証可能。

---

## Phase 4: User Story 2 - 既存の全イベントデータに最新のルールを一括再適用する (Priority: P1) 🎯 MVP

**Goal**: start.gg への再アクセスなしに、既存の全イベントディレクトリの
`attr.json` の `labels`/`label_version` を、現在のルール定義ファイルに
基づいて再計算・更新する手動実行ツールを提供する。デフォルトはdry-run。

**Independent Test**: `quickstart.md` 手順3(サンプルディレクトリでの
dry-run/`--yes`実行)により、他のユーザーストーリーと独立に検証できる。

### Tests for User Story 2

- [ ] T015 [P] [US2] `scripts/test/test_apply_label_rules.py` に、
      ルールに一致するイベントの`labels`/`label_version`が(dry-runでは
      書き込まれず)`--yes`指定時のみ実際に更新されることを確認する
      テストを追加する
- [ ] T016 [P] [US2] 同ファイルに、`attr.json`が存在しない/JSONとして
      壊れているイベントディレクトリに遭遇しても処理全体が停止せず、
      残りのディレクトリを処理し続けること(`skipped_broken`が加算される
      こと)を確認するテストを追加する
- [ ] T017 [P] [US2] 同ファイルに、既存の`label_version`が現在のルール
      セットと一致するイベントは判定の再計算自体が行われず
      (`compute_labels`が呼ばれないことをモック等で確認)、
      `skipped_up_to_date`が加算されることを確認するテストを追加する
- [ ] T018 [P] [US2] 同ファイルに、`--yes`で1回実行した後にもう一度
      `--yes`で実行すると2回目は全件`skipped_up_to_date`になる(冪等)
      ことを確認するテストと、実行中に`scripts.utils.fetch_data_with_retries`
      等のAPI関連関数が一切呼び出されない(importもしていない)ことを
      確認する静的チェックのテストを追加する

### Implementation for User Story 2

- [ ] T019 [US2] `scripts/fix/apply_label_rules.py` に、起動時の
      ルール定義ファイル読み込み・検証(失敗時は1件も処理せずエラー終了)、
      `--events-root`以下の`attr.json`を`rglob`で列挙、壊れた/存在しない
      ファイルのスキップ、既存`label_version`一致時のスキップ
      (判定再計算なし)、それ以外は`compute_labels`/`merge_labels`で
      再計算し`labels`/`label_version`を更新するロジックを実装する
      (data-model.md 処理フロー参照。T004/T006〜T008 に依存)
- [ ] T020 [US2] 同ファイルに、dry-run時は書き込みを行わず「更新予定」を
      出力し、`--yes`指定時のみ`write_json()`で実際に書き込む処理と、
      終了時の要約行(`Done. updated=X skipped_low_version=0 skipped_up_to_date=Y skipped_broken=Z`、
      dry-run時は末尾に`(dry-run)`を付与)の出力を実装する
      (contracts/cli.md 参照。T019 に依存)

**Checkpoint**: User Story 2 は独立に動作・検証可能。この時点で US1+US2 に
より MVP(新規取得への自動付与+既存データへの一括反映)が完成する。

---

## Phase 5: User Story 3 - トーナメント名・イベント名を個別または組み合わせて判定するルールを定義できる (Priority: P2)

**Goal**: 1つのラベルに対する複数ルール(OR条件)、トーナメント名のみ/
イベント名のみ/両方(AND)の判定、異なるラベルの同時付与、が仕様通りに
動作することを確認する。

**Independent Test**: `scripts/test/test_labeling.py`のうち、本ストーリー
専用のテストのみを実行して独立に検証できる。

### Tests for User Story 3

- [ ] T021 [P] [US3] `scripts/test/test_labeling.py` に、spec.md User
      Story 3 Acceptance Scenarios 1〜5 に対応する結合的なテストケースを
      追加する: `tournament_name_match`のみのルール、`event_name_match`
      のみのルール、両方指定(AND)のルール、同じ`label`への複数ルール
      (OR、片方のみ一致でも成立)、異なる2つのラベル
      (`registration_restricted`と`casual`)の条件をそれぞれ独立に満たす
      イベントで`labels`に両方が同時に`true`で設定されること
      (T006〜T008 のFoundational実装が対象。新規のプロダクションコード
      変更は想定しないが、テストで不整合が見つかった場合は
      `scripts/labeling.py`を修正する)

**Checkpoint**: User Story 3 の要件(ルール構造の柔軟性)がテストで
裏付けられる。

---

## Phase 6: User Story 4 - ルールが新しいイベントデータ項目に依存する場合でも安全に運用できる (Priority: P3)

**Goal**: ルール定義ファイルが`min_event_data_version`を宣言している場合、
それを満たさないイベントの`labels`/`label_version`が新規取得経路・
一括適用ツールのいずれでも変更されず、スキップされる。

**Independent Test**: `min_event_data_version`を指定したルール定義ファイルと、
それを満たす/満たさないイベントデータを用意し、両経路でスキップされる
ことを確認することで独立に検証できる。

### Tests for User Story 4

- [ ] T022 [P] [US4] `scripts/test/test_labeling.py` に、
      `compute_event_labels`が`min_event_data_version`要件を満たさない場合
      `(existing_labels相当, None)`を返すこと、`event_data_version`が
      `None`の場合は`0`として扱われること(`min_event_data_version`が
      1以上なら常にスキップ対象になること)を確認するテストを追加する
      (spec.md Clarifications 参照)
- [ ] T023 [P] [US4] `scripts/test/test_apply_label_rules.py` に、
      `min_event_data_version`要件を満たさないイベントが`skipped_low_version`
      として加算され`labels`/`label_version`が変更されないこと、後日
      `event_data_version`が要件を満たす値に更新された上で再実行すると
      正常に判定・更新されることを確認するテストを追加する
- [ ] T024 [P] [US4] `scripts/test/test_download.py`/
      `scripts/test/test_download_specific_event.py`に、
      `min_event_data_version`要件を満たさない場合に`write_event_attributes()`
      が`label_version`フィールドを設定しない(かつ`labels`の
      ルール管理対象キーを変更しない)ことを確認するテストを追加する

### Implementation for User Story 4

- [ ] T025 [US4] `scripts/labeling.py`の`compute_event_labels`に
      `min_event_data_version`のゲート判定を追加する: `event_data_version`
      (`None`の場合は`0`)がルールセットの`min_event_data_version`を
      下回る場合、判定の再計算を行わず`(existing_labels or {}, None)`を
      返す(T008 を拡張。T022 に対応)
- [ ] T026 [US4] `scripts/fix/apply_label_rules.py`に、
      `attr.get("event_data_version") or 0`とルールセットの
      `min_event_data_version`を比較するゲート判定を追加する(要件を
      満たさない場合は`skipped_low_version`を加算しスキップ、
      `labels`/`label_version`は一切変更しない)。要約行の出力に
      `skipped_low_version`の実際の値を反映する(T019/T020 を拡張。
      T023 に対応)

**Checkpoint**: User Story 4 は独立に動作・検証可能。

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T027 [P] `python -m unittest scripts.test.test_labeling scripts.test.test_apply_label_rules scripts.test.test_download scripts.test.test_download_specific_event scripts.test.test_validate_data` を実行し、既存の全テストスイートも含めてすべてパスすることを確認する
- [ ] T028 `quickstart.md` の手順2〜4(サンプルルール定義ファイルでの
      dry-run/`--yes`実行、冪等性確認、実データ`data/startgg/events`への
      dry-run実行)を実際に行い、影響範囲(`updated`件数)を確認する
      (start.gg トークン・ネットワーク不要のため、この機能はローカルで
      完全に検証可能)
- [ ] T029 [P] `docs/data_model.md`の記載(T014・US4 で追記した
      `min_event_data_version`の挙動説明を含む)が、最終的な実装の挙動と
      一致していることを最終確認する

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし、即着手可能
- **Foundational (Phase 2)**: Setup 完了後。全ユーザーストーリーをブロックする
- **User Story 1 (Phase 3)**: Foundational 完了後。他ストーリーへの依存なし
- **User Story 2 (Phase 4)**: Foundational 完了後。US1 への依存なし
  (判定エンジンを共有するのみで、実装ファイルは独立)
- **User Story 3 (Phase 5)**: Foundational 完了後。US1/US2 への依存なし
  (`scripts/labeling.py`のテストのみを追加するため)
- **User Story 4 (Phase 6)**: Foundational 完了後。実装上は US1(T012/T013)・
  US2(T019/T020)が書いたコードを拡張するため、実施順としては US1・US2の
  後に行うことを推奨(spec.mdの優先度どおりP3、他ストーリー完了後で良い)
- **Polish (Phase 7)**: 実施したいユーザーストーリーすべての完了後

### User Story Dependencies

- **US1 (P1)**: Foundational 完了後に着手可能。他ストーリーに依存しない
- **US2 (P1)**: Foundational 完了後に着手可能。US1 に依存しない
- **US3 (P2)**: Foundational 完了後に着手可能。US1/US2 に依存しない
  (テスト追加のみ)
- **US4 (P3)**: Foundational 完了後に着手可能だが、US1(T012/T013)・
  US2(T019/T020)が実装したコードを拡張する実装タスク(T025/T026)を
  含むため、実質的には US1・US2 の完了後に着手するのが自然

### Parallel Opportunities

- Setup の T002〜T005 は並列実行可能(T001 のみ独立に先行してもよい)
- Foundational の T006〜T008 は同一ファイル(`scripts/labeling.py`)のため
  順次実行。T009 はそれらの完了後
- Foundational 完了後は、US1(T010〜T014)・US2(T015〜T020)・
  US3(T021)を並行して進めることができる(ファイルが重複しないため)
- US1 内の T010・T011・T014 は並列実行可能。T012・T013 は別ファイルへの
  同一パターン適用のため並列実行可能
- US2 内の T015〜T018 は並列実行可能(同一テストファイルへの追記だが
  内容は独立)。T019 完了後に T020
- US4 は US1・US2 完了後が自然だが、T022〜T024(テスト)は並列実行可能。
  T025(labeling.py拡張)完了後に T026(apply_label_rules.py拡張)

---

## Parallel Example: Foundational 完了後

```bash
# US1・US2・US3 を同時に着手できる:
Task: "write_event_attributes() への compute_event_labels() 組み込み (US1)"
Task: "apply_label_rules.py の走査・更新ロジック実装 (US2)"
Task: "AND/OR/複数ラベル同時付与のテスト追加 (US3)"
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 2)

1. Phase 1: Setup を完了
2. Phase 2: Foundational を完了(判定エンジン)
3. Phase 3: User Story 1 を完了
4. Phase 4: User Story 2 を完了
5. **STOP and VALIDATE**: `quickstart.md` 手順1・3で US1・US2 を検証
6. この時点で「新規取得データへの自動ラベル付与」+「既存データへの
   一括反映」が実用可能(MVP、spec.md でも US1・US2 はともに P1)

### Incremental Delivery

1. Setup + Foundational → 判定エンジン完成
2. US1 追加 → 単独検証 → 新規取得分から反映開始
3. US2 追加 → 単独検証 → 既存の全データへ一括反映(MVP完成)
4. US3 追加 → ルール構造の柔軟性をテストで裏付け
5. US4 追加 → 将来のスキーマ依存ルールに対する安全機構を追加
6. Polish → 全体テスト・実データでの最終確認

---

## Notes

- [P] タスク = 別ファイル・依存なし(同一ファイルへの複数タスクは順次実行)
- US1〜US4 は同じ判定エンジン(`scripts/labeling.py`)を共有するが、
  US1・US2・US3 は互いに独立して並行実装できる。US4 のみ US1/US2 が
  実装したコードを拡張するため、実質的な着手順に注意する
- テストは実装前に書き、失敗することを確認してから実装に進む
- 各チェックポイントで、そのユーザーストーリーが単独で検証可能であることを確認する
