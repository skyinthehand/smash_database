# Specification Quality Checklist: 同日同名トーナメントの保存先パス衝突の解消

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-29
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

- 具体的な命名調整方式(識別子の付与形式)や、参加者数の取得タイミング
  (延期を防ぐための取得順序変更)といったHOWに関わる詳細は、意図的に
  Assumptions節で「実装時に/speckit-planで確定する」として先送りし、
  [NEEDS CLARIFICATION]は使用しなかった。
- 既存の`004-fix-duplicate-events`(大会延期による同一event_idの重複)とは
  根本原因が異なる別問題(本フィーチャーは異なるtournament_id同士の名前
  衝突)であることを確認済み。
- 初版では「既存の混在データの修復は人手による個別対応(ツール無し)」
  としていたが、ユーザーからのフィードバックにより「修復は人手の判断・
  実行指示のもとで行うが、専用のツールは用意する」に修正
  (User Story 4、FR-009〜FR-011、SC-005を追加)。
- `/speckit-clarify`(2026-08-29): 衝突検出・命名調整ロジックの適用範囲を
  「通常のクロールのみ」に確定し、`redownload_event.py`を明示的にスコープ
  外とした(FR-001・Assumptions更新)。
- `/speckit-plan`後のユーザーフィードバック(2026-08-29): 上記の判断を
  訂正し、`redownload_event.py`も対象に含めることにした。ただし判定基準は
  FR-002/FR-004とは異なる単純な片方向ルール(User Story 5、FR-012)。
- `/speckit-analyze`(2026-08-29): 3件の指摘を反映して修正した。
  (R1・CRITICAL) Edge Casesの「3件以上衝突時は参加者数で毎回順位付け」
  という記述がFR-005(一度確定した保存先は不変)と矛盾していたため、
  「最初の2件のみ参加者数比較を行い、以降はロック済み側を常に維持する」
  に統一(spec.md Edge Cases/FR-002/FR-005、research.md Decision 3、
  tasks.md T009/T010/T014を修正)。(I2・HIGH) plan.mdのConstitution
  Check表が`redownload_event.py`拡張なしという旧Decision 6の記述の
  ままだったため、Decision 7を参照するよう訂正。(C1・HIGH) 憲法
  Principle II(冪等性)がplan.mdで要求する「リネーム中断時の安全な
  再開・収束」を検証するテストがtasks.mdに欠けていたため、T028として
  追加。
- ユーザーフィードバック(2026-08-29、`/speckit-analyze`後): R1の修正が
  「2件目以降の衝突は常にロックし新規側のみ調整する」という設計になって
  いたため、同一の取得処理(1回のクロール実行/1回の修復ツール実行)内で
  3件以上が検出された場合に、最初の2件しか比較されず本来最多であるべき
  3件目以降が正しく維持されない問題を再指摘され、修正した。FR-005の
  恒久ロックは「取得処理をまたいだ」確定にのみ適用し、同一取得処理内は
  `settled_tournament_ids`スナップショットにより常に再比較・入れ替えを
  許容する設計に変更(spec.md Edge Cases/FR-005/US2 Acceptance
  Scenario 3・4、research.md Decision 3・6、data-model.md、
  tasks.md T009-T011/T014/T018-T020、quickstart.md §2・§4を修正)。
  修復ツール(`fix_path_collision.py`)も2件限定から2件以上を一括指定
  できるよう拡張した(FR-010)。
- 実データ運用(2026-08-30)でユーザーから、`fix_path_collision.py`が
  ローカルの`attr.json`の`event_id`を信頼して勝敗を判定する設計は不十分
  (`matches.json`の逐次取得が未完了のまま中断した場合、`attr.json`だけ
  古いイベントの情報が残り得るため)との指摘を受け、参加者数の比較を
  start.ggへの直接アクセス(再取得)に基づくものへ変更した。敗者側は
  取得し直した参加者数が必ず0であることを要求し、0でなければ自動実行を
  中止する安全確認を追加。勝者は`redownload_event.py`と同様の手順で改めて
  完全に再取得する(`research.md` Decision 6)。
- ユーザーフィードバック(2026-08-30): `find_path_collisions.py`で衝突を
  洗い出してから`--event-id`を手動で列挙するのが面倒との指摘を受け、
  `fix_path_collision.py`に`--all`オプションを追加した。
  `find_path_collisions.py`と同じグループ化ロジックで`tournaments.jsonl`
  内の全衝突を自動的に洗い出し、1グループずつ処理する。あるグループが
  安全確認(敗者の参加者数≠0)に失敗しても他のグループの処理は継続し、
  最後にまとめて`tournaments.jsonl`を更新する。
- ユーザーフィードバック(2026-08-30): 目視確認の上`data/startgg/excluded_events.json`
  を更新したので、それを根拠に削除したいとの依頼を受け、
  `fix_path_collision.py`にexcluded_events.json連携を追加した。グループ内の
  ちょうど1件だけが除外リストに登録されている場合、その1件を無条件に敗者、
  残りを無条件に勝者とし(参加者数比較は行わない)、敗者側の参加者数が0で
  あることも要求しない(除外理由が「全員ゲスト」等、参加者数が0でない
  ケースもあり得るため。人間の目視確認をローカルの参加者数比較より優先する)。
