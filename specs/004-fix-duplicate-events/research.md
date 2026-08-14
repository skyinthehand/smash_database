# Research: 大会延期による重複イベントディレクトリとattr.json欠落の解消

Technical Context に `NEEDS CLARIFICATION` は無い(既存コードベースの延長で完結するため)。
本ドキュメントは、実装方針を決定する上で調査・比較検討した論点を記録する。

## 論点1: 延期の検知方法

**Decision**: `should_skip_tournament()` に、現在の(API から取得した最新の)`startAt` から
計算した年月日と、`tournaments.jsonl` に記録済みの各イベントのパスに含まれる年月日を比較する
チェックを追加する。一致しなければ「延期された」とみなし、`force_refresh` と同様にスキップ
せず再処理対象に含める。

**Rationale**: `download_all_tournaments()` は大会一覧をページングで取得する際、毎回
`tournament["startAt"]`(最新値)を既に取得している。追加の API 呼び出しなしに、既存の
値を使って延期を検知できる。`get_date_parts()` は `time.gmtime()` ベースで
`{YYYY}/{MM}/{DD}` の3セグメントを生成するため、これと同じフォーマットの文字列
(`f"/{year}/{month}/{day}/"`)が記録済みパスに部分文字列として含まれるかどうかで判定できる
(ゼロパディングされた固定長セグメントなので誤検知の余地がない)。

**Alternatives considered**:
- *大会ごとに毎回 `fetch_tournament_by_id()` で最新情報を取り直す*: 追加のAPI呼び出しが
  発生し、Constitution の「不要な負荷を避ける」(原則II)に反する。一覧取得の時点で既に最新
  `startAt` を持っているため不要。
- *`event_files_complete()` の判定基準に「ファイルの中身(entrant数など)」を加える*:
  0エントラントの大会が本当に存在する(不成立・中止)場合と区別できず、誤検知のリスクが
  高い。日付比較という構造的な手がかりの方が確実。

## 論点2: 重複ディレクトリの統合(旧ディレクトリの削除)タイミング

**Decision**: 新しいディレクトリへの書き込みが完了し `event_files_complete(new_dir)` が
`True` になったこと(= `attr.json` を含む必須4ファイルが揃ったこと)を確認できた場合にのみ、
`shutil.rmtree(old_dir)` で旧ディレクトリを削除し、`tournaments.jsonl` の記録パスを新しい
パスに更新する。新ディレクトリが不完全なまま処理が打ち切られた場合(大規模イベントの取得
失敗など)は、旧ディレクトリは削除せず、次回実行時に再度統合を試みる。

**Rationale**: spec.md の Edge Case「延期後の再取得が完了する前に処理が再度中断した場合」
に対応する。git はディレクトリ配下の全ファイルが無くなれば自動的にそのパスを履歴から
除外する(空ディレクトリを保持しないため)ので、`rmtree` 後に空になった
`{Region}/{YYYY}/{MM}/{DD}/{Tournament}/` 階層を明示的に掃除するコードは不要。

**Alternatives considered**:
- *旧ディレクトリを即座に削除してから新ディレクトリを書き込む*: 新ディレクトリの取得が
  途中で失敗した場合、両方のデータを失う(旧: 削除済み、新: 不完全)。データを失わないと
  いう既存方針(Assumptions)に反するため却下。
- *旧ディレクトリを削除せず `superseded` フラグ等でマークするだけ*: 「重複が残る」ことに
  なり FR-001(重複を残さない)を満たさない。ファイルベースのフラグ管理は新しいスキーマ
  フィールドの追加を伴い、Constitution I(スキーマ変更は `docs/data_model.md` 更新+移行が
  必須)のコストに見合わない。

## 論点3: `attr.json` 欠落イベントの発見方法

**Decision**: `backfill_schema_version.py::iter_event_dirs()` の走査対象を
`events_root.rglob("attr.json")` から `events_root.rglob("standings.json")` に変更する。

**Rationale**: `download_standings()` はイベント取得パイプラインの最初にディスクへ書き込みを
行う関数であり(`fetch_with_page_fallback()` が成功した直後、`download_seeds`/
`download_all_set`/`write_event_attributes` より前)、ディレクトリが存在する限り
`standings.json` は例外なく存在する(実際に今回の欠落ケースでも存在していた)。これを起点に
することで、`attr.json` の有無に関わらず全ての「取得が試みられたイベントディレクトリ」を
発見できる。

**Alternatives considered**:
- *全ディレクトリを `rglob("*")` で列挙し、リーフディレクトリを判定する*: 走査コストが
  大きく、`matches.json` 等の中間ファイルとの区別ロジックが複雑になる。`standings.json` を
  起点にする方が既存の `REQUIRED_EVENT_FILES` の考え方(`attr.json`, `matches.json`,
  `standings.json`, `seeds.json` を必須集合として扱う)と一貫する。
- *`matches.json` を起点にする*: `download_all_set()` は `download_standings`/
  `download_seeds` より後に実行されるため、より早い段階(seeds取得失敗など)で処理が
  打ち切られたディレクトリを見逃す。より早く書かれる `standings.json` の方が網羅性が高い。

## 論点4: `attr.json` 欠落時の `event_id` 復元

**Decision**: `backfill_one_event()` は、対象ディレクトリに `attr.json` が存在しない(または
`event_id` を読み取れない)場合、`tournaments.jsonl` を読み込み、`events[].path` が対象
ディレクトリと一致するエントリを探して `event_id` を復元するフォールバックを追加する。
見つからない場合は例外を送出せず、「未解決」として呼び出し元に報告する。

**Rationale**: `tournaments.jsonl` は `attr.json` とは独立した記録であり、`download_all_tournaments()`
が正常に events_info を取得できていれば(= 取得処理が `attr.json` 書き込み手前で打ち切られた
場合でも)、通常は最初の1回で追記されている可能性がある。これを使えば追加のAPI呼び出しなしに
`event_id` を得られるケースが多い。それでも見つからない場合(何らかの理由で `tournaments.jsonl`
にも記録が無い)は、spec.md の Edge Case が定める通り「自動修復の対象外、人手確認が必要な
一覧として報告」する設計とする(処理全体を止めない)。

**Alternatives considered**:
- *ディレクトリ名(大会名・イベント名)から `fetch_latest_tournaments_by_game()` を検索し直す*:
  大会名の表記ゆれ・同名大会の存在により誤って別イベントに紐付けるリスクがあり、FR-008
  (event_idが異なるものを誤って重複統合しない)の精神に反する。`tournaments.jsonl` の
  構造化された記録を使う方が安全。

## 既存実装への影響確認

- `should_skip_tournament()` の呼び出し元は `download_all_tournaments()` のみ(1箇所)。
  シグネチャ変更の影響範囲は限定的。
- `iter_event_dirs()` の呼び出し元は `run_backfill()` のみ(1箇所)。戻り値の型(`list[Path]`)
  は変更しない。
- `write_event_attributes()` や `EVENT_DATA_VERSION` 等、`003-attr-end-at` で変更した箇所には
  触れない(本機能はディレクトリの決定・発見ロジックのみが対象)。
