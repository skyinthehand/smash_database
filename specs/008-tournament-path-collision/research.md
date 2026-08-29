# Research: 同日同名トーナメントの保存先パス衝突の解消

## Decision 1: 衝突検出の実装場所とコスト

**Decision**: `download_all_tournaments()`/`download_by_ids()`内、
`event_dir = get_event_directory(...)` を計算した直後(既存の
`load_excluded_event_ids()` チェックと同じ挿入点。`specs/007-exclude-events/`
参照)に、その`event_dir`文字列が、現在メモリ上に保持している
`tournaments`辞書内の**別のtournament_id**配下のいずれかのイベントの
`path`と一致するかどうかを調べる。

実装は、`tournaments`辞書から `path -> (tournament_id, event_id)` の
逆引き辞書(`build_path_index()`)を1回構築し、新しいイベントが登録される
たびに増分更新する。API呼び出しは一切発生しない(既にメモリ上にある
`tournaments.jsonl`の内容を照合するだけ)。

**Rationale**: この逆引き辞書1つだけで、衝突判定はO(1)のディクショナリ
参照になる。既存の`should_skip_tournament()`等と同様、`tournaments`辞書は
既にクロール開始時に`read_tournaments_jsonl()`で全件メモリに読み込まれて
いるため、追加のディスクI/O・API呼び出しは発生しない(SC-001の前提である
「衝突が無い通常時の挙動・コストを変えない」を満たす)。

**Alternatives considered**:
- 毎回`data/startgg/events`をディスク走査して衝突を確認する: 却下。
  クロール中に何百回も呼ばれる処理としては非常に高コスト。
- start.gg APIに「同名の別トーナメントが存在するか」を問い合わせる:
  却下。そのようなクエリは存在せず、そもそも衝突はローカルの保存先計算
  ロジック側の問題であり、API側の情報は不要。

## Decision 2: 参加者数が未確定な新規イベントの取り扱い(FR-003)

**Decision**: 衝突が検出された新規イベントについては、**参加者数の比較・
最終的な保存先の確定・`tournaments.jsonl`への登録を、standings取得
(`download_standings()`)が完了するまで遅延させる**。具体的には:

1. 衝突が検出された場合、既存コードにある「取得処理前の早期登録」
   (`update_event_registration()`の1回目の呼び出し)を**スキップ**する。
2. `download_standings()`は、衝突の有無に関わらずこれまで通り、計算上の
   (衝突しうる)`event_dir`へ実行する(standings.jsonの内容自体は
   どちらの当事者でも同一処理で問題なく書けるため)。
3. `download_standings()`の戻り値から新規イベントの参加者数
   (`len(user_data)`)が判明した時点で、衝突相手(既存に登録済みの方)の
   参加者数を、その`attr.json`の`num_entrants`フィールドから読み取り、
   比較する(Decision 3参照)。
4. 比較結果に基づき、必要であれば新規イベント側(または既存イベント側)の
   ディレクトリをその場でリネームしてから、`update_event_registration()`
   による本登録を行う。

**Rationale**: 参加者数(`num_entrants`)は、現状`download_standings()`が
返す`user_data`の件数からしか判明しない(start.ggの軽量な件数専用
フィールドを新たに調べる代わりに、既存の取得ステップの戻り値をそのまま
使う)。既にこのステップは通常のフロー内で必ず実行されるため、新たな
API呼び出しを追加せずに済む。一方で、standings.jsonの書き込み先
(衝突しうる`event_dir`)自体は先に確定させる必要があるため、「まず
とりあえず書いて、必要なら後でディレクトリごとリネームする」という
順序にする。ディレクトリのリネームは、既存の`cleanup_relocated_directory()`
と同様の「安全な移動」パターン(新しい配置が完全であることを確認して
から古い方を消す)を踏襲する。

**Alternatives considered**:
- standings取得**前**に、`event.standings`のpageInfoから件数だけを軽量に
  取得する専用クエリを新設する: 却下(今回は見送り)。実現できれば
  ディレクトリの仮置き・リネームが不要になり設計はより単純になるが、
  start.gg APIがそのような軽量フィールドを提供しているか未確認であり、
  新規クエリの追加はテスト時にAPIへの実アクセスが無いと検証できない
  (本セッション中に判明した`player.user`フィールドの件と同様のリスク)。
  将来的にAPI仕様が確認できれば、この代替案への切り替えを検討する
  価値はある。

## Decision 3: 参加者数の比較・命名調整ロジック

**Decision**: 新規モジュール関数
`resolve_path_collision(new_event_dir, new_num_entrants, existing_tournament_id, existing_event, tournaments)`
を`scripts/fetch/download.py`に追加する。

- 既存イベント側の参加者数は、`existing_event["path"]/attr.json`の
  `num_entrants`フィールドから読み取る(`attr.json`が無い/読めない場合は
  `0`扱いとし、新規イベント側を優先して既存側をリネームしない安全側に
  倒す)。
- 参加者数が多い方が「重複しない名前」を持たない(=そのまま)、少ない方
  が`disambiguate_event_name()`(Decision 4)で調整した名前を持つように
  する。
- 同数の場合は`tournament_id`が大きい方(=後発として扱う)を調整対象と
  する(Assumptions/Edge Cases参照。決定的で追加のAPI呼び出しを要しない
  基準)。
- 新規イベント側が調整対象になる場合: 計算済みの`new_event_dir`配下に
  既に書かれているstandings.jsonごと、ディレクトリを調整後の名前へ
  リネームする。
- 既存イベント側が調整対象になる場合(新規側の参加者数がより多い場合):
  既存イベントのディレクトリを調整後の名前へリネームし、既存イベントの
  `tournaments`辞書内のエントリ(`path`)を更新する。新規イベント側は、
  空いた「重複しない(調整前の)」パスをそのまま使う。
  **ただし、この既存側リネームは既存イベントが「初回の衝突」である場合
  にのみ行う(下記「初回衝突の判定」参照)。既存イベントが過去に一度
  でも衝突解決を経て確定(ロック)済みの場合は、参加者数の大小に関わらず
  既存側は一切変更せず、常に新規側のみを調整する(FR-005優先、spec.md
  Edge Cases)。**

**初回衝突の判定(`/speckit-analyze`指摘R1、2026-08-29の修正)**: 新たな
永続フィールドは追加しない(`data-model.md`「新規のデータファイルを追加
しない」方針を維持)。既存イベント側が「過去に一度でも衝突解決を経て
確定済みか」は、`tournaments`辞書内に、同じ地域・開催日・大会名・
イベント名の組み合わせに対して`disambiguate_event_name()`形式
(`{tournament_name}_({tournament_id})`)の`path`を持つ**他の**イベントが
既に存在するかどうかで判定する。そのようなエントリが存在する場合、それは
過去にこの大会名で衝突が発生し、片方が既に調整名で確定している(=もう
片方の無調整側は既にロック済みの勝者である)ことを意味する。存在しない
場合は、これが最初の衝突であり、通常通りFR-002/FR-004の参加者数比較を
適用する。

**Rationale**: この判定基準はFR-002/FR-004/FR-011で明記されている通り
「参加者数が多い方は変更しない」という単一のルールであり、User Story 4
の修復ツールでも全く同じ関数を再利用できる(FR-011)。既存イベント側の
参加者数を`tournaments.jsonl`ではなく`attr.json`から読む理由は、
`tournaments.jsonl`のスキーマ(`docs/data_model.md`)に参加者数が含まれて
いないため。「初回衝突の判定」を新規フィールドではなく既存データ
(調整名を持つ兄弟エントリの有無)から導出する設計にした理由は、
`data-model.md`が明記する「本フィーチャーは新しいデータファイルを追加
しない」という制約を維持しつつ、FR-005(一度確定した保存先は不変)と
FR-002(初回衝突時は参加者数比較)を両立させるため。

**Alternatives considered**:
- 常に「新規に見つかった方」を無条件でリネームする(参加者数を比較
  しない): 却下。FR-002がMUSTで要求する「参加者数が多い方は変更しない」
  という不変条件を満たせない。
- 「ロック済みかどうか」を`attr.json`等に新規フィールドとして永続化する:
  却下。`data-model.md`の「新しいデータファイルを追加しない」方針、および
  既存スキーマ(Constitution Principle I)への変更を避けるため。兄弟
  エントリの存在確認だけで同じ判定が既存データのみから導出できる。

## Decision 4: 「重複しない名前」の具体的な形式

**Decision**: 大会名の末尾に`tournament_id`を丸括弧で付加する形式とする。
例: `新京都DSW#34` が衝突した場合、調整後は `新京都DSW#34_(823456)`
(`get_event_directory()`の既存の文字列置換ルール—空白/スラッシュの置換—
を適用した後の形)。

**Rationale**: `tournament_id`は既にstart.gg上で一意かつ安定した識別子
であり、追加の採番管理(連番など)を持ち込む必要がない。連番方式
(`_2`, `_3`など)は、複数の衝突が異なる順序で処理された場合に結果が
一意に定まらない可能性があるが、`tournament_id`ベースなら常に決定的。

**Alternatives considered**:
- 連番サフィックス(`_2`など): 却下。処理順序に依存せず決定的な結果に
  するには、結局tournament_idのような安定した基準でソートする必要が
  あり、素直にtournament_idを直接使う方が単純。
- `event_id`を使う: 却下。1つの大会内に複数イベント(Singles/Doubles等)
  がある場合、`tournament_id`の方が「この大会全体が衝突の当事者である」
  ことを人間が読んで理解しやすい。

## Decision 5: User Story 3(監査ツール)の実装

**Decision**: 新規スクリプト `scripts/fix/find_path_collisions.py` を追加
する。`tournaments.jsonl`を読み込み、全イベントの`path`フィールドで
グルーピングし、同一`path`に異なる`tournament_id`が2件以上紐づいている
組み合わせを標準出力に一覧表示する(read-only、API呼び出し無し)。

**Rationale**: 既存の`scripts/fix/check_events_in_tournaments.py`等と
同様、`tournaments.jsonl`の内容だけで判定できる軽量なツールとして
自己完結させる。

## Decision 6: User Story 4(修復ツール)の実装

**Decision**: 新規スクリプト `scripts/fix/fix_path_collision.py` を追加
する。Decision 5のツールが出力した衝突(2つのevent_idの組)を引数に
取り、両者の現在の参加者数(`attr.json`)を提示した上で、`--yes`が
無ければ実行内容を表示するだけで終了する(既存の`redownload_event.py`の
`--dry-run`既定動作と同じパターン)。`--yes`指定時は、Decision 3の
`resolve_path_collision()`と同じ命名ルールで両者の最終的な保存先を決定
し、`redownload_event.py`が使っているのと同じ取得用の関数群
(`download_standings`/`download_seeds`/`download_all_set`/
`write_event_attributes`)を用いて、それぞれを個別に(決定した保存先へ)
再取得し、`tournaments.jsonl`を更新する。

**Rationale**: `redownload_event.py`本体は、通常の「1件のevent_idを
指定して再取得する」ツールとしての役割を保つ(Decision 7で追加する衝突
回避チェックはあくまで自分自身をずらすだけの単純なガードであり、
FR-002のような参加者数比較や、相手側を動かす判断は持たせない)。衝突
「修復」(2件を意図的に組で扱い、必要なら参加者数比較に基づき相手側も
動かしうる)は異なる責務であるため、既存ツールを拡張するのではなく、
新しい専用ツールとして分離する(scripts/fix/内の既存の1ツール=1責務と
いう設計方針を踏襲)。同じ低レベルの取得関数群を再利用することで、動作
の一貫性を保ちつつコードの重複を避ける。

## Decision 7: `redownload_event.py`自身の衝突回避(User Story 5、FR-012)

**Decision**: `redownload_event.py`の`redownload_event()`内、計算済みの
`event_dir`が確定した時点(既存ディレクトリの探索・削除より前)で、その
`event_dir`が実際にディスク上に存在し、かつその`attr.json`
(または`matches.json`等)が**指定されたevent_idとは異なる**event_idの
ものである場合、`disambiguate_event_name()`(Decision 4と共通)を使って
自分自身(指定されたevent_id)の保存先だけをずらす。相手側のディレクト
リ・`tournaments.jsonl`のエントリは一切変更しない。

判定は`tournaments.jsonl`のインデックス(Decision 1)ではなく、ディスク
上の実際のディレクトリを直接調べる方式にする
(`check_events_in_tournaments.py`の`read_attr()`と同様、対象ディレク
トリの`attr.json`を読んで`event_id`フィールドを比較する)。

**Rationale**: `redownload_event.py`は`tournaments.jsonl`全体を
インデックス化せずに単発で実行されるツールであり、通常のクロールと同じ
`tournaments`辞書ベースの仕組みをそのまま持ち込む必要はない。目的
(「ディレクトリを上書きしない」)を満たすだけなら、対象ディレクトリの
`attr.json`を直接確認する方が単純で、通常のクロールのフローに変更を
加えずに済む。同じevent_idへの繰り返し実行で結果が安定すること
(FR-012)は、Decision 4のtournament_idベースの決定的な命名により自然に
満たされる。

**Alternatives considered**:
- 通常のクロールと同じ参加者数比較ロジックを適用する: 却下(ユーザー
  からの明示的な指示)。1件のevent_idのみを対象とする個別ツールに、
  無関係な既存データ側を動かす判断まで持たせないため。

**Alternatives considered**:
- `redownload_event.py`に `--pair`のようなオプションを追加して拡張する:
  却下。単一event_id向けの既存インターフェースに、2件を組で扱う別物の
  概念を混在させると、既存の使い方(1件ずつの手動再取得)の見通しが
  悪くなる。
