# Quickstart: 汎用イベントラベリング機構(大会名・イベント名ルールベース判定)

## 1. 単体テストを実行する

```bash
python -m unittest scripts.test.test_labeling
python -m unittest scripts.test.test_apply_label_rules
python -m unittest scripts.test.test_download              # write_event_attributes への影響確認
python -m unittest scripts.test.test_download_specific_event
python -m unittest scripts.test.test_validate_data
```

期待結果: 全てパスする。特に以下がカバーされていること
([data-model.md](./data-model.md)・[contracts/cli.md](./contracts/cli.md) 参照):

- `tournament_name_match`のみ・`event_name_match`のみ・両方指定(AND条件)
  のいずれのルールでも判定できる。
- 同じ`label`に対する複数ルールがOR条件で成立する。異なる`label`同士が
  独立に、複数同時に`true`になり得る。
- スラッシュで囲んだパターン(`/制限/`)と囲まないパターン(`制限`)の
  両方が同じ結果になる。
- `tournament_name`/`event_name`が`None`/空文字列でもエラーにならず、
  該当ラベルが付与されない。
- ルール定義ファイルの欠落・JSON不正・不正な正規表現が、明確な
  エラーで検出され処理が中止される。
- `merge_labels`が、ルール管理対象外の既存キー(`registration_type`等)を
  保持したまま、管理対象ラベルのみを完全に再計算する。
- `min_event_data_version`要件を満たさないイベントの`labels`/
  `label_version`が変更されない。
- 一括適用ツールが、壊れた`attr.json`をスキップしつつ残りを処理する。
- 一括適用ツールが、`label_version`が既に一致するイベントを判定自体
  スキップする(処理時間・書き込み双方が発生しない)。
- 一括適用ツールがデフォルトでdry-run(書き込みなし)で動作し、
  `--yes`指定時のみ実際に書き込む。
- 一括適用ツールが同じ入力・同じルール定義に対して2回実行しても結果が
  変わらない(冪等性)。
- `write_event_attributes()`(`download.py`/`download_specific_event.py`
  の両実装)が、`labels`/`label_version`を正しく書き込む。

## 2. サンプルのルール定義ファイルを用意する

```bash
mkdir -p /tmp/labeling_quickstart
cat > /tmp/labeling_quickstart/label_rules.json <<'EOF'
{
  "label_version": 1,
  "matches": [
    {"label": "registration_restricted", "tournament_name_match": "/制限/"},
    {"label": "casual", "tournament_name_match": "/スマパ/", "event_name_match": "/カジュアル/"}
  ]
}
EOF
```

一時ディレクトリに、上記ルールに一致する/しないサンプルの`attr.json`を
2〜3件用意する(`tournament_name`/`event_name`/`event_data_version`を
含む最小限のフィールドでよい)。

## 3. ローカルで一括適用ツールをdry-run実行する

```bash
python3 scripts/fix/apply_label_rules.py \
  --events-root /tmp/labeling_quickstart/events \
  --rules-file /tmp/labeling_quickstart/label_rules.json
```

確認ポイント:

- 末尾のサマリー行に `(dry-run)` が付き、`attr.json`が一切変更されて
  いないこと(`git diff`不要、一時ディレクトリのmtime/内容を確認)。
- ルールに一致するサンプルについて「更新予定」の出力があること。
- 一致しないサンプルには変化がないこと。

`--yes`を付けて再実行し、実際に`labels`/`label_version`が書き込まれる
ことを確認する。続けてもう一度`--yes`付きで実行し、サマリーの
`skipped_up_to_date`が全件になる(判定が再計算されない)ことを確認する。

## 4. 実データに対する影響を事前に確認する

```bash
python3 scripts/fix/apply_label_rules.py
```

(デフォルトで`--events-root data/startgg/events`・
`--rules-file data/startgg/label_rules.json`・dry-runなので、この時点では
`attr.json`は一切変更されない。)サマリー行で影響範囲(`updated`件数)を
確認してから、`--yes`を付けて実行し、`git status --short data/startgg/events`
で変更されたファイル数を確認する。
