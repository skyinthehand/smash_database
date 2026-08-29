# Research: 取得対象からのイベント除外

`spec.md`のClarifications/Assumptionsで既に大半の設計判断が確定しているため、
本フェーズでは既存コードベースの調査結果として、その判断の妥当性を裏付ける。
NEEDS CLARIFICATIONは残っていない。

## Decision 1: 除外リストの保存形式・置き場所

**Decision**: 既存の`data/startgg/excluded_phases.json`を
`data/startgg/excluded_events.json`へリネームし、event単位・phase単位
両方の除外を1ファイルで扱えるよう拡張する。両者は専用の`type`
フィールドではなく、event_id配下の**値の形**で区別する:

- 値が**配列**(`[{"phase_id": ..., "reason": ...}]`): 従来通り、
  特定phaseのみの除外(挙動は完全に不変)。
- 値が**オブジェクトかつ`reason`を直下に持つ**
  (`{"reason": ...}`): イベント全体の除外(新規)。除外日時は持たない
  (git履歴で表現するため。下記参照)。

```json
{
  "436192": [
    {"phase_id": 731718, "reason": "start.gg側のデータ不整合により..."}
  ],
  "1359150": {
    "reason": "テスト運用のみの重複イベント(壁スマ#2 ggテスト運用と同一)"
  }
}
```

**Rationale**: ユーザーからの明示的な指示(2026-08-29のセッション)。
別ファイルに分割する案(当初のspec.md初版の設計)よりも、「除外設定は
1箇所を見ればよい」という点で運用上の見通しが良い。`type`フィールドを
追加しない理由: 値の型(配列 or オブジェクト)自体が既に判別に十分な
情報を持っており、冗長なフィールドを追加すると「`type`と実際の値の形が
食い違う」という新しい不整合の可能性を生むだけになる。既存の配列形状
エントリは無変換のまま新形式として通用するため、移行スクリプトは不要
(ファイル名の変更のみ`git mv`で行う)。

**Alternatives considered**:
- 別ファイル(`excluded_events.json`を新規追加し、`excluded_phases.json`
  はそのまま): 当初案。却下(ユーザー指示により1ファイルへ統合)。
  除外設定が2ファイルに分散すると、「このイベントは除外されているか」を
  確認する際に2ファイルを見る必要が生じる。
- 明示的な`type`フィールド(`{"type": "event", ...}` /
  `{"type": "phases", "phases": [...]}`): 却下。値の形(配列/オブジェクト)
  だけで曖昧さなく判別できるため、冗長。
- CSV: 除外理由に自由記述の日本語テキストを含めるため、カンマを含む
  理由文のエスケープが必要になりCSVは不向き。
- JSONL(1行1エントリ): 「あるevent_idが除外されているか」をO(1)で
  判定したいため、キーで直接引けるJSONオブジェクトの方が適切。

**関連する既存コードの変更点**: `load_excluded_phase_ids()`は、
統合後のファイルに新たに登場する「オブジェクト形状(イベント全体除外)」
のエントリを、従来の`entry["phase_id"]`前提の内包表記でそのまま処理
すると壊れる(オブジェクトは`entry`としてイテレートできない)。
配列形状のエントリのみを対象にするよう、`isinstance(entries, list)`
のガードを追加する(オブジェクト形状のエントリは黙ってスキップする
= 従来の「phase単位の除外は無い」という判定と同じ結果になる)。
`EXCLUDED_PHASES_PATH`定数も`EXCLUDED_EVENTS_PATH`へリネームする。

## Decision 1a: 除外日時フィールドは持たせない

**Decision**: Excluded Event Entryのオブジェクトは`reason`のみを持ち、
`excluded_at`のような日付フィールドは持たせない。

**Rationale**: ユーザーからの明示的な指示(2026-08-29のセッション)。
除外リストファイル自体がgit管理されているため、「いつそのエントリが
追加/変更されたか」は当該ファイルへの`git log`/`git blame`で確実に
確認でき、ファイル内に同じ情報を重複して持たせる必要がない(除外解除の
扱い方を決めたDecision含意=クリアリング済みのClarifications参照、と
同じ「状態はgit履歴に委ね、ファイル自体はできる限り単純に保つ」という
一貫した方針)。

**Alternatives considered**:
- `excluded_at`フィールドを持たせる(当初案): 却下。git履歴と二重に
  日時情報を管理することになり、手動編集時に日付を書き忘れる/古い日付を
  コピペしてしまう等の不整合の温床になる。

## Decision 2: 除外チェックを組み込む箇所

**Decision**: 以下の関数の、イベントディレクトリパスを計算した直後
(実際のディレクトリ作成・`tournaments.jsonl`登録より前)に、除外チェックを
挿入する。
- `scripts/fetch/download.py`の`download_all_tournaments()`(通常の
  定期クロール、`event_dir = get_event_directory(...)`の直後)
- `scripts/fetch/download.py`の`download_by_ids()`(同様のクロールを
  tournament_id直接指定で行う経路)
- `scripts/fix/redownload_event.py`の`redownload_event()`(個別イベントの
  手動再取得、既存ディレクトリ探索の直後)
- `scripts/fix/backfill_tournament_index.py`の`scan_and_fill()`
  (`tournaments.jsonl`の抜け補完、`os.path.isdir(event_dir)`チェックの
  近く)
- `scripts/fix/check_events_in_tournaments.py`の`main()`(attr.json
  ベースの`tournaments.jsonl`抜け補完、`event_id = attr.get("event_id")`
  で event_id が判明した直後。`/speckit-analyze`指摘により追加:
  このツールを対象外のままにすると、除外後もディレクトリが残存する
  既存イベントが誤って`tournaments.jsonl`へ再登録されうる)
- `scripts/fix/fix_missing_tournaments.py`の`clean_tournaments()`
  (`tournaments.jsonl`のエントリ検証・削除、`event.get("event_id")`
  取得直後・`check_event()`呼び出しの前。除外対象のevent_idは検証・
  削除判定の対象から外し、既存のエントリがあればそのまま残す)

**Rationale**: いずれも`get_event_directory()`でパスを計算した直後、
または`event_id`が判明した直後という共通の構造を持つため、同じ判定
ロジック(`load_excluded_event_ids()`で読み込んだ辞書にevent_idが
含まれるか)を、各エントリポイントの先頭付近に挿入するだけで済む。
`excluded_phases.json`の`load_excluded_phase_ids()`が
`fetch_set_ids_for_event()`/`fetch_all_sets()`の内部で個別に呼ばれている
のと同じ「呼び出し側が明示的にチェックする」スタイルを踏襲する(共通の
デコレータやミドルウェアは導入しない)。

**Alternatives considered**:
- `get_event_directory()`自体の内部で除外チェックを行い例外を投げる:
  却下。`get_event_directory()`は純粋なパス計算関数であり、副作用
  (例外送出によるフロー制御)を持ち込むと、除外と無関係な呼び出し元
  (パス文字列の比較のみを行うツール等)にも影響が及ぶ。

## Decision 3: ログ出力の形式(FR-004a)

**Decision**: `download_all_tournaments()`内の他のスキップ理由と同じ
`print(f"...")`形式で、`"Tournament {tournament_id}: event {event_id} is excluded. Skipping."`
相当の1行を出力する。

**Rationale**: 同関数には既に`"({tournament_name} ...) already downloaded."`
のような同種のprint文が複数存在し、専用のロギングフレームワークは
使われていない。既存パターンとの一貫性を優先する。

**Alternatives considered**: 構造化ロギング(`logging`モジュール)の導入は、
本フィーチャー単体のスコープを超える既存コードベース全体の変更となる
ため見送る。

## Decision 4: 個別ツール側での報告方法(FR-006)

**Decision**: 対象4ツールは、除外されたevent_idをスキップした際、
各ファイルの既存の接頭辞スタイルに倣って1行報告する:
- `redownload_event.py`: 既存の`print(f"[{event_id}] ...")`に倣い
  `print(f"[{event_id}] excluded: ...")`。
- `backfill_tournament_index.py`: 既存の`print(f"[ADD] ...")`に倣い
  `print(f"[SKIP-EXCLUDED] ...")`。
- `check_events_in_tournaments.py`: 既存の`print(f"[SKIP] ...")`に倣い
  `print(f"[SKIP-EXCLUDED] {event_dir}: ...")`。
- `fix_missing_tournaments.py`: 既存の`report_lines.append(f"[OK] ...")`/
  `f"[REMOVE] ...")`に倣い、`report_lines.append(f"[EXCLUDED] ...")`。

戻り値としては「失敗」ではなく「除外によりスキップ」を呼び出し元が
区別できるようにする。
