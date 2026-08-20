# Feature Specification: 空イベントディレクトリの整理

**Feature Branch**: `005-tournament-event-sync`

**Created**: 2026-08-17

**Status**: Draft(User Story 1 は撤回、Clarifications 参照)

**Input**: User description: "event_idからではなくtournamentからズレが発生していないかをチェックすればいいのではないでしょうか。例えばbackfillでそれを行うなど。置き換わったという判断は不要です。matches.jsonとstandings.jsonが空の場合消して、新しいevent_idの取得さえ行われば最終的なデータは整理された状態になるのでそれでよいです。"

## User Scenarios & Testing *(mandatory)*

`004-fix-duplicate-events` の実データ検証中に、第7回チバスマ交流会(tournament_id=811466)で
新しいパターンの不整合が見つかった。当初「開催日が延期され、同じイベント(event_id)が
別ディレクトリに保存された」と考えていたが、調査の結果、実際には**延期のタイミングで
start.gg側のイベント自体が作り直されていた**(event_id が `1423946` → `1533881` に変化)。

この時点では「`004` の重複解消ロジックは event_id の一致を前提にしており、同一
tournament_id の下で event_id が作り直されるケースを検知できない」という仮説のもと、
トーナメント単位でのイベント一覧の差分検知(旧 User Story 1)を計画した。しかし
`scripts/fix/redownload_event.py --event-id 1533881` で直接取得・調査した結果、
`tournaments.jsonl` に新しく記録されたのは **tournament_id=811466 ではなく
tournament_id=867504** という、全く別のトーナメントレコードだった(start.gg側の
スラッグも `/tournament/7-58` → `/tournament/7-62` と別物になっていた)。つまり
実態は「同一トーナメント内でのイベント作り直し」ではなく、**主催者が別の新しい
トーナメントを作成していた**というものであり、当初の仮説は誤りだった。

さらに調査の結果、真の原因は `scripts/fetch/download.py` の
`download_all_tournaments()` / `download_by_ids()` が、`tournaments.jsonl` への
記録(event_id と保存先パスの対応関係)を、取得パイプライン全体(standings→seeds→
matches→attr.json)が成功した**後**にのみ行っていたことだった。2026年4月の取得時、
tournament_id=867504 は通常の新規トーナメント発見(`download_all_tournaments()`)で
正しく発見され、`standings.json`/`seeds.json`(4/10)・`matches.json`(4/25)は
書き込めていたが、`matches.json` 取得(大規模イベント処理)の失敗により
`write_event_attributes()` にも `tournaments.jsonl` への記録にも到達せず、
「このevent_idはこのパスに存在する」という最も基本的な対応関係すらどこにも
残らない状態になっていた。

この根本原因(記録タイミングの遅さ)は `004-fix-duplicate-events` の延長として
`download_all_tournaments()` / `download_by_ids()` を直接修正し、event_id と
保存先パスが判明した時点(取得処理を開始する前)で `tournaments.jsonl` に記録する
よう変更した(取得が途中で失敗しても記録が残るようにするための修正)。

この修正により、旧 User Story 1(トーナメント単位でのイベント一覧差分検知)が
前提としていた失敗モード自体が解消されたため、User Story 1 は**撤回**した
(詳細は Clarifications 参照)。本specは、event_id・tournament_idの作り直しとは
独立に元々必要だった **User Story 2(実データの無い空のイベントディレクトリの整理)**
のみを対象とする。

## Clarifications

### Session 2026-08-17

- Q: `tournaments.jsonl` 上の記録イベント数が0件になったトーナメント(User Story 2の削除により、唯一の記録イベントが無くなった場合)は、User Story 1の再チェック対象に含めるか？ → A: 含める(User Story 1 自体は後に撤回。詳細は次の項目)。
- Q(2026-08-18、実データ検証後): 第7回チバスマ交流会の実態を `redownload_event.py --event-id 1533881` で確認した結果、tournament_id が 811466 から 867504 に変わっていた(同一トーナメント内でのevent_id作り直しではなかった)。真の原因は `download_all_tournaments()`/`download_by_ids()` が `tournaments.jsonl` への記録を取得パイプライン完了後まで遅延させていたことだった。この根本原因を直接修正した結果、User Story 1(トーナメント単位でのイベント一覧差分検知)は不要と判断し撤回する。→ A: User Story 1 を仕様から削除し、User Story 2(空イベントディレクトリの整理)のみを本機能のスコープとする。
- Q(2026-08-18、`--apply` の実運用中): `standings.json`/`matches.json` がローカルで空という理由だけでディレクトリを削除したところ、start.gg上には実際にイベントが存在するもの(`187-7-23ver`)を誤って削除してしまった。「取得済み時点で`endAt`が過去だったなら、ローカルが空=本当に空」という当初の前提(Assumptions参照)が誤りだった。→ A: 削除前に必ず(1)同じevent_idの再取得、(2)同じトーナメント配下に未記録の別スマブラSPイベントが無いかの確認、の2段階を行う。どちらかで実データ・未記録イベントが見つかった場合、または確認自体ができなかった場合(APIエラー等)は削除しない。両方とも「確認できた上で空」の場合のみ削除する。

---

### User Story 1 - 実データの無い空のイベントディレクトリを整理する (Priority: P1)

データ利用者として、`standings.json` と `matches.json` がどちらも空(参加者・試合結果が
0件)のイベントディレクトリが、既存の段階的な自動処理の中で自動的に削除され、
データセットに残り続けないようにしたい。

**Why this priority**: 大会が実際には開催されなかった、あるいは取得時点でまだ参加者が
確定していなかった等の理由で実データを持たないイベントディレクトリは、放置すると
データセットに残り続ける。event_id・tournament_idが作り直されたかどうかとは無関係に、
実データの無い記録を整理する必要がある。

**Independent Test**: `standings.json` と `matches.json` がどちらも空のイベント
ディレクトリを用意し、整理処理を1回実行して、そのディレクトリが削除され、対応する
`tournaments.jsonl` の記録からも取り除かれることを確認する。

**Acceptance Scenarios**:

1. **Given** `standings.json` と `matches.json` がどちらも空(`data` 配列が0件)の
   イベントディレクトリ、**When** 整理処理が実行され、同じ event_id を再取得しても
   なお空で、かつ同じトーナメント配下に未記録の別イベントも無いことを確認できた、
   **Then** そのディレクトリは削除され、`tournaments.jsonl` の該当イベントの記録も
   削除される。
2. **Given** `standings.json` または `matches.json` のいずれかに1件以上のデータを
   持つイベントディレクトリ、**When** 整理処理が実行される、**Then** そのディレクトリは
   削除されない(実データは失われない)。
3. **Given** ローカルでは空だが、同じ event_id を再取得すると実データが見つかる
   イベントディレクトリ、**When** 整理処理が実行される、**Then** 削除せず、取得できた
   実データで上書き保存する。
4. **Given** ローカルでは空で、再取得後も空のままだが、同じトーナメント配下に
   `tournaments.jsonl` に未記録の別のスマブラSPイベントが見つかった、**When** 整理
   処理が実行される、**Then** そのディレクトリは削除しない。
5. **Given** 再取得や兄弟イベントの確認がAPIエラー等で行えなかった、**When** 整理
   処理が実行される、**Then** そのディレクトリは削除しない(判断がつかない場合は
   安全側に倒す)。

---

### Edge Cases

- トーナメント自体が本当に中止され、start.gg側のイベント一覧が完全に空になった場合は
  どうなるか？ → 同じevent_idの再取得後も空、かつ同トーナメント配下に他のイベントも
  無いことを確認できれば削除される。トーナメント自体の記録(`tournaments.jsonl` の
  該当エントリ)を削除するかどうかは本機能のスコープ外とする(イベントが0件になった
  場合の扱いは既存の `tournament_events_complete()` 等の挙動に委ねる)。
- 取得したばかりの新しいイベントがたまたま参加者0件だった場合はどうなるか？ →
  通常の取得結果としてそのまま保存される。次回以降の本機能の実行サイクルで、
  再取得・兄弟イベント確認の両方を経てなお空であれば整理対象になり得る。
- `standings.json`/`matches.json` は空だが `seeds.json` には値がある場合はどうなるか？
  → `seeds.json` の中身は削除判定に含めない(ユーザー指定通り、判定基準は
  `standings.json` と `matches.json` の2ファイルのみ)。ただし削除前の再取得・兄弟
  イベント確認は必ず行う。
- 兄弟イベントの確認に使う `fetch_event_ids_from_tournament()` が `events: null` を
  返す(実例: tournament_id=811466)場合はどうなるか？ → GraphQLの `errors` を伴わない
  場合(`NoEventsForGameError`)は「確認できた上で対象ゲームのイベントが0件」と判定し、
  削除候補として扱う。`errors` を伴う場合(通信エラー等、確認そのものができなかった
  場合)は通常の `FetchError` として扱い、削除しない。
- 兄弟イベントが見つかった場合、それを自動的に取得・保存するか？ → しない
  (旧User Story 1と同じ理由でスコープ外)。削除を保留するのみで、発見・取得は
  既存の `download_all_tournaments()` の通常サイクルに委ねる。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: システムは、既存のイベントディレクトリのうち、`standings.json` と
  `matches.json` の両方が空(データ0件)であるものを削除候補として検出できなければ
  ならない。
- **FR-002**: システムは、FR-001の削除候補を削除する前に、同じ event_id を
  start.gg から再取得しなければならない。再取得の結果実データが見つかった場合は
  削除せず、取得した実データで保存しなければならない。
- **FR-003**: システムは、FR-002で再取得後もなお空だった削除候補について、削除する
  前に、同じトーナメント配下に `tournaments.jsonl` に未記録の別のイベント(対象ゲーム)
  が存在しないかを確認しなければならない。未記録のイベントが見つかった場合、または
  確認自体ができなかった場合は削除してはならない。
- **FR-004**: システムは、FR-002・FR-003のいずれの確認でも「実データなし・未記録の
  イベントなし」と確認できた削除候補についてのみ削除し、対応する `tournaments.jsonl`
  の記録からも取り除かなければならない。
- **FR-005**: システムは、`standings.json` または `matches.json` のいずれかに1件以上の
  データを持つイベントディレクトリを、誤って削除してはならない。

### Key Entities *(include if feature involves data)*

- **空イベントディレクトリ**: `standings.json` と `matches.json` の両方が空の
  イベントディレクトリ。本機能の削除対象。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 参加者・試合結果がいずれも0件の既存イベントディレクトリは、既存の
  段階的な自動処理の実行サイクルの中で自動的に削除される。
- **SC-002**: 実データ(参加者または試合結果のいずれか)を持つイベントディレクトリが、
  本機能によって誤って削除されることはない。
- **SC-003**: 判断がつかない(再取得・兄弟イベント確認のいずれかがAPIエラー等で
  行えなかった)削除候補は、本機能によって削除されず、次回以降の実行サイクルに
  持ち越される(データを失うより保留する方が安全、という方針が守られている)。
  第7回チバスマ交流会の旧event_id(1423946、tournament_id=811466、実データ無し)は、
  兄弟イベント確認に使う `fetch_event_ids_from_tournament(811466, ...)` が
  `events: null`(GraphQLの`errors`を伴わない、`NoEventsForGameError`)を返すため、
  「対象ゲームのイベントが確認できた上で0件」と判定され、本機能の実行サイクルにより
  削除される。event_id=1533881・tournament_id=867504 側は、`004-fix-duplicate-events`
  の延長で行った記録タイミング修正と `redownload_event.py` による手動取得により、
  本specの対象に先立って解消済み。

## Assumptions

- 空判定の対象ファイルは `standings.json` と `matches.json` の2つに限定する
  (`seeds.json` や `attr.json` の中身は判定に使わない)。
- 空イベントディレクトリの削除は、必ず start.gg への再確認(同じevent_idの再取得+
  同トーナメント配下の兄弟イベント確認)を経てから行う。当初は「取得済み時点で
  `endAt` が過去である前提があるため再確認は不要」としていたが、実運用で
  `187-7-23ver` の誤削除が発生したため撤回した(Clarifications参照)。
- 兄弟イベントの確認で新しいイベントが見つかった場合、そのイベント自体を自動取得
  することはしない(削除を保留するのみ)。取得・保存は既存の
  `download_all_tournaments()` の通常サイクルに委ねる。
- トーナメント・イベントの新規発見(tournament_id の作り直しを含む)は既存の
  `download_all_tournaments()` に委ねる(本機能のスコープ外)。event_id と保存先
  パスの対応関係が取得失敗時にも記録され続けるようにする修正は、本specではなく
  `004-fix-duplicate-events` の延長として `scripts/fetch/download.py` に直接
  実装した。
