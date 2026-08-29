# Research: 取得対象からのイベント除外

`spec.md`のClarifications/Assumptionsで既に大半の設計判断が確定しているため、
本フェーズでは既存コードベースの調査結果として、その判断の妥当性を裏付ける。
NEEDS CLARIFICATIONは残っていない。

## Decision 1: 除外リストの保存形式・置き場所

**Decision**: `data/startgg/excluded_events.json`に、`{"<event_id>": {"excluded_at": "...", "reason": "..."}}`
という、event_id(文字列キー)をトップレベルのキーとするJSONオブジェクトとして保存する。

**Rationale**: 既存の`data/startgg/excluded_phases.json`(`scripts/fetch/download.py`)
が、`{"<event_id>": [{"phase_id": ..., "reason": "..."}]}`という、event_idを
キーとする単純なJSONオブジェクトで既に運用されている。本フィーチャーは
粒度がevent_id単位であり配下に複数エントリを持つ必要が無いため、値は
配列ではなく単一オブジェクト(`{"excluded_at": ..., "reason": ...}`)とする。
`load_excluded_phase_ids()`と同じtry/exceptパターン(ファイル未存在時は
空辞書)で読み込めるため、既存の実装パターンをそのまま再利用できる。

**Alternatives considered**:
- CSV: `docs/data_model.md`の管理ファイル節には`done.csv`のような単純な
  1行1IDのCSVも存在するが、除外理由に自由記述の日本語テキストを含める
  ため、カンマを含む理由文をエスケープする必要が生じCSVは不向き。
- JSONL(1行1エントリ): `tournaments.jsonl`/`users.jsonl`と同様の形式だが、
  「あるevent_idが除外されているか」を都度全行走査せずO(1)で判定したい
  ため、キーで直接引けるJSONオブジェクトの方が`excluded_phases.json`との
  一貫性も含め適切。

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

**Rationale**: いずれも`get_event_directory()`でパスを計算した直後という
共通の構造を持つため、同じ判定ロジック(`load_excluded_event_ids()`で
読み込んだ辞書にevent_idが含まれるか)を、各エントリポイントの先頭付近に
挿入するだけで済む。`excluded_phases.json`の`load_excluded_phase_ids()`が
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

**Decision**: `redownload_event.py`/`backfill_tournament_index.py`は、
除外されたevent_idをスキップした際、各ファイルの既存の`print(f"[{event_id}] ...")`
(`redownload_event.py`)/`print(f"[ADD] ...")`(`backfill_tournament_index.py`)
という接頭辞スタイルに倣い、それぞれ`print(f"[{event_id}] excluded: ...")`
/`print(f"[SKIP-EXCLUDED] ...")`のような1行を出力する。戻り値としては
「失敗」ではなく「除外によりスキップ」を呼び出し元が区別できるようにする。
