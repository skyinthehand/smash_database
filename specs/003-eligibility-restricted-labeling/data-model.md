# Phase 1 Data Model: 大会属性判定ロジックの内製化(参加資格制限大会ラベル)

## エンティティ

### `scripts/label_rules.py`(判定ルール定義)

```python
# 参加資格制限大会かどうかの判定に使う文字列リスト。
# トーナメント名(tournament_name)またはイベント名(event_name)に、
# ここに含まれる文字列が部分一致で含まれていれば「参加資格制限大会」と判定する。
# リストの追加・変更はこのファイルを直接編集し、コミットすることで
# git 履歴として管理する。
REGISTRATION_RESTRICTED_KEYWORDS: list[str] = [
    # 例: "招待制", "参加資格" などの実際の判定文字列をここに追加する
]


def is_registration_restricted(tournament_name: str | None, event_name: str | None) -> bool:
    """tournament_name/event_name のいずれかに REGISTRATION_RESTRICTED_KEYWORDS の
    いずれかが部分一致で含まれていれば True を返す。大文字小文字・全角半角の
    正規化は行わない(単純な `in` 判定)。値が None/空文字列の場合は False。"""
    ...
```

- **型**: `list[str]`(キーワードリスト)+ 純粋関数(判定ロジック)。
- **バージョニング**: git のコミット履歴がそのまま変更履歴になる。専用の
  バージョン番号は持たない(`002` の `EVENT_DATA_VERSION` とは無関係、
  research.md 参照)。

### `attr.json.labels.registration_restricted`(永続化データ)

- **型**: `bool`
- **書き込みタイミング**: `write_event_attributes()` が呼ばれるたび、
  その時点の `tournament_name`/`event_name` と
  `REGISTRATION_RESTRICTED_KEYWORDS` を使って再計算し、`labels` に
  非破壊マージして書き込む。
- **既存プロパティとの関係**: `labels` 内の他のキー
  (`registration_type`/`event_type`/`game_rule` 等、OpenAI推定によるもの)は
  一切変更しない。
- **既存データ(本機能導入前に取得されたイベント)**: `labels` に
  `registration_restricted` キーが存在しない。一括適用ツール実行後に追加される。

## 処理フロー

### 新規取得時(`write_event_attributes()` 内)

```text
labels_out = dict(labels or {})
labels_out["registration_restricted"] = is_registration_restricted(tournament_name, event_name)
json_data["labels"] = labels_out
```

### 一括適用ツール(`scripts/fix/apply_registration_restricted_label.py`)

```text
[開始]
  → data/startgg/events 以下の attr.json を列挙
  → 各 attr.json について:
      try: attr = read_json(path)
      except (OSError, ValueError): スキップ件数 += 1; continue
      restricted = is_registration_restricted(attr.get("tournament_name"), attr.get("event_name"))
      labels = dict(attr.get("labels") or {})
      changed = labels.get("registration_restricted") != restricted
      labels["registration_restricted"] = restricted
      attr["labels"] = labels
      if changed: write_json(attr, path, with_version=True); 更新件数 += 1
      else: 変更なし件数 += 1
  → サマリー(更新件数/変更なし件数/スキップ件数)を出力して正常終了
[終了]
```

`changed` の判定により、値が変わらないイベントについては不要なファイル書き込み
(mtime変化やdiffノイズ)を避ける。

## `docs/data_model.md` への追記内容(実装タスク)

`attr.json` の `labels` サンプルに `registration_restricted` を追記する:

```json
"labels": {
  "registration_type": "full-open",
  "event_type": "main",
  "game_rule": "1on1",
  "registration_restricted": false
},
```

および「注意点」セクションに、判定文字列リストは `scripts/label_rules.py` で
管理される旨を追記する。
