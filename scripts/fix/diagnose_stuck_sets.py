import argparse
import json
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.fetch.download import fetch_set_ids_for_event  # noqa: E402
from scripts.queries import get_sets_by_ids_query  # noqa: E402
from scripts.utils import fetch_data_with_retries, set_api_parameters  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="指定したset_idについて、start.ggのレスポンス(dataとerrorsの両方、"
        "何も加工せず)をそのまま表示する読み取り専用の診断ツール。"
        "matches.jsonなど既存ファイルは一切変更しない。"
    )
    parser.add_argument("--url", default="https://api.start.gg/gql/alpha")
    parser.add_argument("--token", required=True)
    parser.add_argument("--set_ids", required=True, nargs="+", type=int)
    parser.add_argument(
        "--event_id",
        type=int,
        default=None,
        help="指定すると、start.ggから現在のイベントの全set_id一覧を取得し、"
        "--set_idsで指定したidが現在も存在するかどうかを表示する",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=5,
        help="1リクエストで問い合わせるset_id件数。本番のfetch_set_details_by_ids"
        "と全く同じクエリ形状を再現してキャッシュの影響を切り分けたい場合は25を指定する",
    )
    args = parser.parse_args()

    set_api_parameters(args.url, args.token)

    batch_size = args.batch_size
    for start in range(0, len(args.set_ids), batch_size):
        batch = args.set_ids[start:start + batch_size]
        query = get_sets_by_ids_query(batch)
        variables = {f"id{i}": set_id for i, set_id in enumerate(batch)}
        response_data = fetch_data_with_retries(query, variables)
        print(f"--- set_ids={batch} ---")
        print(json.dumps(response_data, ensure_ascii=False, indent=2))

    if args.event_id is not None:
        live_set_ids = fetch_set_ids_for_event(args.event_id)
        requested = set(args.set_ids)
        print(f"--- event {args.event_id}: 現在start.gg上に存在するset_id件数={len(live_set_ids)} ---")
        still_present = requested & set(live_set_ids)
        no_longer_present = requested - set(live_set_ids)
        print(f"指定したset_idのうち、現在も存在する: {sorted(still_present)}")
        print(f"指定したset_idのうち、現在は存在しない: {sorted(no_longer_present)}")


if __name__ == "__main__":
    main()
