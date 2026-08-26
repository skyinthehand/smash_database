# 契約: `matches.json` レコード形状

このプロジェクトには外部ユーザー向けのネットワークAPIやCLI表面は無い——
その「インターフェース」は`data/startgg/`配下に書き出すJSONファイルであり、
本リポジトリ内の他のスクリプト（`scripts/fix/validate_data.py`、
`scripts/queries.py`、`scripts/fetch/backfill_schema_version.py`）や、
`docs/data_model.md`に従ってコミット済みデータを直接読む誰か、によって消費
される。本ドキュメントは、本機能が変更する唯一のファイル形状に関する契約
である。

## 生産者（Producer）

`scripts/fetch/download.py`（`matches.json`を書き込む全てのエントリポイント:
メインの`download_all_tournaments()`経路、`download_specific_event.py`、
`backfill_schema_version.py`の再取得経路）。

## 消費者（Consumers）

- `scripts/fix/validate_data.py` — `attr.json`の存在によって発見したイベント
  について`matches.json`を読む（research.md §7参照）。FR-010により、
  `attr.json`が存在するイベントについては、常に完全に`complete`な
  レコードのみを見ることが保証されなければならない——これが、既存の
  バリデータを変更せずとも正しく動作し続けるための不変条件である。
- `scripts/queries.py`やその他の読み取り専用の分析コード — 同じ不変条件:
  イベントが「完了」（`attr.json`/`archive_status`経由）として公開される
  のは、`matches.json`にプレースホルダーレコードが1件も無い場合のみ。
- `scripts/fetch/backfill_schema_version.py` — 生産者（古いイベントを
  再取得する）であると同時に、間接的にはプレースホルダー/完了済みの状態を
  読み取って、部分的にバックフィル済みのイベントに何が未取得として残って
  いるかを判断する消費者でもある。

## 本機能が守るべき保証

1. **`attr.json`をゲートに使う消費者が、プレースホルダーレコードを観測する
   ことは無い。** `attr.json`（`archive_status: "completed"`付き）が
   書き込まれるのは、そのイベントの`matches.json`内の全レコードが
   `complete`である場合に限る（FR-010）。`attr.json`を先に確認せずに
   `matches.json`を読む消費者は、これまでもイベントのデータが
   不在/不完全であることを許容せざるを得なかった（本機能以前から中断は
   起こり得た）——本機能はこの既存の前提を変えるのではなく、「不完全」を
   ファイル欠如ではなくファイル内のより粒度の細かい表現に変えるだけである。

2. **`set_id`の一意性。** 1つのイベントの`matches.json`内では、
   状態を問わず、2つのレコードが同じ`set_id`を共有することは無い
   （FR-009）。消費者は`set_id`をキーとして安全に扱ってよい。

3. **単調な状態遷移。** レコードは`placeholder → complete`にのみ遷移し、
   逆方向には遷移しない。その遷移をまたいで`set_id`は不変である
   （data-model.md）。

4. **後方互換な完了済みレコード形状。** `complete`状態は、本機能導入前の
   既存`matches.json`レコード形状（`winner_id`、`loser_id`、
   `winner_score`、`loser_score`、`round_text`、`round`、`phase`、
   `phase_order`、`wave`、`dq`、`cancel`、`state`、`details`）に、新規の
   `set_id`フィールドを加えたものである。既存フィールドの改名・型変更・
   削除は行わない——本機能導入前の形状を前提に書かれた消費者コードは、
   `set_id`が増える点を除き、`complete`レコードに対して変更無く動作し
   続ける。

## 対象外（明示的にスコープ外）

- プレースホルダーレコードは、`attr.json`でゲートされたイベントのみを見る
  消費者（保証#1で述べた既存の標準的な利用パターン）にとって、必ずしも
  目に触れる保証は無い。
- 本契約は`standings.json`、`seeds.json`、`attr.json`を対象としない——
  これらは本機能により変更されない。
