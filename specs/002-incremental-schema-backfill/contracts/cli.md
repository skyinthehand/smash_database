# CLI Contract: `scripts/fetch/backfill_schema_version.py`

## コマンド

```bash
python3 scripts/fetch/backfill_schema_version.py \
  --token <STARTGG_TOKEN> \
  [--events_root data/startgg/events] \
  [--users_file_path data/startgg/users.jsonl] \
  [--cursor_path data/startgg/schema_backfill_cursor.txt] \
  [--max_events 200] \
  [--max_retries 20] \
  [--retry_delay 5] \
  [--indent_num 2] \
  [--url https://api.start.gg/gql/alpha]
```

## 引数

| 引数 | 必須 | デフォルト | 意味 |
|---|---|---|---|
| `--token` | ○ | — | start.gg API トークン |
| `--events_root` | - | `data/startgg/events` | イベントディレクトリのルート |
| `--users_file_path` | - | `data/startgg/users.jsonl` | ユーザー情報の読み書き先 |
| `--cursor_path` | - | `data/startgg/schema_backfill_cursor.txt` | カーソル永続化ファイル |
| `--max_events` | - | `200` | 1回の実行で実際に再取得する上限件数(既に最新のイベントをスキップする分は含まない) |
| `--max_retries` / `--retry_delay` | - | `20` / `5` | 既存の `set_retry_parameters()` にそのまま渡す |
| `--indent_num` | - | `2` | JSON 出力のインデント |
| `--url` | - | `https://api.start.gg/gql/alpha` | API エンドポイント |

`--yes` のような dry-run スイッチは持たない(削除を伴わない「不足分の追記」のみを
行うため、`redownload_event.py` のような破壊的操作の確認は不要。ただし
`--dry-run` で「対象件数と最初の数件のパスだけを表示して終了する」ことは
実装時のオプション拡張として妨げない)。

## 終了コード

- `0`: 正常終了(対象0件を含む)。
- `1`: 1件以上の再取得が API エラー等で失敗した場合(`redownload_event.py` の
  `success`/`failure` カウントパターンを踏襲)。

## 標準出力(契約として保証する内容)

- 開始時にカーソル位置と対象候補の走査範囲を出力する。
- 各処理イベントについて `event_id` と再取得結果(成功/失敗)を1行で出力する。
- 終了時に「処理件数」「スキップ件数」「一周したかどうか」を要約行として出力する。
  例: `Done. processed=12 skipped=4310 wrapped_around=false`

## `.github/workflows/schema_backfill.yml` の契約

- **トリガー**: `schedule`(cron、初期値は日次)と `workflow_dispatch`。
- **concurrency**: `group: chore-update-branch`, `cancel-in-progress: true`
  (既存の `update_tournament.yml` / `update_user.yml` と共有)。
- **コミット**: 変更があれば `chore-update` ブランチへ
  `chore(data): backfill event schema version` のようなメッセージでコミットし、
  同ブランチへ push する。`main` への直接 push は行わない。
- **PR**: 既存の `update_tournament.yml` と同じ「`chore-update` → `main` の
  オープンPRが無ければ作成する」ロジックを再利用する(新規に別PRを乱立させない)。
