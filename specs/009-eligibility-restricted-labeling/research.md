# Phase 0 Research: 大会属性判定ロジックの内製化(参加資格制限大会ラベル)

## 1. 判定文字列リストの置き場所・形式

- **Decision**: 新規モジュール `scripts/label_rules.py` を追加し、プレーンな
  Python の文字列リスト定数 `REGISTRATION_RESTRICTED_KEYWORDS: list[str]` として
  定義する。あわせて、判定ロジック本体
  `is_registration_restricted(tournament_name, event_name) -> bool` も
  同モジュールに実装する。
- **Rationale**: 本リポジトリでは `EVENT_DATA_VERSION`/`JSON_VERSION` のような
  「バージョン管理したい設定値」を既に `scripts/utils.py` のプレーンな
  Python 定数として管理しており、この慣習に合わせることで新しいファイル形式・
  パーサーを追加せずに済む。git diff でリストの変更内容がそのまま見える点も
  「gitでバージョン管理できればOK」という要望に合致する。判定ロジックと
  リストを同じモジュールに置くことで、呼び出し側は関数を呼ぶだけで済み、
  リストの形式変更の影響を受けない。
- **Alternatives considered**: `data/` 配下の JSON ファイル — 却下。
  パーサー・読み込みコードが新たに必要になり、`scripts/utils.py` の
  既存パターンとも一貫しない。非エンジニアが編集する想定であれば有力な
  選択肢だが、本 spec ではその要件は明言されていない。

## 2. 新規取得経路への組み込み方法

- **Decision**: `write_event_attributes()`(`scripts/fetch/download.py` /
  `scripts/fetch/download_specific_event.py` の両実装)の内部で、既に
  引数として受け取っている `tournament_name`/`event_name`/`labels` を使い、
  `labels = {**(labels or {}), "registration_restricted": is_registration_restricted(tournament_name, event_name)}`
  のように非破壊マージしてから `json_data["labels"]` に設定する。
- **Rationale**: `event_data_version`/`guest_entrant_count` の実装と同様、
  `write_event_attributes()` は全呼び出し経路(`download.py` 2箇所,
  `download_specific_event.py`, `redownload_event.py`, `backfill_events.py`,
  `backfill_schema_version.py`)が既に通る唯一の共通点であるため、ここに
  実装すれば呼び出し元のシグネチャ変更は一切不要になる。既存の
  `labels = {}` という呼び出し元のコードもそのまま動作する
  (空dictに対して非破壊マージしても問題ない)。
- **Alternatives considered**: 各呼び出し元で個別に `labels["registration_restricted"] = ...`
  を追加する案 — 却下。6箇所すべてに同じ1行を追加する必要があり、
  将来同様の判定を追加するたびに同じ修正が繰り返される。

## 3. 既存データへの一括適用ツール

- **Decision**: 新規スクリプト `scripts/fix/apply_registration_restricted_label.py`
  を追加する。`data/startgg/events` 以下の `attr.json` を全件走査し、
  各ファイルの `tournament_name`/`event_name` から
  `is_registration_restricted()` を再計算し、`labels.registration_restricted`
  のみを更新して書き戻す(他のフィールド・`labels` 内の他プロパティは
  一切変更しない)。start.gg への API 通信は行わない(トークン引数も
  持たない)。
- **Rationale**: `scripts/fix/` は既存の「補完・検証・修復」ツール群の置き場所
  であり、`find_empty_events.py`/`validate_data.py` と同じ
  `events_root.rglob("attr.json")` ベースの走査パターンを再利用できる。
  API通信を行わないため `002-incremental-schema-backfill` の
  `EVENT_DATA_VERSION`・カーソル・スケジュール実行の仕組みとは独立させる
  (spec の Assumptions のとおり)。
- **Alternatives considered**: `scripts/fetch/backfill_schema_version.py` に
  統合する案 — 却下。あちらは API 再取得とカーソルベースの段階的処理が
  前提であり、本機能は「即座に全件処理できる、API不要のローカル処理」という
  性質上、統合すると条件分岐が複雑になり、可読性が下がる。

## 4. `attr.json` の部分更新方法

- **Decision**: 一括適用ツールは、`scripts.utils.read_json()` で `attr.json`
  全体を読み込み、`labels` キーが無ければ空dictとして扱い、
  `registration_restricted` キーのみを追加・上書きしたうえで、
  `scripts.utils.write_json(data, path, with_version=True)` でファイル全体を
  書き戻す。`fetched_at`/`event_data_version`/`guest_entrant_count` 等の
  他フィールドは読み込んだ値をそのまま保持する(再計算・変更しない)。
- **Rationale**: この処理はあくまで「ローカルデータの導出ラベルの再計算」で
  あり、「データを再取得した」という意味を持つ `fetched_at` 等を変更するのは
  誤解を招く。ファイル全体を読み込んで特定フィールドだけ書き換えることで、
  他ツール(`redownload_event.py` 等)による今後の変更とも独立して動作する。

## 5. `attr.json` が存在しない・壊れている場合の扱い

- **Decision**: `read_json()` が `OSError`/`ValueError`(JSON デコードエラー)を
  送出した場合はそのイベントディレクトリをスキップし、警告を標準エラー出力に
  出したうえで処理を継続する。最終的に処理件数・スキップ件数のサマリーを
  出力する。
- **Rationale**: `validate_data.py`/`find_empty_events.py`/
  `backfill_schema_version.py` で既に確立されている
  「壊れたデータでも全体を止めない」という一貫したエラーハンドリング方針を
  踏襲する。

## Resolved unknowns

Technical Context の項目はすべて上記決定で確定し、NEEDS CLARIFICATION は
残っていない。
