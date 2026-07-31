# Feature Specification: データ品質チェックの test_validate_data への統合

**Feature Branch**: `001-consolidate-validation-checks`

**Created**: 2026-08-01

**Status**: Draft

**Input**: User description: "これらのチェック処理をすべて test_validate_data に移動したい"

## User Scenarios & Testing *(mandatory)*

現状、データ品質の異常検知は複数の場所に分散している。

- `scripts/fix/validate_data.py`(`scripts.test.test_validate_data` から呼ばれ、日次自動更新ワークフローの
  「Run tests」ステップで自動実行される)は、必須ファイル・必須フィールド・
  `standings`/`seeds` が `num_entrants > 0` なのに空、といった一部のケースのみを判定している。
- `scripts/fix/find_empty_events.py` は「`matches.json` は非空なのに `standings.json` が空」という
  ケースを検出できるが、手動実行が前提の読み取り専用レポートツールであり、
  ワークフローの自動テストには組み込まれていない。

この結果、日次自動更新ワークフロー(`update_tournament.yml` / `update_user.yml`)が
新しく取り込んだデータの中に「`matches` はあるのに `standings` が空」という異常が
含まれていても、メンテナが `find_empty_events.py` を手動実行するまで誰も気づけない。

### User Story 1 - 自動テストが「matches非空・standings空」を検知する (Priority: P1)

メンテナとして、日次自動更新ワークフローの「Run tests」ステップ
(`python -m unittest scripts.test.test_validate_data`)が、
`matches.json` の `data` が非空なのに `standings.json` の `data` が空、という
これまで検出できていなかった異常パターンを自動的に検知してほしい。
これにより、`find_empty_events.py` を手動実行しなくても、異常なデータが
`main` に取り込まれる前に気づける。

**Why this priority**: 既に実データで10件のこのパターンが確認されており、
かつ自動更新ワークフローが唯一実行しているテストがこれを見逃す現状の
ギャップを塞ぐ、最も影響が大きい変更のため。

**Independent Test**: `matches.json` に非空の `data`、`standings.json` に
空の `data` を持つ一時イベントディレクトリを作成し、
`validate_event_dir()` を呼び出して結果(エラー/警告リスト)を検証することで、
単独でテスト可能。

**Acceptance Scenarios**:

1. **Given** イベントディレクトリの `matches.json` の `data` が非空で `standings.json` の `data` が空、
   かつ `num_entrants` が0より大きい、**When** `test_validate_data` を実行する、
   **Then** バリデーションはこのイベントを異常として報告する。
2. **Given** イベントディレクトリの `matches.json` と `standings.json` の `data` がともに空で、
   `num_entrants` が0(または未エントラント)、**When** `test_validate_data` を実行する、
   **Then** 既存動作どおり異常として報告されない(waiting list等の正当な空イベントを誤検知しない)。

---

### User Story 2 - 既存の分散チェックとの整合性を保つ (Priority: P2)

メンテナとして、`validate_data.py` に統合された判定ロジックを、
`find_empty_events.py` のような既存の read-only レポートツールからも
再利用したい。判定基準(何が異常で何が正当な空データか)が
ツールごとに食い違うと、どちらを信じればよいか分からなくなるため。

**Why this priority**: ロジックの二重実装は将来的な判定基準のズレ
(この会話で既に発生した「BOTH_EMPTY 1408件中ほとんどが正当な空データ」
のような誤検知)を再発させるリスクがある。

**Independent Test**: `find_empty_events.py` を実行し、その結果が
`validate_data.py` 側の新しい判定関数の出力と矛盾しないことを確認する。

**Acceptance Scenarios**:

1. **Given** `validate_data.py` に統合された判定ロジック、**When** `find_empty_events.py` を実行する、
   **Then** 同じ判定関数(または同じ基準)を使って結果を出力し、`validate_data.py` 単体の結果と一致する。

---

### User Story 3 - 再取得時の退行検知を検証可能な形にする (Priority: P2)

メンテナとして、`redownload_event.py` 実行時にコンソールへ出力されるだけの
「`matches`/`standings` が非空から空に退行した」という警告を、目視確認だけに
頼らず、テストスイートや自動化された仕組みから再現・検証できる形にしたい。

**Why this priority**: 現状は `redownload_event.py` を手動実行した担当者が
コンソール出力を見逃すと、データ損失に気づけないまま `main` にマージされうる
(実際に event_id=1290086 でこの見逃しに近い事象が発生した)。

**Independent Test**: 再取得前に `matches.json`/`standings.json` の `data` が
非空なイベントディレクトリを用意し、再取得後にそれが空になった状態を再現した上で、
退行検知ロジックを単体で呼び出し、異常として報告されることを確認する。

**Acceptance Scenarios**:

1. **Given** 再取得前に `matches.json` の `data` が非空、**When** 再取得後に `data` が空になる、
   **Then** 退行検知ロジックはこれを異常として報告する。
2. **Given** 再取得前後で `matches.json` の `data` が空のまま(元々空)、**When** 再取得を行う、
   **Then** 退行検知ロジックは異常を報告しない(空→空は退行ではない)。

---

### Edge Cases

- `num_entrants` フィールド自体が欠落している、または整数でない場合はどう扱うか
  → 既存の `standings`/`seeds` 空チェックと同じ扱い(「0件確定」以外は「エントラントがいるはず」とみなす)を踏襲する。
- `matches.json` や `standings.json` がJSONとして壊れている場合
  → 既存の「JSON parse エラー」チェックが先に発火し、今回の新チェックはスキップされる(既存動作を踈襲)。
- 大会名・イベント名の変更によって event_id が孤立し、再取得すると `matches`/`standings` が
  非空→空に「退行」するケース(過去に `redownload_event.py` で実際に発生)は、
  本機能のスコープに含める(User Story 3 参照)。ただし単一時点のスナップショット比較である
  他のチェックとは異なり、再取得前後の比較が必要になる点に留意する。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: システムは、`matches.json` の `data` が非空でありながら `standings.json` の `data` が
  空であるイベントディレクトリを `scripts/fix/validate_data.py` の `validate_event_dir()` 内で
  検出しなければならない。
- **FR-002**: FR-001 の検出結果は `scripts.test.test_validate_data` のテストスイートから
  検証可能でなければならない(= 日次自動更新ワークフローの「Run tests」ステップで自動的に
  実行される)。
- **FR-003**: FR-001 の検出は、`num_entrants` が 0 (エントラント無しと確定しているイベント、
  例: waiting list) の場合には異常として扱ってはならない。既存の `standings`/`seeds` 空チェックと
  同じ判定基準を用いる(決定事項: 一貫性を優先し、この除外ルールを適用する。詳細は
  Assumptions 参照)。
- **FR-004**: FR-001 の検出結果は WARNING として扱う(既存の「`matches` 空・`standings` 非空」の
  ケースと同様、`--strict` 指定時のみテスト失敗として扱う。常時 ERROR とはしない)。
- **FR-005**: `scripts/fix/find_empty_events.py` は、`validate_data.py` に統合された判定ロジックを
  再利用し、同一の異常を独自基準で二重に判定してはならない。
- **FR-006**: FR-003 の `num_entrants == 0` 除外ルールにより、現時点で実データ中に確認されている
  10件の既存の異常イベント(いずれも `num_entrants = 0`)は、本チェックの対象外となる。
  これは意図された結果であり、既存データの修正や除外リストによる追加のグランドファザリング処理は
  不要とする。
- **FR-007**: システムは、再取得(redownload)によって `matches.json` または `standings.json` の
  `data` が非空から空へ変化した(退行した)場合を検出しなければならない。この検出は
  `redownload_event.py` 内の一時的なコンソール警告のみに留めず、テストスイートや自動化された
  仕組みから再現・検証できる形で提供しなければならない。
- **FR-008**: FR-007 の退行検知は、再取得前のデータ状態と再取得後のデータ状態を比較すること
  によって判定しなければならない。空のまま(非退行)のケースを誤って異常と報告してはならない。

### Key Entities *(include if feature involves data)*

- **Event Directory**: `attr.json` / `matches.json` / `seeds.json` / `standings.json` を含む
  1イベント分のデータ一式。`num_entrants` (エントラント数) を `attr.json` から参照する。
- **Validation Finding**: `validate_event_dir()` が返すエラーまたは警告メッセージ。
  対象イベントディレクトリと理由を含む。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 日次自動更新ワークフローが「`matches` 非空・`standings` 空」のイベントを
  新規に取り込んだ場合(かつ `num_entrants` が0でない場合)、`find_empty_events.py` を
  手動実行しなくても、次回のテスト実行(`python -m unittest scripts.test.test_validate_data`)
  だけでそのイベントが検出される。
- **SC-002**: 再取得(redownload)によって `matches`/`standings` が非空から空へ退行した場合、
  `redownload_event.py` のコンソール出力を見なくても、テストスイートや自動化された仕組みから
  その退行を再現・検証できる。
- **SC-003**: `num_entrants = 0` の正当な空イベント(waiting list等、現状多数存在)について、
  誤検知(false positive)が発生しない。既知の10件の既存違反イベントもすべて
  `num_entrants = 0` であるため、この除外ルールにより新チェックの対象外となることを許容する。

## Assumptions

- 対象は「`matches.json` は非空なのに `standings.json` が空」という、
  現在 `validate_data.py` では未検出の1方向のみとする(逆方向の
  「`matches` 空・`standings` 非空」は既に警告として実装済みのため変更しない)。
- `num_entrants == 0` の除外ルールは、既存の `standings`/`seeds` 空チェックとの一貫性を優先し、
  新チェックにも同様に適用する。この結果、現状確認されている10件の既存違反
  (event_id: 1077435, 520798, 1178502, 1182225, 1186909, 1210678, 1226835, 1239495,
  1248914, 1261379。いずれも `num_entrants = 0`)は本チェックでは検知されなくなるが、
  これは既存ロジックとの整合性を優先した結果として許容する。
- 再取得(redownload)時の「前後比較による退行検知」(`redownload_event.py` に実装済みの
  強めのワーニング)は、本機能のスコープに含める(FR-007, FR-008, User Story 3 参照)。
  単一時点のスナップショットを前提とする他のチェックとは異なり、"再取得前" の状態への
  参照が必要になる点は、計画(`/speckit-plan`)フェーズで設計する。
- 大会名・イベント名の変更に伴う event_id の孤立は、本会話で既に「今は対応不要」と
  明言されているため、本機能のスコープに含めない。
- API のクエリ複雑度エラーがフォールバックを使い切っても解消しないケースは、
  データバリデーションではなくスクリプト実行時エラーであるため、
  `test_validate_data` (静的なデータ検証) のスコープには含めない。
