# Quickstart: 大会属性判定ロジックの内製化(参加資格制限大会ラベル)

## 1. 単体テストを実行する

```bash
python -m unittest scripts.test.test_label_rules
python -m unittest scripts.test.test_apply_registration_restricted_label
python -m unittest scripts.test.test_download   # write_event_attributes への影響確認
python -m unittest scripts.test.test_validate_data
```

期待結果: 全てパスする。特に以下がカバーされていること([data-model.md](./data-model.md) 参照):

- `REGISTRATION_RESTRICTED_KEYWORDS` にある文字列がトーナメント名/イベント名の
  どちらに含まれていても `True` になる。
- キーワードが含まれない場合、`tournament_name`/`event_name` が `None`/空文字列の
  場合に `False` になる。
- `write_event_attributes()` が `labels` の既存プロパティ
  (`registration_type` 等)を保持したまま `registration_restricted` を追加する。
- 一括適用ツールが、壊れた `attr.json` をスキップしつつ残りを処理する。
- 一括適用ツールが同じ入力に対して2回実行しても結果が変わらない(冪等性)。

## 2. ローカルで一括適用ツールを試す

一時ディレクトリにサンプルの `attr.json` を1〜2件用意し、実行して確認する:

```bash
python3 scripts/fix/apply_registration_restricted_label.py \
  --events_root /tmp/sample_events
```

確認ポイント:

- `REGISTRATION_RESTRICTED_KEYWORDS` に一致するサンプルの `attr.json` の
  `labels.registration_restricted` が `true` になること。
- 一致しないサンプルは `false` になること。
- `labels` に元々あった他のキーが変化しないこと。
- start.gg への通信が一切発生しないこと(ネットワークを切断した状態でも
  同じ結果になることで確認できる)。

## 3. 実データに対する影響を事前に確認する(dry-run 的な使い方)

`--events_root` を実際の `data/startgg/events` に向けて一度実行し、
`git diff --stat` で変更されたファイル数・内容を確認してからコミットする:

```bash
python3 scripts/fix/apply_registration_restricted_label.py
git status --short data/startgg/events | wc -l
git diff data/startgg/events | head -50
```

`REGISTRATION_RESTRICTED_KEYWORDS` が空リストのままの場合、既存データは
すべて `registration_restricted: false` になる(誤検知は発生しないが、
本来の判定文字列を追加するまでは意味のある判定結果にはならない)。
