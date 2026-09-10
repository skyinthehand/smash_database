# Tasks: 未開催トーナメントの管理

**Input**: Design documents from `/specs/010-upcoming-tournaments/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: 憲法Principle III(マージ前の検証ゲート)により、新しいデータ形状・
スクリプトには対応するテストがMUSTなので、本タスクリストにはテストタスクを
含める。

**Organization**: タスクはユーザーストーリー(spec.mdのUS1/US2/US3)ごとに
まとめ、各ストーリーが独立して実装・検証できるようにする。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並行実行可能(別ファイル・依存無し)
- **[Story]**: 対応するユーザーストーリー(US1/US2/US3)
- 各タスクは具体的なファイルパスを含む

---

## Phase 1: Setup

**Purpose**: 新規ファイルの土台を用意する

- [ ] T001 `scripts/fetch/download_upcoming_tournaments.py`を新規作成し、
      `argparse`によるCLI引数(`--token`必須、`--country_code`既定`JP`、
      `--game_id`既定`1386`、`--url`既定`https://api.start.gg/gql/alpha`、
      `--tournaments_file`既定`data/startgg/upcoming_tournaments.jsonl`、
      `--max_retries`/`--retry_delay`)と`main()`の骨格のみを用意する
      (`contracts/cli.md` #2のCLI契約通り)。

---

## Phase 2: Foundational(全ユーザーストーリーの前提)

**Purpose**: どのユーザーストーリーの実装にも必要な、API仕様の確認と
クエリ関数の追加

**⚠️ CRITICAL**: このフェーズが終わるまでユーザーストーリーの実装には
着手できない(特にT002はクエリ設計そのものを左右する)

- [ ] T002 `quickstart.md` #0の手順で、`afterDate`フィルタと大会一覧への
      `events`ネストが実際にstart.gg APIで有効かを、ユーザーのトークンで
      1回手動確認する(コード変更は無し。結果を`research.md`に反映する
      ドキュメント更新のみ。T002の結果次第でT003・T009の実装が
      `research.md`のFallback方式のいずれになるかが決まる)。
- [ ] T003 `scripts/queries.py`に`get_upcoming_tournaments_by_game_query
      (country_code, after_date)`を新規追加する(`contracts/cli.md` #1
      通り。既存の`get_tournaments_by_game_query`は変更しない)。T002で
      `afterDate`/`events`ネストが有効と確認できた場合はそのまま実装し、
      無効だった場合は`research.md` #1/#2のFallback方式(早期終了判定/
      個別呼び出し)に沿った関数シグネチャに調整する。

**Checkpoint**: クエリ関数が用意でき、以後のユーザーストーリー実装が
着手可能になる

---

## Phase 3: User Story 1 - 未開催大会一覧を把握する (Priority: P1) 🎯 MVP

**Goal**: JPの未開催大会一覧を`data/startgg/upcoming_tournaments.jsonl`に
記録できる(参加人数・ラベルを除く基本情報のみ)

**Independent Test**: `download_upcoming_tournaments.py --country_code JP`
を実行し、未開催大会のみが索引ファイルに記録され、終了済みの大会が
含まれないことを確認する

### Tests for User Story 1

- [ ] T004 [P] [US1] `scripts/test/test_download_upcoming_tournaments.py`
      を新規作成し、`fetch_data_with_retries`をモックしてページングで
      複数ページ分の大会を正しく集約することを確認するテストを書く。
- [ ] T005 [P] [US1] 同ファイルに、実行のたびに既存の
      `upcoming_tournaments.jsonl`の内容を破棄して完全に上書きすること
      (差分マージしないこと、FR-006)を確認するテストを書く。
- [ ] T006 [P] [US1] 同ファイルに、`download_upcoming_tournaments.py`の
      実行前後で`data/startgg/tournaments.jsonl`・
      `data/startgg/events/`配下・`data/startgg/done.csv`・
      `data/startgg/done_events.csv`のいずれにも変更が生じないこと
      (FR-007)、および`data/startgg/events/`配下に新規ディレクトリが
      作成されないこと(FR-005)を確認するテストを書く。
- [ ] T007 [P] [US1] 同ファイルに、開始日時は過去だが終了日時が未来
      (＝開催中)の大会が一覧に含まれないことを確認するテストを書く
      (spec.md Edge Cases「開催中の大会は対象外」)。

### Implementation for User Story 1

- [ ] T008 [US1] `scripts/fetch/download_upcoming_tournaments.py`に、
      T003のクエリ関数を使ってJPの未開催大会をページングしながら全件
      取得する処理を実装する(`fetch_data_with_retries`/`fetch_all_nodes`
      経由、憲法Principle V)。
- [ ] T009 [US1] 同ファイルに、取得した各大会を`data-model.md`の
      スキーマ(`tournament_id`/`name`/`country_code`/`start_at`/
      `end_at`/`url`/`place`/`fetched_at`/`version`。`events`は空配列で
      いったん組み立てる)に変換する処理を実装する。
- [ ] T010 [US1] 同ファイルに、`write_jsonl(records,
      tournaments_file, with_version=True)`で`upcoming_tournaments.jsonl`
      を全件書き出す処理を実装する(既存内容とのマージはしない。既存の
      `tournaments.jsonl`等には一切書き込まない、T006と対応)。
- [ ] T011 [US1] 同ファイルに、取得件数(大会数)を標準出力に1行報告する
      処理を追加する(`contracts/cli.md` #2、ワークフロー側の確認用)。

**Checkpoint**: この時点で、大会一覧(参加人数・ラベル無し)が単独で
動作・検証可能

---

## Phase 4: User Story 2 - 参加人数を確認する (Priority: P2)

**Goal**: 各種目の現時点の参加登録人数を記録できる

**Independent Test**: 取得結果の各種目レコードに`num_entrants`が含まれ、
start.gg上の実際の登録人数と一致することを確認する

### Tests for User Story 2

- [ ] T012 [P] [US2] `test_download_upcoming_tournaments.py`に、大会
      ノードにネストされた`events`から`num_entrants`を正しく抽出する
      ケースのテストを追加する。
- [ ] T013 [P] [US2] 同ファイルに、ネストされた`events`が使えない
      (取得できない)場合に、個別呼び出しフォールバック(FR-003a)が
      発動し、それでも`num_entrants`が埋まることを確認するテストを
      追加する。

### Implementation for User Story 2

- [ ] T014 [US2] `download_upcoming_tournaments.py`に、T002/T003の結果に
      応じて、大会ノードにネストされた`events`(`id`/`name`/
      `numEntrants`/`state`/`type`/`isOnline`)を各大会レコードの
      `events`配列に変換する処理を実装する(T009で空配列にしていた
      箇所を実装)。
- [ ] T015 [US2] 同ファイルに、ネスト方式が使えなかった場合の
      フォールバックとして、`fetch_event_ids_from_tournament`相当→
      `get_event_details_by_id_query`相当の個別呼び出しで`num_entrants`
      を補完する処理を実装する(FR-003a、`research.md` #2)。

**Checkpoint**: 大会一覧+参加人数が単独で動作・検証可能(US1に統合)

---

## Phase 5: User Story 3 - 未開催の種目にもラベルを付与する (Priority: P3)

**Goal**: 各種目に既存のラベリング機構によるラベルを付与できる

**Independent Test**: `label_rules.json`のルールに合致する種目名を持つ
未開催種目に、該当ラベルが記録されることを確認する

### Tests for User Story 3

- [ ] T016 [P] [US3] `test_download_upcoming_tournaments.py`に、
      `compute_event_labels`が呼ばれ、大会名・種目名のルールに応じた
      `labels`/`label_version`が各種目レコードに含まれることを確認する
      テストを追加する。
- [ ] T017 [P] [US3] 同ファイルに、ルールセットの
      `min_event_data_version`要件を満たさない場合に`label_version`が
      `null`になることを確認するテストを追加する。

### Implementation for User Story 3

- [ ] T018 [US3] `download_upcoming_tournaments.py`で、
      `scripts/labeling.py`の`compute_event_labels(None, tournament_name,
      event_name, EVENT_DATA_VERSION, rules_path=...)`を各種目について
      呼び出し、結果の`labels`/`label_version`を種目レコードに追加する
      (`research.md` #3)。

**Checkpoint**: US1〜US3が全て単独・統合の両方で動作・検証可能

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: ドキュメント更新・日次自動化への統合・最終確認

- [ ] T019 [P] `docs/data_model.md`に`data/startgg/upcoming_tournaments.jsonl`
      の新セクションを追加する(`data-model.md`の内容を転記、憲法
      Principle I)。
- [ ] T020 `.github/workflows/update_tournament.yml`に、
      `contracts/cli.md` #3の「Refresh upcoming tournaments (JP)」
      ステップ(`continue-on-error: true`)を追加する(FR-008/FR-009)。
- [ ] T021 `quickstart.md`の手順1〜6を実際に(ユーザーのトークンで)
      実行し、想定通り動作することを確認する。
- [ ] T022 `python3 -m unittest discover -s scripts/test -p "test_*.py"`
      を実行し、既存テスト+本機能の新規テストが全てpassすることを
      確認する(憲法Principle III)。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存無し、即着手可能
- **Foundational (Phase 2)**: Setup完了後。T002(API疎通確認)は全ての
  後続実装の前提であり、他の何よりも先に終わらせる必要がある
- **User Story 1 (Phase 3)**: Foundational完了後。他のストーリーに依存
  しない
- **User Story 2 (Phase 4)**: Foundational完了後。US1のT009(大会レコード
  組み立て)に統合する形のため、US1完了後に着手するのが自然(ただし
  テスト(T012/T013)自体はUS1と並行して書ける)
- **User Story 3 (Phase 5)**: Foundational完了後。US1のレコード組み立てに
  統合するため、US1完了後に着手するのが自然(US2とは独立)
- **Polish (Phase 6)**: 望ましい範囲のユーザーストーリー完了後

### Within Each User Story

- テストを先に書き、実装前に失敗することを確認する
- US1: クエリ呼び出し→レコード組み立て→書き出し、の順
- US2/US3: いずれもUS1のレコード組み立て処理に追加する形なので、US1の
  T009完了が前提

### Parallel Opportunities

- T004/T005/T006/T007(US1のテスト)は並行して書ける
- T012/T013(US2のテスト)、T016/T017(US3のテスト)もそれぞれ並行して
  書ける
- US2のテスト(T012/T013)とUS3のテスト(T016/T017)は、US1の実装と並行して
  先に書き進めることができる(実装(T014/T015/T018)はUS1のT009完了後)
- T019(ドキュメント)はT001〜T018と並行して進められる

---

## Parallel Example: User Story 1

```bash
# US1のテストを並行して書く:
Task: "test_download_upcoming_tournaments.py にページング集約のテストを追加"
Task: "test_download_upcoming_tournaments.py に完全上書きのテストを追加"
Task: "test_download_upcoming_tournaments.py に既存データ非干渉のテストを追加"
Task: "test_download_upcoming_tournaments.py に開催中大会の除外テストを追加"
```

---

## Implementation Strategy

### MVP First (User Story 1 のみ)

1. Phase 1: Setup を完了
2. Phase 2: Foundational を完了(T002のAPI疎通確認が特に重要)
3. Phase 3: User Story 1 を完了
4. **一旦停止して検証**: `quickstart.md` #1・#4・#5でUS1単独の動作を確認
5. 必要ならここでリリース(参加人数・ラベル無しの一覧のみでも価値がある)

### Incremental Delivery

1. Setup + Foundational → 基盤完成
2. User Story 1 追加 → 単独で検証 → リリース可能(MVP)
3. User Story 2 追加 → 単独で検証 → リリース
4. User Story 3 追加 → 単独で検証 → リリース
5. Polish(ドキュメント・ワークフロー統合)で日次自動化に組み込み完了

---

## Notes

- [P] タスク = 別ファイル・依存無し
- [Story] ラベルはどのユーザーストーリーに対応するかを示す
- 各ユーザーストーリーは独立して完了・検証可能であるべき
- 実装前にテストが失敗することを確認する
- タスクごと、または論理的なまとまりごとにcommitする
- 各チェックポイントで一旦立ち止まり、ストーリー単独の動作を検証する
