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

**実装時の訂正(2026-08-29)**: 上記2.の「計算上の(衝突しうる)`event_dir`
へ実行する」は、文字通り実装すると、その`event_dir`(衝突している=既に
既存イベントの完全なデータが置かれているディレクトリ)へ新規イベントの
`standings.json`を直接上書きしてしまい、比較結果が判明する前に既存データ
を破壊してしまう。実装では、衝突検出時点で新規イベント用の**暫定的な
(disambiguate_event_name()で調整済みの)ディレクトリ**を先に計算し、
`download_standings()`以降の全ての書き込みはこの暫定ディレクトリへ
行う。参加者数判明後、新規側が敗者ならこの暫定ディレクトリをそのまま
使い続け、新規側が勝者なら(a)既存側を暫定的な調整名ディレクトリへ退避
させ、(b)新規側のデータを暫定ディレクトリから本来の(衝突していた)
`event_dir`へ移動する、という2段階の入れ替えを行う(`resolve_path_collision()`
の実装、Decision 3参照)。

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
  `tournaments`辞書内のエントリ(`path`)を更新する(既に調整名を持って
  いた場合は、その調整名を解除して本来の名前に戻すのではなく、新規側が
  今度は「無調整の勝者」になり、旧勝者側が新たに調整名を持つ、という
  入れ替えになる)。

**「同一の取得処理内かどうか」の判定(ユーザーフィードバック2026-08-29に
よる修正、`/speckit-analyze`指摘R1からの再訂正)**: FR-005の恒久ロックは
「**別の**(過去に完了した)取得処理で既に確定・保存済みの保存先」にのみ
適用し、「同一の取得処理(1回のクロール実行、または1回の修復ツール実行)
の中でまだ処理が進行中の間」は、たとえ一度暫定的に調整が行われた後でも、
より参加者数の多い同日同名イベントが同じ処理の中でさらに検出されれば
再比較・入れ替えを行う(spec.md Edge Cases/FR-005/US2 Acceptance
Scenario 3・4)。

具体的には、`download_all_tournaments()`/`download_by_ids()`が
`read_tournaments_jsonl()`で`tournaments.jsonl`を読み込んだ直後(この
取得処理自身がまだ何も新規登録していない時点)に、その時点で
`tournaments`辞書に存在するtournament_idの集合を
`settled_tournament_ids`としてスナップショットする(新たな永続フィールド
は追加せず、実行中のみ保持するメモリ上の集合)。`resolve_path_collision()`
は衝突する既存側の`existing_tournament_id`がこの`settled_tournament_ids`
に含まれるかどうかで分岐する:

- 含まれる場合(=この取得処理が始まる**前から**確定済みだった、つまり
  別の過去の取得処理で決着済み): FR-005の恒久ロックを適用し、参加者数の
  大小に関わらず既存側は一切変更せず、常に新規側のみを調整する。
- 含まれない場合(=既存側もこの取得処理の中で新たに登録・調整された、
  まだ進行中のグループの一員): 通常通りFR-002/FR-004の参加者数比較を
  適用し、新規側の方が多ければ入れ替える(3件目・4件目が同じ処理内で
  現れても、同じ判定を繰り返し適用することで自然に「その処理内での
  最多」へ収束する)。

`scripts/fix/fix_path_collision.py`(User Story 4、Decision 6参照)は、
コマンドラインで明示的に指定された対象event_id群を、たとえ全件が
ディスク上の`tournaments.jsonl`から読み込まれたものであっても、
互いに対しては`settled_tournament_ids`に**含めない**(=指定された対象
同士は常に「同一の取得処理内」として扱い、比較・入れ替えの対象とする)。
指定対象以外の(無関係な)既存エントリは通常通り`settled_tournament_ids`
に含める。

**Rationale**: この判定基準はFR-002/FR-004/FR-011で明記されている通り
「参加者数が多い方は変更しない」という単一のルールであり、User Story 4
の修復ツールでも全く同じ関数を再利用できる(FR-011)。既存イベント側の
参加者数を`tournaments.jsonl`ではなく`attr.json`から読む理由は、
`tournaments.jsonl`のスキーマ(`docs/data_model.md`)に参加者数が含まれて
いないため。「同一の取得処理内かどうか」を新規の永続フィールドではなく
実行時のみのスナップショット(`settled_tournament_ids`)から導出する
設計にした理由は、`data-model.md`が明記する「本フィーチャーは新しい
データファイルを追加しない」という制約を維持しつつ、FR-005(取得処理を
またいだ確定は不変)とEdge Cases(同一取得処理内では3件以上でも最多を
維持)を両立させるため。

**Alternatives considered**:
- 常に「新規に見つかった方」を無条件でリネームする(参加者数を比較
  しない): 却下。FR-002がMUSTで要求する「参加者数が多い方は変更しない」
  という不変条件を満たせない。
- 「ロック済みかどうか」を`attr.json`等に新規フィールドとして永続化する:
  却下。`data-model.md`の「新しいデータファイルを追加しない」方針、および
  既存スキーマ(Constitution Principle I)への変更を避けるため。実行時
  スナップショットだけで同じ判定が既存データのみから導出できる。
- 「調整名を持つ兄弟エントリの有無」でロック済みかどうかを判定する
  (`/speckit-analyze`指摘R1時点の設計): 却下。同一の取得処理内で3件目
  以降が現れた場合、直前の暫定調整によって既に兄弟エントリが存在して
  しまうため、「最初の2件しか比較されない」問題を再現してしまう
  (ユーザーフィードバック2026-08-29で指摘)。取得処理の開始時点の
  スナップショットで判定することで、同一処理内では常に再比較できる
  ようにした。

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
する。Decision 5のツールが出力した衝突に属する2件**以上**のevent_id
(`--event-id <id1> <id2> [<id3> ...]`)を引数に取り、全員の現在の参加者数
(`attr.json`)を提示した上で、`--yes`が無ければ実行内容を表示するだけで
終了する(既存の`redownload_event.py`の`--dry-run`既定動作と同じ
パターン)。`--yes`指定時は、Decision 3の`resolve_path_collision()`と
同じ命名ルール・同じ`settled_tournament_ids`の仕組みで最終的な保存先を
決定する。ただし、コマンドラインで明示的に指定された対象event_id群は
互いに対して`settled_tournament_ids`に含めない(=指定された全員を
「同一の取得処理内」として扱い、3件以上でも参加者数が最多の1件だけが
元の名前を維持するよう、まとめて比較・入れ替えの対象とする。Decision 3
参照)。対象データは全て既にディスク上に存在するため、start.gg への
再取得は行わない(実装時の判断。当初は`redownload_event.py`と同じ
取得用の関数群を再利用する想定だったが、既存ディレクトリの移動だけで
十分であり、無駄なAPI呼び出しを避けられる。憲法Principle V)。各対象の
`attr.json`(`place.country_code`/`timestamp`/`tournament_name`/
`event_name`)から本来の(衝突していない)保存先を再計算し、既存
ディレクトリをそこへ移動した上で`tournaments.jsonl`を更新する。

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
