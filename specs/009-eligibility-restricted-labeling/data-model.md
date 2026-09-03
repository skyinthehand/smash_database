# Phase 1 Data Model: 汎用イベントラベリング機構(大会名・イベント名ルールベース判定)

## エンティティ

### `data/startgg/label_rules.json`(ラベルルール定義ファイル、新規データファイル)

```json
{
  "label_version": 1,
  "min_event_data_version": null,
  "matches": [
    {"label": "registration_restricted", "tournament_name_match": "/制限/"},
    {"label": "registration_restricted", "event_name_match": "/制限/"},
    {"label": "casual", "tournament_name_match": "/スマパ/", "event_name_match": "/カジュアル/"}
  ]
}
```

- **`label_version`**(int、必須): このルールセット全体を一意に識別する
  バージョン番号。ルール内容(`matches`)を変更するたびにメンテナが手動で
  増分する(`EVENT_DATA_VERSION`と同様の運用、`002-incremental-schema-backfill`
  参照)。
- **`min_event_data_version`**(int、任意、デフォルト`null`/省略可):
  このルールセットの適用に必要な最低限の`event_data_version`。省略時は
  制約なし(どの`event_data_version`のイベントにも適用可能)。
- **`matches`**(配列、必須。空配列も許容): 各要素は以下を持つ:
  - `label`(文字列、必須): 付与するラベル名。
  - `tournament_name_match`(文字列、任意): `tournament_name`に対する
    正規表現(スラッシュ記法対応、後述)。
  - `event_name_match`(文字列、任意): `event_name`に対する正規表現。
  - `tournament_name_match`/`event_name_match`の少なくとも一方が必須。
    両方指定時はAND条件、片方のみ指定時はその項目のみで判定する。
- **正規表現の記法**: `/パターン/`のように前後をスラッシュで囲んだ場合は
  内側をパターンとして扱い、囲まれていない場合はそのまま全体をパターンと
  して扱う(research.md #2)。パターンはPythonの`re`モジュール構文。
  マッチングは文字列全体の完全一致ではなく`re.search`相当の部分一致
  (spec Clarifications 参照)。大文字小文字・全角半角の自動正規化は
  行わない。
- **同一`label`に対する複数ルール**: OR条件(いずれか1つでも成立すれば
  付与)。異なる`label`同士は互いに独立(複数ラベルが同時にtrueになり
  得る)。
- **不正なファイル**: ファイル自体の欠落・JSONデコードエラー・
  必須フィールド欠落・不正な正規表現は、いずれも起動時に検出され、
  処理全体を中止するエラーとして扱われる(FR-001, FR-012)。

### `scripts/labeling.py`(判定エンジン、新規コードモジュール)

```python
DEFAULT_LABEL_RULES_PATH = "data/startgg/label_rules.json"

class LabelRuleError(Exception):
    """ルール定義ファイルの欠落・JSON不正・検証エラーをまとめて表す。"""

@dataclass
class CompiledLabelRule:
    label: str
    tournament_pattern: re.Pattern | None
    event_pattern: re.Pattern | None

@dataclass
class CompiledLabelRuleSet:
    label_version: int
    min_event_data_version: int | None
    rules: list[CompiledLabelRule]
    managed_label_names: frozenset[str]

def load_label_ruleset(path: str) -> dict: ...
def compile_label_ruleset(ruleset: dict) -> CompiledLabelRuleSet: ...
def compute_labels(compiled: CompiledLabelRuleSet, tournament_name: str | None, event_name: str | None) -> dict[str, bool]: ...
def merge_labels(existing_labels: dict | None, computed_labels: dict[str, bool], managed_label_names: frozenset[str]) -> dict: ...
def compute_event_labels(
    existing_labels: dict | None,
    tournament_name: str | None,
    event_name: str | None,
    event_data_version: int | None,
    *,
    rules_path: str = DEFAULT_LABEL_RULES_PATH,
) -> tuple[dict, int | None]: ...
```

- **`compute_labels`の戻り値**: 一致したラベルのみを`True`で含むdict
  (不一致ラベルはキー自体を含めない)。
- **`merge_labels`の挙動**: `existing_labels`のうち`managed_label_names`
  (現在のルールセットが管理する全ラベル名)に含まれないキーは保持し、
  含まれるキーは`computed_labels`の内容で完全に置き換える(過去に
  付与されたが現在は対象外のラベルは残らない、FR-006)。
- **`compute_event_labels`の戻り値**: `(merged_labels, label_version)`。
  `min_event_data_version`要件を満たさない場合は
  `(existing_labels 相当, None)` を返し、呼び出し側は`label_version`
  フィールドへの書き込みを省略する(FR-011)。ルールセットは
  `functools.lru_cache`でプロセス内キャッシュされる(research.md #3)。

### `attr.json.labels`(既存、スキーマ拡張)

- **型**: 引き続きオブジェクト型。値は真偽値。
- **書き込みタイミング**: `write_event_attributes()`が呼ばれるたび
  (新規取得経路)、または一括適用ツール実行時(既存イベント)に、
  その時点の`tournament_name`/`event_name`とルール定義ファイルを使って
  再計算し、`labels`に非破壊マージして書き込む。
- **既存プロパティとの関係**: `labels`内の、ルール定義ファイルが管理
  しないキー(`registration_type`/`event_type`/`game_rule`等、OpenAI推定
  由来)は一切変更しない。
- **既存データ(本機能導入前に取得されたイベント)**: ルール管理対象の
  ラベルキーが存在しない。一括適用ツール実行後に追加される。

### `attr.json.label_version`(新規フィールド)

- **型**: int(存在しない場合もある)。
- **位置づけ**: `event_data_version`と並ぶ独立したトップレベル
  フィールド。両者は完全に独立したバージョンカウンタであり、
  `min_event_data_version`による依存関係チェック(FR-011)を除き
  互いに関与しない。
- **書き込みタイミング**: `labels`のうちルール管理対象分を算出した
  ルール定義ファイルの`label_version`を記録する。
- **未設定になるケース**: 本機能導入前の既存イベント、および
  `min_event_data_version`要件を満たさずスキップされたイベント
  (この場合、以前の値があればそのまま保持される)。

## 処理フロー

### 新規取得時(`write_event_attributes()`内、`download.py`/`download_specific_event.py`)

```text
labels, label_version = compute_event_labels(
    labels, tournament_name, event_name, EVENT_DATA_VERSION,
)
json_data["labels"] = labels
if label_version is not None:
    json_data["label_version"] = label_version
```

ルール定義ファイルが欠落・不正な場合、`compute_event_labels()`は
`LabelRuleError`を送出し、呼び出し元の取得処理全体が停止する
(research.md #4、意図的な挙動)。

### 一括適用ツール(`scripts/fix/apply_label_rules.py`)

```text
[開始]
  → ルール定義ファイルを読み込み・検証・コンパイル
      (失敗時: エラーを報告して即座に終了、1件も処理しない)
  → data/startgg/events 以下の attr.json を列挙
  → 各 attr.json について:
      try: attr = read_json(path)
      except (OSError, ValueError): skipped_broken += 1; continue

      event_data_version = attr.get("event_data_version") or 0
      if compiled.min_event_data_version is not None
         and event_data_version < compiled.min_event_data_version:
        skipped_low_version += 1; continue   # labels/label_version は一切変更しない

      if attr.get("label_version") == compiled.label_version:
        skipped_up_to_date += 1; continue    # 判定の再計算自体を行わない

      computed = compute_labels(compiled, attr.get("tournament_name"), attr.get("event_name"))
      attr["labels"] = merge_labels(attr.get("labels"), computed, compiled.managed_label_names)
      attr["label_version"] = compiled.label_version
      updated += 1
      if apply_changes:  # --yes 指定時のみ
        write_json(attr, path, with_version=True)
  → サマリー(updated/skipped_low_version/skipped_up_to_date/skipped_broken)
    を出力して正常終了
[終了]
```

`skipped_up_to_date`のゲート(既存`label_version`が現在のルールセットと
一致するイベントは判定自体をスキップする)により、ルール未変更時の
再実行コストを避ける(FR-010)。このゲートを通過したイベントは
`label_version`自体が更新されるため常に書き込み対象になる
(research.md #6、`labels`の内容自体が変わらない場合を含む)。

## `docs/data_model.md`への追記内容(実装タスク)

`attr.json`のスキーマ例に、ルール管理対象ラベルの例と`label_version`を
追記する:

```json
{
  "labels": {
    "registration_type": "full-open",
    "event_type": "main",
    "game_rule": "1on1",
    "registration_restricted": true
  },
  "label_version": 1,
  "event_data_version": 7
}
```

および「注意点」相当のセクションに、ラベル判定ルールは
`data/startgg/label_rules.json`で管理され、判定エンジンは
`scripts/labeling.py`である旨を追記する。
