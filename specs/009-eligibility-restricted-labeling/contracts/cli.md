# Contracts: 汎用イベントラベリング機構

## 1. `scripts/labeling.py`(判定エンジン、内部ライブラリ契約)

`scripts/fetch/download.py`・`scripts/fetch/download_specific_event.py`・
`scripts/fix/apply_label_rules.py`が共通で依存する契約。

```python
DEFAULT_LABEL_RULES_PATH = "data/startgg/label_rules.json"

class LabelRuleError(Exception): ...

def load_label_ruleset(path: str = DEFAULT_LABEL_RULES_PATH) -> dict: ...
def compile_label_ruleset(ruleset: dict) -> CompiledLabelRuleSet: ...
def compute_labels(
    compiled: CompiledLabelRuleSet,
    tournament_name: str | None,
    event_name: str | None,
) -> dict[str, bool]: ...
def merge_labels(
    existing_labels: dict | None,
    computed_labels: dict[str, bool],
    managed_label_names: frozenset[str],
) -> dict: ...
def compute_event_labels(
    existing_labels: dict | None,
    tournament_name: str | None,
    event_name: str | None,
    event_data_version: int | None,
    *,
    rules_path: str = DEFAULT_LABEL_RULES_PATH,
) -> tuple[dict, int | None]: ...
```

- `load_label_ruleset`/`compile_label_ruleset`: ファイルが存在しない、
  JSONとして不正、必須フィールド(`label_version`, `matches`)の欠落、
  各ルールの`label`欠落、`tournament_name_match`/`event_name_match`
  両方欠落、正規表現として不正なパターン、のいずれかを検出した場合、
  検出した問題点をすべて列挙した1つの`LabelRuleError`を送出する
  (部分的な検証成功のまま処理を継続しない)。
- `compute_labels`: 一致したラベルのみ`True`で含むdictを返す
  (不一致ラベルはキーを含まない)。マッチングは`re.search`相当の
  部分一致。
- `merge_labels`: `managed_label_names`に含まれない`existing_labels`の
  キーは保持し、含まれるキーは`computed_labels`で完全に置き換える。
- `compute_event_labels`: `event_data_version`が`None`の場合は`0`として
  扱う。ルールセットの`min_event_data_version`要件を満たさない場合は
  `(existing_labels 相当のdict, None)`を返す(呼び出し側は`label_version`
  フィールドへの書き込みを省略すること)。ルールセットは
  `functools.lru_cache`でプロセス内キャッシュされ、`rules_path`ごとに
  1回だけ読み込み・検証・コンパイルされる。

## 2. `scripts/fix/apply_label_rules.py`(一括適用ツール、CLI契約)

### コマンド

```bash
python3 scripts/fix/apply_label_rules.py \
  [--events-root data/startgg/events] \
  [--rules-file data/startgg/label_rules.json] \
  [--indent-num 2] \
  [--yes]
```

start.gg への通信を行わないため、`--token`等のAPI関連引数は一切持たない。

### 引数

| 引数 | 必須 | デフォルト | 意味 |
|---|---|---|---|
| `--events-root` | - | `data/startgg/events` | イベントディレクトリのルート |
| `--rules-file` | - | `data/startgg/label_rules.json` | ラベルルール定義ファイルのパス |
| `--indent-num` | - | `2` | JSON出力のインデント(既存ツールとの一貫性のため) |
| `--yes` | - | (フラグ、指定なしはdry-run) | 指定した場合のみ実際に`attr.json`へ書き込む |

`--yes`を指定しない場合、`attr.json`への書き込みは一切発生せず、
実行結果のサマリーのみが出力される(dry-run、spec Clarifications 参照)。

### 終了コード

- `0`: 正常終了(dry-run・`--yes`のいずれでも、更新0件を含む)。
- `1`: ルール定義ファイルの読み込み・検証エラー(FR-012)、または
  予期しない例外で処理全体が中断した場合。個々のイベントディレクトリの
  スキップ(壊れた`attr.json`・バージョン要件未達)は終了コードに
  影響しない。

### 標準出力(契約として保証する内容)

- ルール定義ファイルの読み込み・検証に失敗した場合、問題点を列挙した
  エラーメッセージを標準エラー出力に表示し、以降の処理を一切行わずに
  終了する。
- 各更新対象イベントについて、`event_id`と新しい`labels`/`label_version`
  を1行で出力する(dry-runの場合も「更新予定」として同様に出力する)。
- 壊れた/存在しない`attr.json`に遭遇した場合は標準エラー出力に警告を
  出し、処理を継続する。
- `min_event_data_version`要件を満たさずスキップしたイベントについて、
  その旨(event_idと理由)を出力する(User Story 4 Acceptance Scenario 1)。
- 終了時に要約行を出力する。
  例: `Done. updated=134 skipped_low_version=0 skipped_up_to_date=26512 skipped_broken=3 (dry-run)`
  `--yes`指定時は末尾の`(dry-run)`を付けない。

## 3. `data/startgg/label_rules.json`(ルール定義ファイル、データ契約)

data-model.md の該当セクションを参照。この契約に違反するファイル
(欠落・JSON不正・スキーマ不正・正規表現不正)は、`scripts/labeling.py`の
`load_label_ruleset`/`compile_label_ruleset`が検出し、新規取得経路・
一括適用ツールのいずれもこれを検出した時点で処理全体を中止する。
