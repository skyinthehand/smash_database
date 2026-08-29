# Quickstart: 同日同名トーナメントの保存先パス衝突の解消

実装後、以下の手順でエンドツーエンドに動作確認する。`data-model.md`/
`research.md`を合わせて参照。

## 1. 新規衝突の防止を確認する(US1, FR-001〜FR-003/FR-006/FR-007)

同じ地域・開催日・大会名を持つ、tournament_idが異なる2大会分のデータを
通常のクロール(`scripts/fetch/download.py`)で取得する(実運用では
偶然の一致を待つしかないため、検証時はテスト用の一時データ・モックで
2大会を意図的に衝突させる)。

- 両者が別々のディレクトリに保存されていることを確認する。
- `data/startgg/tournaments.jsonl` の両者の`path`が、実際のディスク上の
  ディレクトリと一致していることを確認する。
- 衝突の無い(地域・開催日・大会名のいずれかが異なる)組み合わせでは、
  従来通りの挙動(名前調整なし)であることを確認する。

## 2. 参加者数に基づく優先順位を確認する(US2, FR-002/FR-004/FR-005)

参加者数が異なる2つの同日同名大会を衝突させ、参加者数が少ない方だけが
`大会名_(tournament_id)`の形式に調整され、参加者数が多い方は元の名前の
ままであることを確認する。

**同一の取得処理内での3件目(入れ替わりを確認)**: 上記と同じ1回の
クロール実行の中で、さらに参加者数の多い3件目の同日同名大会を追加で
衝突させ、最終的にその3件目が元の名前を維持し、それまで暫定的に元の
名前を維持していた1件目(または2件目)側が調整されることを確認する
(Edge Cases、ユーザーフィードバック2026-08-29)。

**別の取得処理をまたいだ4件目(ロックを確認)**: 上記のクロール実行が
完了し結果が保存された後、**別の**クロール実行で、確定済みの勝者より
さらに参加者数の多い4件目の同日同名大会を検出させ、既に確定・保存済み
の保存先が再度変更されず、4件目のみが調整されることを確認する
(FR-005)。

## 3. 既存データの監査を確認する(US3, FR-008)

```bash
python3 scripts/fix/find_path_collisions.py
```

- 意図的に衝突を再現したテストデータ(2つの異なるtournament_idが同一の
  `path`を`tournaments.jsonl`に記録している状態)に対して実行し、その
  組み合わせが一覧に出力されることを確認する。
- 衝突が存在しない通常のデータに対しては、何も報告されないことを確認する。

## 4. 修復ツールを確認する(US4, FR-009〜FR-011)

```bash
# まずは確認のみ(--yes無し): 対象・現状・実行後の見込みが表示され、
# 実際の変更は一切発生しないことを確認する(2件でも3件以上でも可)。
# 対象データは全て既にディスク上に存在するため、start.gg への再取得は
# 行わない(--tokenは不要)。
python3 scripts/fix/fix_path_collision.py \
  --event-id <衝突当事者1のevent_id> <衝突当事者2のevent_id>

# 実際に修復する
python3 scripts/fix/fix_path_collision.py \
  --event-id <衝突当事者1のevent_id> <衝突当事者2のevent_id> --yes
```

- `--yes`無しの実行では、`data/startgg/`配下・`tournaments.jsonl`が
  一切変更されていないことを確認する。
- `--yes`付きの実行後、指定した全event_idがそれぞれ別ディレクトリに
  分離され、参加者数が最多の1件の保存先名だけが変更されていないこと、
  `tournaments.jsonl`の全員分のパスが実体と一致していることを確認する。
- 同一パスに3件以上が衝突しているケースでは、`--event-id`に3件以上を
  まとめて指定して実行し、参加者数が最多の1件のみが元の名前を維持する
  ことを確認する(ユーザーフィードバック2026-08-29、`research.md`
  Decision 6)。

## 5. `redownload_event.py`自身の衝突回避を確認する(US5, FR-012)

```bash
# 既に別のevent_idのデータが存在するディレクトリと同じ保存先に
# 解決される、無関係なevent_idを指定して再取得する。
python3 scripts/fix/redownload_event.py --token <TOKEN> --event-id <対象のevent_id> --yes
```

- 既存の(別event_idの)ディレクトリの内容が一切変更されていないことを
  確認する。
- 指定したevent_id側は、`大会名_(tournament_id)`の形式に調整された、
  別のディレクトリに保存されていることを確認する。
- 衝突しない通常のevent_idを指定した場合は、従来通りの挙動(名前調整
  なし)であることを確認する。
- 同じevent_idで再度実行し、調整後の保存先が前回と同じであることを
  確認する(FR-012)。

## 6. 自動テスト

```bash
python3 -m unittest discover -s scripts/test
```

衝突検出・命名調整ロジック(`build_path_index`/`resolve_path_collision`/
`disambiguate_event_name`/`path_occupied_by_different_event`)、
`download_all_tournaments`/`download_by_ids`/`redownload_event.py`への
統合、`find_path_collisions.py`/`fix_path_collision.py`の新規テストを
含め、リポジトリ全体のテストが通ることを確認する(憲法Principle III)。
