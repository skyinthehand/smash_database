# CLI Contract: `scripts/fix/apply_registration_restricted_label.py`

## コマンド

```bash
python3 scripts/fix/apply_registration_restricted_label.py \
  [--events_root data/startgg/events] \
  [--indent_num 2]
```

`--token` を含む API 関連の引数は一切持たない(start.gg への通信を行わないため)。

## 引数

| 引数 | 必須 | デフォルト | 意味 |
|---|---|---|---|
| `--events_root` | - | `data/startgg/events` | イベントディレクトリのルート |
| `--indent_num` | - | `2` | JSON 出力のインデント(既存ツールとの一貫性のため) |

## 終了コード

- `0`: 正常終了(更新0件を含む)。
- `1`: 予期しない例外で処理全体が中断した場合のみ(個々のイベントの
  スキップは終了コードに影響しない)。

## 標準出力(契約として保証する内容)

- 各更新イベントについて `event_id` と新しい判定結果を1行で出力する。
- 壊れた/存在しない `attr.json` に遭遇した場合は標準エラー出力に警告を出し、
  処理を継続する。
- 終了時に要約行を出力する。
  例: `Done. updated=12 unchanged=26700 skipped=3`

## `scripts/label_rules.py` の契約

- `REGISTRATION_RESTRICTED_KEYWORDS: list[str]` — 判定文字列のリスト。
  空リストも許容する(その場合、全イベントが `registration_restricted: false`
  と判定される)。
- `is_registration_restricted(tournament_name: str | None, event_name: str | None) -> bool`
  — `tournament_name`/`event_name` のいずれかにキーワードが部分一致で
  含まれていれば `True`。両方が `None`/空文字列でもエラーにせず `False` を返す。
