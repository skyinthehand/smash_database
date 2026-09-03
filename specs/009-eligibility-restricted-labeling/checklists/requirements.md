# Specification Quality Checklist: 汎用イベントラベリング機構(大会名・イベント名ルールベース判定)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-01
**Revised**: 2026-09-03
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- 初版(2026-08-01)は「参加資格制限大会かどうか」という単一の固定ラベルのみを
  対象にしていたが、実装着手前の2026-08-30に「もっと汎用的に作るべき」との
  ユーザーフィードバックを受け、任意のラベルを宣言的なJSONルールファイルで
  定義できる汎用機構へと全面的に再検討した(初版は未実装のまま、tasks.md含め
  今回の内容で置き換え)。
- 今回の再検討で追加された主な仕様: (1) ルール定義ファイル自体の
  `label_version`と、それを記録する`attr.json.label_version`(新規
  トップレベルフィールド、`event_data_version`とは独立)の新設。(2) ラベル
  付与処理はstart.ggアクセスを伴わない高速なローカル処理として、イベント
  データ取得処理とは別個に管理する方針の明文化。(3) ルールが将来
  `event_data_version`の特定バージョン以上を要求できるようにする
  `min_event_data_version`(User Story 4、FR-011)。(4) トーナメント名・
  イベント名を個別または組み合わせ(AND条件)で判定できるルール構造
  (User Story 3、FR-001〜FR-003)。
- 正規表現の前後スラッシュ記法(`/パターン/`)の扱い(スラッシュの有無
  どちらも受け付けるか等)は意図的にAssumptionsで「`/speckit-plan`で確定する」
  として先送りし、[NEEDS CLARIFICATION]は使用しなかった(HOWレベルの詳細
  であり、スコープ・UXへの影響が無いため)。
- ユーザーフィードバック(2026-08-30): 「1つのイベントに複数の異なるラベルが
  同時に設定され得るか」が明示されていなかったため、FR-003に「異なるラベル
  同士の判定は互いに独立に行われ、複数該当すれば同時に全て設定される」旨を
  追記し、User Story 3にAcceptance Scenario 5(2つの異なるラベルが同時に
  trueになることを検証)を追加した。
- ユーザーフィードバック(2026-08-30): 一括適用ツールが`label_version`一致分の
  イベントについて「判定は再計算するが書き込みだけスキップする」設計だったが、
  約26,000件超の規模での再計算コスト自体を避けたいとの指摘を受け、FR-010・
  User Story 2 Acceptance Scenario 4を「`label_version`が一致していれば判定の
  再計算自体をスキップする」に変更した。
- `/speckit-clarify`(2026-09-03)にて4件の質問を実施し、`## Clarifications`
  節に記録の上で以下をspec本文へ反映した: (1) FR-011で`event_data_version`
  フィールド自体が存在しないイベントは`0`として扱いスキップ対象とする。
  (2) ルール定義ファイル自体が存在しない・JSONとして壊れている場合も
  FR-012の不正な正規表現と同様に起動時検出・処理中止とする(FR-012・
  Edge Casesに追記)。(3) `tournament_name_match`/`event_name_match`の
  「一致」は`re.search`相当の部分一致であることをFR-002に明記した。
  (4) FR-007の一括適用ツールは他の修復ツール(`fix_path_collision.py`等)
  に倣いデフォルトdry-run・明示オプション時のみ実書き込みとする
  (FR-007・User Story 2 Acceptance Scenario 5に追記)。
