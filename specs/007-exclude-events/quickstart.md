# Quickstart: 取得対象からのイベント除外

実装後、以下の手順でエンドツーエンドに動作確認する。`data-model.md`の
ファイル形状、`spec.md`のFR/SCを合わせて参照。

## 前提

- リポジトリのルートで作業する。
- 除外リストファイルは `data/startgg/excluded_events.json`(実装時の
  正式なパス名は `research.md` Decision 1 に従う)。

## 1. 除外エントリを追加する

まだ取得していない、または今後除外したいevent_idを1件選び、
`data/startgg/excluded_events.json` に直接エントリを追記する
(ファイルが存在しなければ新規作成する)。

```json
{
  "<対象のevent_id>": {
    "excluded_at": "2026-08-29",
    "reason": "動作確認用の一時的な除外エントリ"
  }
}
```

## 2. 通常クロールでの除外を確認する(US1, FR-003/FR-004/FR-004a)

そのevent_idを含むトーナメントに対して `scripts/fetch/download.py`
(または対象を絞った `--tournament_ids` 指定)を実行し、以下を確認する:

- 標準出力に、そのevent_idが除外によりスキップされた旨のログが1行
  出力される(FR-004a)。
- `data/startgg/events/` 配下に、そのevent_idに対応するディレクトリが
  作成されていない(SC-001)。
- 実行後の `data/startgg/tournaments.jsonl` に、そのevent_idが一切
  出現しない(SC-002)。
- 同じトーナメント内の、除外リストに載っていない他のevent_idは通常通り
  取得・登録されている(FR-005)。

## 3. 個別ツール経由での除外を確認する(US3, FR-006)

```bash
python3 scripts/fix/redownload_event.py --token <TOKEN> --event-id <対象のevent_id> --yes
```

- ツールが取得を行わず、除外されている旨を報告して終了することを確認する。

```bash
python3 scripts/fix/backfill_tournament_index.py --token <TOKEN> --dry-run
```

- 対象のevent_idに対応するディレクトリが仮に存在していても、
  `tournaments.jsonl` への追加対象として報告されないことを確認する。

## 4. 除外理由の可読性を確認する(US2, SC-004)

```bash
cat data/startgg/excluded_events.json
```

- 追加のスクリプトやツールを使わずに、event_id・除外日時(`excluded_at`)・
  除外理由(`reason`)の3項目がそのまま読めることを確認する。

## 5. 除外を解除する(FR-008)

`data/startgg/excluded_events.json` から該当event_idのキーを削除する。
以後、そのevent_idは除外リストに未登録のevent_idと同じ扱いになる
(手順2を再実行し、通常通り取得・登録されることを確認する)。

## 6. 自動テスト

```bash
python3 -m unittest discover -s scripts/test
```

除外機構に対応するテスト(`load_excluded_event_ids`の読み込み、各
エントリポイントでのスキップ挙動)を含め、リポジトリ全体のテストが
通ることを確認する(憲法Principle III)。
