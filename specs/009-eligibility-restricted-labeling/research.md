# Phase 0 Research: 汎用イベントラベリング機構(大会名・イベント名ルールベース判定)

## 0. 既存コードベースの前提調査(設計の土台)

実装対象コードを事前に調査し、以下を確認した(以降の決定の前提):

- `write_event_attributes()` は実は**2つの独立した実装**が存在する:
  `scripts/fetch/download.py`(2箇所の呼び出し元)と
  `scripts/fetch/download_specific_event.py`(独自実装、1箇所の呼び出し元)。
  一方、`scripts/fix/redownload_event.py`・`scripts/fetch/backfill_schema_version.py`・
  `scripts/fix/backfill_events.py` の3つは、いずれも
  `scripts.fetch.download` から `write_event_attributes` を import しており、
  **独自実装を持たない**(呼び出し元が異なるだけ)。したがって FR-005 が挙げる
  5つの経路のうち、実際にコード変更が必要な箇所は
  `scripts/fetch/download.py` と `scripts/fetch/download_specific_event.py`
  の2ファイル(2つの`write_event_attributes`実装)のみである。
- 現在、全ての呼び出し元は `write_event_attributes(...)` の `labels` 引数に
  常に空dict `{}` を渡している(OpenAIによる`registration_type`等の推定結果を
  渡している呼び出し元は現状存在しない)。一方、実データ
  (`data/startgg/events/**/attr.json`)には既に28件、過去の一括処理由来と
  見られる `labels.registration_type`/`event_type`/`game_rule` が存在する。
  → FR-006の非破壊マージ要件は、新規取得経路(現状は空dictを渡すため実害は
  限定的)よりも、**一括適用ツール側(既存の`attr.json`を直接読み書きする)**
  で確実に守ることが特に重要である。
- `scripts/fix/validate_data.py` の `ATTR_REQUIRED_FIELDS` は「最低限
  必須のフィールド」の一覧であり、未知の追加フィールドを禁止する
  allow-list 検証ではない。したがって新規トップレベルフィールド
  `label_version` を追加しても `validate_data.py` の変更は不要。

## 1. ルール定義ファイルの置き場所・形式

- **Decision**: `data/startgg/label_rules.json` を新設する。トップレベルに
  `label_version`(数値、必須)・`min_event_data_version`(数値、任意)・
  `matches`(ルール配列、必須)を持つ。各ルールは `label`(文字列)・
  `tournament_name_match`(文字列、任意)・`event_name_match`(文字列、任意)を
  持つ。
- **Rationale**: 本 spec の Key Entities で既にこのパスが明示されている。
  `data/startgg/excluded_events.json`(`007-exclude-events`)と同様、
  「プログラムが生成するfetch結果ではないが、`data/startgg/`配下でgit管理される
  人間編集の設定ファイル」という既存の前例に倣う。取得データそのもの
  (`tournaments.jsonl`等)と物理的に隣接させることで、判定対象データと
  ルール定義の対応関係が分かりやすくなる。
- **Alternatives considered**: 旧spec案(初版2026-08-01)のように
  `scripts/label_rules.py` にPythonリストとして定義する案 — 却下。今回の
  再検討で「ルールはトーナメント名・イベント名ごとに個別に判定できる
  構造化データであるべき」という要件に変わったため、単純な文字列リストでは
  表現できない。JSONの方が非エンジニアにも読み書きしやすく、
  `excluded_events.json` との一貫性もある。

## 2. 正規表現のスラッシュ記法(`/pattern/`)の扱い

- **Decision**: パターン文字列が `/` で始まり `/` で終わり、かつ長さが2文字
  以上の場合、前後の `/` を取り除いた内側の文字列を正規表現として扱う。
  それ以外(スラッシュで囲まれていない文字列)は、そのまま正規表現として
  扱う。つまりスラッシュの有無どちらも受け付ける。
- **Rationale**: spec入力例の `"/制限/"` という記法(他言語の正規表現
  リテラルに倣った可読性のための記法)をそのまま使えるようにしつつ、
  スラッシュを省略した `"制限"` のような素朴な記法も同時にエラーなく
  受け付けることで、ルール作成者の記述揺れを吸収する。spec の
  Assumptions で「実装時にスラッシュの有無どちらも受け付けるかは
  `/speckit-plan` で確定する」とされていた事項への回答。
- **Alternatives considered**: スラッシュ記法を必須にする案 — 却下
  (素朴に書いた場合にエラーになり不親切)。スラッシュを常に除去せず
  常に正規表現の一部として扱う案 — 却下(spec入力例と矛盾する)。

## 3. 判定エンジンの実装場所

- **Decision**: 新規モジュール `scripts/labeling.py` を追加する。責務は
  以下の通り:
  - `load_label_ruleset(path) -> dict`: JSONの読み込み。ファイル欠落・
    JSONデコードエラーは `LabelRuleError` に変換する(FR-012)。
  - `compile_label_ruleset(ruleset: dict) -> CompiledLabelRuleSet`:
    各ルールの正規表現(スラッシュ記法を#2の規則で正規化した上で)を
    `re.compile()` する。不正な正規表現・必須フィールド欠落
    (`label`必須、`tournament_name_match`/`event_name_match`の少なくとも
    一方が必須)を全ルール分まとめて検証し、問題があれば全件をまとめた
    メッセージで `LabelRuleError` を送出する(FR-001, FR-012)。
  - `compute_labels(compiled, tournament_name, event_name) -> dict[str, bool]`:
    一致したラベルのみを `True` で含む dict を返す(不一致ラベルはキー自体を
    含めない、FR-002, FR-003)。マッチングは `re.search` 相当の部分一致
    (spec Clarifications 参照)。
  - `merge_labels(existing_labels, computed_labels, managed_label_names) -> dict`:
    `existing_labels` のうち `managed_label_names`(現在のルールセットが
    管理する全ラベル名の集合)に含まれないキーはそのまま保持し、
    `managed_label_names` に該当するキーは一旦除去した上で
    `computed_labels` を反映する(FR-006)。
  - `compute_event_labels(existing_labels, tournament_name, event_name, event_data_version, *, rules_path=DEFAULT_LABEL_RULES_PATH) -> tuple[dict, int | None]`:
    上記を組み合わせた高レベル関数。ルールセットは
    `functools.lru_cache` でプロセス内キャッシュし(同一パスなら1回だけ
    読み込み・コンパイルする)、`min_event_data_version` 要件を満たさない
    場合は `(existing_labels, None)` を返す(呼び出し側は `label_version`
    フィールドへの書き込みを省略する、FR-011)。要件を満たす場合は
    `(merge_labels(...), ruleset["label_version"])` を返す。
    `event_data_version` が `None` の場合は `0` として扱う
    (spec Clarifications 参照)。
- **Rationale**: 新規取得経路(`download.py`/`download_specific_event.py`)と
  一括適用ツール(`scripts/fix/apply_label_rules.py`)の両方から同じ判定
  ロジックを再利用する必要があるため、両者に依存されない独立モジュールに
  切り出す(`scripts/utils.py`と同様の位置づけ)。プロセス内キャッシュに
  より、大量のイベントを処理する一括適用ツール・大量取得を行う
  `download.py` のいずれでも、ルールファイルの読み込み・正規表現コンパイルは
  1プロセスにつき1回で済む。
- **Alternatives considered**: 判定ロジックを一括適用ツールの内部関数として
  実装し、新規取得経路側は重複実装する案 — 却下(ロジックの重複は
  `002-incremental-schema-backfill` 以前に実際に問題になった前例
  (research.md #2 相当)を繰り返すことになる)。

## 4. 新規取得経路(`write_event_attributes`)への組み込み

- **Decision**: `scripts/fetch/download.py`・
  `scripts/fetch/download_specific_event.py` それぞれの
  `write_event_attributes()` 内で、`json_data` を組み立てる直前に
  `labels, label_version = compute_event_labels(labels, tournament_name, event_name, EVENT_DATA_VERSION)`
  を呼び出す。`json_data["labels"] = labels` とし、`label_version` が
  `None` でなければ `json_data["label_version"] = label_version` を設定する
  (`None` の場合はキー自体を設定しない = FR-011のスキップ)。
  `scripts/fix/redownload_event.py`・`scripts/fetch/backfill_schema_version.py`・
  `scripts/fix/backfill_events.py` は `download.py` の実装を import して
  いるだけなので、コード変更は不要で自動的にこの挙動を継承する。
- **Rationale**: 呼び出し元(6箇所)のシグネチャ変更を一切必要とせず、
  既存の `labels`(常に`{}`)引数をそのまま活かせる。`EVENT_DATA_VERSION`は
  既にモジュールレベル定数として `write_event_attributes()` 内から参照
  可能なため、追加の引数も不要。
- **重要な設計上の含意**: ルール定義ファイル(`data/startgg/label_rules.json`)
  が存在しない・壊れている場合、`compute_event_labels()` は
  `LabelRuleError` を送出し、新規イベント取得処理全体(`download.py`の
  実行等)が停止する(FR-012の「処理を中止する」を新規取得経路にも
  適用した結果)。これは意図的な挙動である(spec Clarifications
  参照、不正なルールファイルを検出せず一部のイベントだけ誤った判定で
  取得され続ける事態を避けるため)。

## 5. 既存データへの一括適用ツール

- **Decision**: 新規スクリプト `scripts/fix/apply_label_rules.py` を追加する。
  `scripts/fix/fix_path_collision.py`(`008-tournament-path-collision`)の
  慣例に倣い、**デフォルトはdry-run**(サマリーのみ出力、書き込みなし)とし、
  `--yes` を指定した場合のみ実際に `attr.json` へ書き込む
  (spec Clarifications 参照)。処理フロー:
  1. `data/startgg/label_rules.json` を読み込み・検証・コンパイルする
     (失敗時は即座にエラー終了、1件も処理しない、FR-012)。
  2. `events_root.rglob("attr.json")` で全イベントディレクトリを走査する
     (`validate_data.py`/`find_empty_events.py`と同じ走査パターン)。
  3. 各 `attr.json` について:
     - 読み込み失敗(`OSError`/`JSONDecodeError`)→ `skipped_broken` を
       加算しスキップ(FR-009)。
     - `min_event_data_version` 要件を満たさない(`event_data_version`が
       未設定の場合は`0`として比較)→ `skipped_low_version` を加算し
       スキップ、`labels`/`label_version`は一切変更しない(FR-011)。
     - 既存の `label_version` が現在のルールセットの`label_version`と
       一致する → `skipped_up_to_date` を加算し、判定の再計算自体を
       行わずスキップ(FR-010前半)。
     - 上記いずれにも該当しない → `compute_labels`/`merge_labels`で
       判定を再計算し、`labels`/`label_version`を更新して(dry-runでなければ)
       書き戻す。`updated` を加算する(#6 参照、このパスに到達した
       イベントは常に書き込み対象になる)。
  4. 最終的に `updated`/`skipped_low_version`/`skipped_up_to_date`/
     `skipped_broken` の件数サマリーを標準出力に表示する。
- **Rationale**: 既存の `scripts/fix/` 配下ツールの走査・エラー処理・
  dry-run規約を再利用することで、新規パターンを持ち込まない。
- **Alternatives considered**: `scripts/fetch/backfill_schema_version.py`に
  統合する案 — 却下(あちらはAPI再取得・カーソルベースの段階的処理が
  前提であり、本機能は「即座に全件をローカルのみで処理できる」という
  性質上、統合すると条件分岐が複雑化し可読性が下がる。spec Assumptionsの
  想定とも一致)。

## 6. FR-010「結果が変化する場合のみ書き込む」の解釈

- **Decision**: 一括適用ツールにおいて、あるイベントの `label_version` が
  現在のルールセットの `label_version` と既に一致している場合は
  #5 の通り判定の再計算自体をスキップする(書き込みなし)。それ以外
  ―― つまり `label_version` が不一致(未設定・古い値を含む)で#5の
  スキップ条件に該当しなかった場合 ―― は、`labels`の内容自体が
  変化するかどうかに関わらず、**常に書き込みを行う**(`label_version`
  フィールド自体が新しい値に更新されるため、これも「結果の変化」に
  含まれると解釈する)。
- **Rationale**: `label_version`を更新せずに処理をスキップしてしまうと、
  そのイベントは次回実行時も「未一致」のまま残り続け、ルールセットが
  変わらない限り毎回無駄に再計算対象になってしまい、FR-010前半の
  スキップ最適化の効果が薄れる(いつまでも最新化されないイベントが
  蓄積する)。「`label_version`が一致していれば判定自体をスキップする」
  (#5の一段目のゲート)が本来のコスト最適化の主眼であり、「結果が
  変化する場合のみ書き込む」という文言は、このゲートを一度通過した
  イベントについて `labels` の内容だけを比較して書き込みを絞り込む
  追加の最適化を意図したものではない、と解釈する。
- **Alternatives considered**: `labels`の内容が実際に変化しない限り
  `label_version`も含めて一切書き込まない案 — 却下。上記の通り、
  ルールセットが変更されるたびに該当イベントが恒久的に「未一致」の
  ままになり、以後のあらゆる一括適用実行で毎回無駄な再計算対象
  (約26,000件規模)になり続けるため、FR-010の目的(不要な再計算
  コストを避ける)にかえって反する。

## 7. ドキュメント更新

- **Decision**: `docs/data_model.md` の `attr.json` スキーマ例に、
  `labels` 内のルール管理対象ラベルの例(例: `registration_restricted: true`)
  と、新規トップレベルフィールド `label_version` を追記する。あわせて
  「注意点」相当のセクションに、ラベル判定ルールは
  `data/startgg/label_rules.json` で管理される旨、および判定エンジンは
  `scripts/labeling.py` である旨を追記する。
- **Rationale**: Constitution原則I(データスキーマの整合性とバージョニング)
  により、スキーマ変更は同一PRで `docs/data_model.md` を更新することが
  MUST。

## Resolved unknowns

Technical Context の項目は全て上記決定で確定し、NEEDS CLARIFICATION は
残っていない。
