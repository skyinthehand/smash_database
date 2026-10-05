<!--
Sync Impact Report
-------------------
Version change: 2.2.0 → 2.3.0
Rationale: MINOR — 公開に向けたディレクトリ構成の整理に伴い、データ保存規約と
開発ワークフローのルールを追加・再定義し、IV に現行の push 手段を明記した。
既存原則の削除ではないため、本憲法自身のバージョニング方針（Governance節）に
照らし MINOR とする。

Modified principles / sections:
- IV. ブランチとオートメーションの規律: 対象を `data/`・`state/` に広げ、main は
  ruleset で PR 必須であること、定期更新系ワークフローは bypass list に登録した
  デプロイキー（`DATA_PUSH_DEPLOY_KEY`）で直接 push すること、人による変更は
  PR を経由することを追記（「main へ直接 commit / push する」原則の手段の明確化）。
  Rationale の過去事例のパスは当時のまま残し、現在のパスを補足。
- データ保存規約: `data/` には公開データだけを置き、取得処理の進捗を
  `state/startgg/`、人が編集する設定を `config/startgg/` に分離する項目を追加。
- 開発ワークフロー: スクリプトの役割分担を `fetch/` / `check/`（データを書き換え
  ない）/ `fix/` / `merge/` と直下の共通ライブラリに再定義。
- III. マージ前の検証ゲート: 例の `data_monthly_check.yml`（既に存在しない）を
  実在する定期更新系ワークフローに差し替え（意味は不変）。
- 参照の追随（意味は不変）: `docs/githubAction.md` → `docs/github_actions.md`、
  `docs/chore-tornament` → `docs/chore-tournament`。

Added sections: none (既存の節への追記・再定義のみ)

Removed sections: none

Templates requiring updates:
- .specify/templates/plan-template.md: ✅ no change needed (スクリプト配置・
  データ配置への具体的な言及なし)
- .specify/templates/spec-template.md: ✅ no change needed (同上)
- .specify/templates/tasks-template.md: ✅ no change needed (同上)
- .specify/templates/checklist-template.md: ✅ no change needed (同上)
- .claude/skills/speckit-*/SKILL.md: ✅ no change needed (旧パス・旧ファイル名への
  参照なし)
- docs/directory.md / docs/data_model.md / docs/github_actions.md / CONTRIBUTING.md:
  ✅ refactor/structure ブランチで新構成に更新済み

Follow-up TODOs: none
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
`scripts/test` に MUST 追加する。`update_tournament.yml` などの定期更新系
ワークフローのように、検証失敗がワークフロー全体を失敗させる設計は MUST 維持する。
Rationale: データベース全体の一貫性は自動収集パイプラインの信頼性に直結し、
一度壊れたデータは後から検出・修復するコストが高い。

### IV. ブランチとオートメーションの規律 (Branch & Automation Discipline)
`data/`・`state/` を更新する GitHub Actions 自動化は MUST 中間ブランチを
経由せず、`main` へ直接 commit / push する。複数の自動化ワークフローが同時に
`main` へ push しうる場合、共有の `concurrency` group で MUST 直列化し、push が
競合した場合は `git pull --rebase origin main` による MUST リトライを行う。
`main` に変更を積む前に、Principle III（マージ前の検証ゲート）のテストを
MUST pass させる。
`main` は ruleset で Pull Request を必須にしており、`GITHUB_TOKEN` による直接
push は拒否される。そのため、`main` へ直接 push する定期更新系ワークフローは、
ruleset の bypass list に登録したデプロイキー（Secret `DATA_PUSH_DEPLOY_KEY`）で
MUST checkout し、そのキーで push する。人による変更は MUST Pull Request を
経由する。
`docs/chore-tournament/README.md` と `checked_dates.json` は
`scripts/fix/update_chore_tournament_log.py` 経由でのみ MUST 更新し、手動編集
は MUST NOT 行わない。
Rationale: 以前は自動更新を `chore-update` ブランチに集約し、PR 経由の
rebase auto-merge で `main` に反映していたが、`main` への直接コミット(手動の
修正など)が発生すると `chore-update` 側の自動化はそれに気づかず、古い状態を
ベースに動き続けてしまう実害(例: 当時の `data/startgg/schema_backfill_cursor.txt`
(現在は `state/startgg/schema_backfill_cursor.txt`)を `main` で手動削除したのに、`chore-update` ベースで動く定期実行がそれを
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
- `data/` には利用者向けの公開データ以外を MUST NOT 置かない。取得処理の進捗
  （取得済みID・巡回カーソル）は `state/startgg/`、人が編集する取得処理の設定
  （除外イベント・ラベル判定ルール）は `config/startgg/` に置き、これらのパスは
  `scripts/utils.py` の定数で一元管理する。
  Rationale: 公開データと管理用ファイルが `data/startgg/` に混在し、データだけを
  使いたい利用者にとって、どれが本体か分かりにくかった。
- 既知の不完全な点・未対応事項はコードコメントではなく `docs/fix.md` に
  MUST 記録する（コメントは実装変更に追随せず陳腐化しやすいため）。
- `STARTGG_TOKEN` 等のシークレットはリポジトリに MUST NOT コミットせず、
  GitHub Actions の Secrets 経由でのみ MUST 利用する。

## 開発ワークフロー (Development Workflow)

- スクリプトは役割ごとに `scripts/fetch/`（取得）、`scripts/check/`（検査・診断。
  データを MUST NOT 書き換えない）、`scripts/fix/`（既存データの補完・修復）、
  `scripts/merge/`（マージ競合解消の補助）に MUST 分離し、責務を混在させない。
  `scripts/` 直下には共通ライブラリ（`utils.py` / `queries.py` / `labeling.py`）
  だけを置く。
  Rationale: 調べるだけのスクリプトと書き換えるスクリプトが `scripts/fix/` に
  混在し、`scripts/` 直下にもどこにも属さないスクリプトがあった。
- スキーマやワークフロー（`.github/workflows/*.yml`）に変更を加える PR は、
  対応する `docs/*.md` の更新を同一PRに MUST 含める。
- 大量の re-fetch や再構成を伴う破壊的なデータ移行を行う前に、対象範囲と
  想定される影響（対象イベント数・API呼び出し回数など）を PR 説明に MUST
  明記する。
- spec-kit コマンド（`/speckit-specify` / `/speckit-clarify` / `/speckit-plan` /
  `/speckit-tasks` 等）が `specs/` 配下に生成するドキュメント（`spec.md` /
  `plan.md` / `research.md` / `data-model.md` / `quickstart.md` /
  `contracts/` / `tasks.md` / `checklists/` 等）は、コード識別子・
  ファイルパス・フィールド名・関数名などコード由来の用語を除き、MUST
  日本語で記述する。
  Rationale: コミットメッセージや既存の `docs/` 配下のドキュメントは
  日本語で書かれており、spec-kit の成果物だけ英語のままだと一貫性が無く、
  後から日本語へ翻訳し直す手戻りが発生する。
- コミットメッセージは Conventional Commits 形式とし、変更内容を最も具体的に
  表す種類（`feat` / `fix` / `docs` / `build` / `ci` / `refactor` / `test` /
  `perf` / `style` / `revert`）を MUST 選ぶ。`chore` は他のどの種類にも
  当てはまらない場合にのみ使い、何でも入る受け皿として MUST NOT 使わない。
  種類の異なる変更は MUST 別のコミットに分ける。
  - 例: 依存関係（`requirements.txt`）は `build`、ワークフロー・Dependabot は
    `ci`、ドキュメントは `docs`、不具合を直すデータ・設定の変更（除外イベントの
    追加など）は `fix(data)`。
  - 自動化ワークフローが定期的に行うデータ更新の `chore(data):` は、既存の
    慣習として許容する。
  Rationale: `chore` を受け皿として使うと、コミットの中身が履歴から読み取れ
  なくなる。実際に、依存関係・Dependabot・セキュリティポリシーの追加を1つの
  `chore` コミットにまとめた例や、カーソルの停止を直す除外設定を `chore` に
  した例があった。

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
  `docs/github_actions.md` / `docs/directory.md` / `docs/fix.md` を参照する。

**Version**: 2.3.0 | **Ratified**: 2026-07-31 | **Last Amended**: 2026-10-05
