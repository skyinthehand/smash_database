# Fix / 不完全な点メモ

- `scripts/fetch/download_specific_event.py` は既存トーナメントにイベントを追加する際、`tournaments.jsonl` に反映されない（コメントにも記載あり）。
- `scripts/fetch/download_specific_event.py` は `scripts/fetch/download.py` とは
  独立に、`fetch_all_sets`/`download_all_set`/`write_matches`/`write_event_attributes`
  を自前で再実装しており、`006-incremental-set-fetch`（一括優先・失敗時のみ
  逐次(set単位)取得へフォールバックする方式、`set_id`の付与、`attr.json`の
  完了ゲーティング）を導入していない。単一イベントを手動で個別取得するための
  補助スクリプトであり、`download.py`のメインパイプライン（週次gap-check等）
  ほど大規模イベントを継続的に扱う想定ではないため、今回は意図的にスコープ外
  とした。将来この経路で大規模イベントの取得漏れが問題になった場合は、
  `download.py`側の実装を再利用する形にリファクタリングすることを検討する。
- `scripts/fetch/download_specific_event.py` の先頭コメントに「get_event_details_by_slug_query を追加する必要がある」とあるが、現状は `get_event_details_by_tournament_query` を使用しておりコメントが古い。
- `scripts/utils.py` の `fetch_data_with_retries()` は `variables` を `json.dumps()` して送信しているため、APIが変数をオブジェクトとして要求する場合に互換性の懸念がある。
- 一部の大規模イベントでは、`event.sets(sortType: STANDARD)` によるイベント単位のページネーションが安定せず、`per_page` をどれだけ縮めても重複/欠落が解消しないことがある(`scripts/fetch/download.py` の `fetch_all_sets` は、この場合 `pageInfo.total` との照合で解決しなければ自動的に phaseGroup 単位のページネーション(`_fetch_all_sets_by_phase_group`)へフォールバックする)。さらに、phaseGroup 単位でも解決できない=start.gg 側のデータそのものが壊れていると判明した phase は、`data/startgg/excluded_phases.json` に登録して取得対象から除外する。既知のケース: event_id=436192(第12回スマバトSP「予選あり1on1トーナメント」)の phase_id=731718。
- 大会の開催日が延期された場合、`scripts/fetch/download.py` の `record_event_path()` は `tournaments.jsonl` に記録されている**1件の旧パス**とのみ比較して重複ディレクトリを解消する(新ディレクトリの必須ファイルが揃うまでは旧ディレクトリを残す)。このため、同じ大会が2回以上延期され、かつ `tournaments.jsonl` の更新が行われないまま(修正前のバグにより)3件以上のディレクトリが既に発生してしまっているケースでは、`tournaments.jsonl` からも参照されていない「中間の」ディレクトリまでは自動検出・削除できない。既知のケース: `走利夜-SO-RYA_#2`、`L.S.C.T〜Love_Smash_Champion_Tournament〜`(いずれも Japan リージョン、3件のディレクトリが重複)。これらは人手での確認・統合が必要。
- 第7回チバスマ交流会(event_id=1423946, tournament_id=811466)の重複は、上記の `record_event_path()` の延期検知では解消されなかった。実態は「延期」ではなく、start.gg側で**別のtournament_id(867504)として作り直されていた**ためで、`fetch_event_ids_from_tournament(811466, game_id)` は今も `events: null`(GraphQLの`errors`を伴わない)を返す。`scripts/fix/prune_empty_events.py` はこれを `NoEventsForGameError` として扱い、「確認できた上でtournament_id=811466にはスマブラSPのイベントが0件」と判定して、対応する空ディレクトリ(event_id=1423946)を削除対象にする(`errors`を伴うレスポンスは通常の`FetchError`として区別し、その場合は削除しない)。event_id=1533881(tournament_id=867504)側は `scripts/fix/redownload_event.py --event-id 1533881 --yes` で手動取得済み。
- （逐次取得モード／`event_data_version>=6`）一括sets取得が失敗したイベントは、
  `fetch_set_ids_for_event()`によるID専用の軽量クエリでset一覧を取得してから
  `matches.json`にプレースホルダーを投入する。このID専用クエリ自体は、既存の
  `max_pages`ベースの安全網（large-event-skip issue自動作成／`fetch_large_event`
  手動ワークフロー）が廃止されたことに伴い、専用の手動escape hatchを持たない。
  理論上、病的に巨大なイベントでこのID一覧取得自体が完走できない場合、そのイベントは
  他のイベントと同様に逐次取得と繰り返しのスケジュール実行に委ねて収束を待つのみと
  なる。2026年時点で観測された最大級のイベント（488人／1267ページ相当）では
  問題無く完走する見込みだが、これを大幅に超える規模のイベントが今後出現した場合は
  改めて対応を検討する。
- `scripts/fix/validate_data.py`は`events_root.rglob("attr.json")`でイベント
  ディレクトリを発見するため、逐次取得モードで取得中(`attr.json`未生成)のイベントは
  そもそも検証対象にならず、プレースホルダー混在の`matches.json`から誤検知エラーが
  出ることは無い(設計上の意図的な性質。詳細は
  `specs/006-incremental-set-fetch/research.md` §7)。「`attr.json`が存在する
  イベントについて`matches.json`にプレースホルダーが1件も無いこと」を
  `validate_data.py`側でも追加でassertする案を検討したが、上記の理由により
  現状のコードは既にこの不変条件を破り得ないため、今回は見送った(意図的な
  スコープ外判断であり、検討漏れではない)。将来、仮に`attr.json`が時期尚早に
  書き込まれるバグが混入した場合の防御的チェックとして追加する価値はある。
