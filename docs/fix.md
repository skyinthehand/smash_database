# Fix / 不完全な点メモ

- `scripts/fetch/download_specific_event.py` は既存トーナメントにイベントを追加する際、`tournaments.jsonl` に反映されない（コメントにも記載あり）。
- `scripts/fetch/download_specific_event.py` の先頭コメントに「get_event_details_by_slug_query を追加する必要がある」とあるが、現状は `get_event_details_by_tournament_query` を使用しておりコメントが古い。
- `scripts/utils.py` の `fetch_data_with_retries()` は `variables` を `json.dumps()` して送信しているため、APIが変数をオブジェクトとして要求する場合に互換性の懸念がある。
- 一部の大規模イベントでは、`event.sets(sortType: STANDARD)` によるイベント単位のページネーションが安定せず、`per_page` をどれだけ縮めても重複/欠落が解消しないことがある(`scripts/fetch/download.py` の `fetch_all_sets` は、この場合 `pageInfo.total` との照合で解決しなければ自動的に phaseGroup 単位のページネーション(`_fetch_all_sets_by_phase_group`)へフォールバックする)。さらに、phaseGroup 単位でも解決できない=start.gg 側のデータそのものが壊れていると判明した phase は、`data/startgg/excluded_phases.json` に登録して取得対象から除外する。既知のケース: event_id=436192(第12回スマバトSP「予選あり1on1トーナメント」)の phase_id=731718。
