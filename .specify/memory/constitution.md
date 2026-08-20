<!--
Sync Impact Report
-------------------
Version change: 1.0.0 → 2.0.0
Rationale: MAJOR — Principle IV redefined in a backward-incompatible way.
The `chore-update` branch + PR-based rebase auto-merge requirement is
removed and replaced with a direct-to-main commit requirement. This is not
an additive clarification; it reverses a previously MUST'd mechanism, so
per this constitution's own versioning policy (Governance section) it is a
MAJOR bump.

Modified principles:
- IV. ブランチとオートメーションの規律 (Branch & Automation Discipline):
  chore-update ブランチ + PR 経由の rebase auto-merge (MUST) を廃止し、
  `main` への直接 commit/push (MUST) + 共有 concurrency group による直列化
  + push 競合時の `git pull --rebase origin main` リトライ (MUST) に置換。
  `docs/chore-tornament/README.md` / `checked_dates.json` の
  script-only-update ルールは変更なしで維持。
  Rationale の追記: 実際に main への直接コミットが chore-update ベースの
  自動化から見えず、古い状態のまま処理が継続した実インシデント
  (`schema_backfill_cursor.txt` の手動削除が無視された事例)を根拠として
  記録。

Added sections: none

Removed sections: none (IV の本文のみ再定義。見出し名は維持)

Templates requiring updates:
- .specify/templates/plan-template.md: ✅ no change needed (no
  chore-update-specific references found)
- .specify/templates/spec-template.md: ✅ no change needed (no
  chore-update-specific references found)
- .specify/templates/tasks-template.md: ✅ no change needed (no
  chore-update-specific references found)
- .claude/skills/speckit-*/SKILL.md: ✅ no chore-update-specific references
  found requiring updates
- .github/workflows/schema_backfill.yml,
  .github/workflows/update_tournament.yml,
  .github/workflows/update_user.yml,
  .github/workflows/prune_empty_events.yml,
  .github/workflows/reset_chore_update_after_merge.yml: ⚠ pending — must be
  updated (or, for reset_chore_update_after_merge.yml, removed) to match
  the new Principle IV outside of this command's scope; tracked as a
  deferred intent below.
- docs/githubAction.md: ⚠ pending — describes the old chore-update flow in
  detail; tracked as a deferred intent below.

Follow-up TODOs: none within constitution scope. See "Next Actions" for the
non-governance follow-up (workflow YAML / docs updates) the requester will
perform separately.
-->

# smash_database Constitution
<!-- start.gg 経由でスマブラ大会データを収集・保存するデータパイプラインの憲法 -->

## Core Principles

### I. データスキーマの整合性とバージョニング (Data Schema Integrity & Versioning)
`data/startgg/` 配下に保存する全てのデータファイル（`attr.json` / `standings.json` /
`seeds.json` / `matches.json` / `tournaments.jsonl` / `users.jsonl`）は
`docs/data_model.md` に定義されたスキーマに MUST 準拠する。各ファイルは
`version` フィールドを MUST 保持する。スキーマを変更する場合は
`docs/data_model.md` を同一PRで MUST 更新し、既存データへの影響がある場合は
`scripts/fix/backfill_events.py` 等を用いて MUST 移行する。
Rationale: スキーマとドキュメントが乖離すると、`scripts/queries.py` など
データを読む側のコードが静かに壊れる。

### II. 冪等でインクリメンタルな収集 (Idempotent Incremental Collection)
`scripts/fetch/*` の取得処理は、同じ入力に対して複数回実行しても安全であるよう
MUST 冪等に実装する。既に取得済みの大会・イベントは `done.csv` /
`done_events.csv` で管理し、再取得前に MUST これらを参照して重複取得を回避する。
Rationale: start.gg API への不要な負荷を避け、レート制限・APIコストに配慮する
ため（`docs/flow.md` の「終了済み & 未取得」判定はこの原則の実装）。

### III. マージ前の検証ゲート (Validation Gate, NON-NEGOTIABLE)
`data/` やそれを生成する `scripts/` に変更を加える場合、`scripts/test` 配下の
関連テスト（最低限 `scripts.test.test_validate_data`）が pass するまで MUST
merge しない。新しいデータ形状・フィールドを追加する場合は、対応するテストを
`scripts/test` に MUST 追加する。`data_monthly_check.yml` のように検証失敗が
ワークフロー全体を失敗させる設計は MUST 維持する。
Rationale: データベース全体の一貫性は自動収集パイプラインの信頼性に直結し、
一度壊れたデータは後から検出・修復するコストが高い。

### IV. ブランチとオートメーションの規律 (Branch & Automation Discipline)
`data/` を更新する GitHub Actions 自動化は MUST 中間ブランチを経由せず、
`main` へ直接 commit / push する。複数の自動化ワークフローが同時に `main`
へ push しうる場合、共有の `concurrency` group で MUST 直列化し、push が
競合した場合は `git pull --rebase origin main` による MUST リトライを行う。
`main` に変更を積む前に、Principle III（マージ前の検証ゲート）のテストを
MUST pass させる。
`docs/chore-tornament/README.md` と `checked_dates.json` は
`scripts/fix/update_chore_tournament_log.py` 経由でのみ MUST 更新し、手動編集
は MUST NOT 行わない。
Rationale: 以前は自動更新を `chore-update` ブランチに集約し、PR 経由の
rebase auto-merge で `main` に反映していたが、`main` への直接コミット(手動の
修正など)が発生すると `chore-update` 側の自動化はそれに気づかず、古い状態を
ベースに動き続けてしまう実害(例: `data/startgg/schema_backfill_cursor.txt`
を `main` で手動削除したのに、`chore-update` ベースで動く定期実行がそれを
無視して古いカーソル位置から処理を継続した実例)が確認された。二段階の
ブランチ間接化が安全性ではなく不整合の温床になっていたため、直接 `main` へ
commit する方式に改めた。

### V. 外部APIへの耐障害アクセス (Resilient External API Access)
start.gg GraphQL API への呼び出しは `scripts/utils.py` の
`fetch_data_with_retries()` / `fetch_all_nodes()` を MUST 経由し、リトライ・
バックオフ・ページングを個別スクリプトで独自実装することは MUST NOT 行わない。
429 は待機時間延長、5xx は指数バックオフという既存のリトライポリシーを
変更する場合は、その理由を PR 説明または `docs/startgg_design.md` に MUST
明記する。
Rationale: 統一されたリトライ経路がないと、一部スクリプトだけがレート制限で
サイレントに失敗し、データ欠損に気づけなくなる。

## データ保存規約 (Data Storage Conventions)

- 取得データは `data/startgg/` に集約し、`docs/directory.md` で定義された
  `{Region}/{YYYY}/{MM}/{DD}/{Tournament}/{Event}` レイアウトに MUST 従う。
- 既知の不完全な点・未対応事項はコードコメントではなく `docs/fix.md` に
  MUST 記録する（コメントは実装変更に追随せず陳腐化しやすいため）。
- `STARTGG_TOKEN` 等のシークレットはリポジトリに MUST NOT コミットせず、
  GitHub Actions の Secrets 経由でのみ MUST 利用する。

## 開発ワークフロー (Development Workflow)

- スクリプトは役割ごとに `scripts/fetch/`（取得）、`scripts/fix/`（補完・検証・
  修復）、`scripts/queries.py`（読み取り専用の集計・分析）に MUST 分離し、
  責務を混在させない。
- スキーマやワークフロー（`.github/workflows/*.yml`）に変更を加える PR は、
  対応する `docs/*.md` の更新を同一PRに MUST 含める。
- 大量の re-fetch や再構成を伴う破壊的なデータ移行を行う前に、対象範囲と
  想定される影響（対象イベント数・API呼び出し回数など）を PR 説明に MUST
  明記する。

## Governance

この憲法はリポジトリ内の他の慣習・暗黙のルールに優先する。原則と矛盾する
実装や運用は、明確な正当化がない限り MUST NOT マージする。

- **改訂手続き**: 憲法の改訂は `/speckit-constitution` コマンドを通じて行い、
  変更内容を Sync Impact Report として本ファイル冒頭に記録する。
- **バージョニング方針**: semantic versioning（MAJOR.MINOR.PATCH）に従う。
  既存原則の後方非互換な削除・再定義は MAJOR、原則の追加や大幅な拡充は
  MINOR、文言修正や非意味的な明確化は PATCH とする。
- **コンプライアンスレビュー**: `data/` や `scripts/` に触れる PR は、
  レビュー時に本憲法の該当原則との整合性を MUST 確認する。逸脱がある場合は
  PR 説明にその理由を明記しなければ merge してはならない。
- 実行時の詳細なガイダンス（スキーマ定義・API仕様・運用フロー）は
  `docs/data_model.md` / `docs/startgg_design.md` / `docs/flow.md` /
  `docs/githubAction.md` / `docs/directory.md` / `docs/fix.md` を参照する。

**Version**: 2.0.0 | **Ratified**: 2026-07-31 | **Last Amended**: 2026-08-20
