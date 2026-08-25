import os
import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from collections import Counter

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.queries import (
    get_event_sets_query, get_event_sets_light_query, get_standings_query, get_seeds_query,
    get_event_entrants_query,
    get_tournament_events_query, get_phase_groups_query, get_tournaments_by_game_query,
    get_tournament_by_id_query,
    get_phase_group_sets_query, get_phase_group_sets_light_query,
)
from scripts.utils import (
    country_code2region, get_date_parts, get_event_directory,
    read_users_jsonl, read_set, read_tournaments_jsonl,
    write_json, extend_jsonl, write_jsonl, read_json,
    set_indent_num, set_page_delay, get_page_delay,
    fetch_data_with_retries, fetch_all_nodes,
    set_retry_parameters, set_api_parameters,
    FetchError, NoEventsForGameError, NoPhaseError, AllFallbacksExhaustedError, MaxPagesExceededError,
    EVENT_DATA_VERSION,
)

REQUIRED_EVENT_FILES = ("attr.json", "matches.json", "standings.json", "seeds.json")
DEFAULT_MAX_RETRIES = 100
DEFAULT_RETRY_DELAY = 5
DEFAULT_PAGE_DELAY = 2
MATCHES_ONLY_MAX_RETRIES = 8
MATCHES_ONLY_RETRY_DELAY = 2
MATCHES_ONLY_PAGE_DELAY = 1
TOURNAMENTS_PER_PAGE = 100
STANDINGS_PER_PAGE = 200
SEEDS_PER_PAGE = 200
SETS_PER_PAGE = 50
LIGHTWEIGHT_SETS_PER_PAGE = 25
ENTRANTS_PER_PAGE = 200
STANDINGS_PER_PAGE_FALLBACKS = (200, 100, 50, 25, 10)
SEEDS_PER_PAGE_FALLBACKS = (200, 100, 50, 25, 10)
SETS_PER_PAGE_FALLBACKS = (50, 25, 10, 5, 3, 1)
LIGHTWEIGHT_SETS_PER_PAGE_FALLBACKS = (25, 10, 5, 2)
ENTRANTS_PER_PAGE_FALLBACKS = (200, 100, 50, 25, 10)
PHASE_GROUPS_PER_PAGE = 100
MAX_PHASE_GROUPS_FETCH_ITERATIONS = 50
EXCLUDED_PHASES_PATH = "data/startgg/excluded_phases.json"

def parse_date_or_datetime(value):
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"Invalid datetime '{value}'. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS."
    )


def configure_fetch_behavior(args):
    max_retries = args.max_retries
    retry_delay = args.retry_delay
    page_delay = DEFAULT_PAGE_DELAY

    if args.matches_only:
        if max_retries == DEFAULT_MAX_RETRIES:
            max_retries = MATCHES_ONLY_MAX_RETRIES
        if retry_delay == DEFAULT_RETRY_DELAY:
            retry_delay = MATCHES_ONLY_RETRY_DELAY
        page_delay = MATCHES_ONLY_PAGE_DELAY

    set_retry_parameters(max_retries, retry_delay)
    set_page_delay(page_delay)
    print(
        f"Fetch behavior: matches_only={args.matches_only} max_retries={max_retries} retry_delay={retry_delay}s page_delay={page_delay}s"
    )

def main():
    # コマンドライン引数の設定
    parser = argparse.ArgumentParser(description="Download tournament data from start.gg")
    parser.add_argument("--url", default="https://api.start.gg/gql/alpha", help="API URL")
    parser.add_argument("--token", required=True, help="API token")
    parser.add_argument(
        "--start_date",
        type=parse_date_or_datetime,
        default=None,
        help="Upper bound datetime for retrieval (inclusive). Format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS",
    )
    parser.add_argument(
        "--finish_date",
        type=parse_date_or_datetime,
        default=datetime(2018, 1, 1),
        help="Lower bound datetime for retrieval (inclusive). Format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS",
    )
    parser.add_argument("--max_retries", type=int, default=DEFAULT_MAX_RETRIES, help="Maximum number of retries for API requests")
    parser.add_argument("--retry_delay", type=int, default=DEFAULT_RETRY_DELAY, help="Delay between retries in seconds")
    parser.add_argument("--indent_num", type=int, default=2, help="Indentation level for JSON output")
    parser.add_argument("--startgg_dir", default="data/startgg/events", help="Directory to save event data")
    parser.add_argument("--done_file_path", default="data/startgg/done.csv", help="Path to the file recording completed downloads")
    parser.add_argument("--users_file_path", default="data/startgg/users.jsonl", help="Path to the file recording startgg user info")
    parser.add_argument("--tournament_file_path", default="data/startgg/tournaments.jsonl", help="Path to the file recording tournament info")
    parser.add_argument("--game_id", default="1386", help="Game ID for tournament retrieval. see https://developer.start.gg/docs/examples/queries/videogame-id-by-name/")
    parser.add_argument("--country_code", default="", help="Country code for tournament retrieval. e.g. JP")
    parser.add_argument(
        "--force_refresh",
        action="store_true",
        help="Re-download tournaments even when they are already marked done and event files exist.",
    )
    parser.add_argument(
        "--matches_only",
        action="store_true",
        help="Refresh only matches.json for existing event directories. Skip standings, seeds, attr, and user updates.",
    )
    parser.add_argument(
        "--max_pages",
        type=int,
        default=None,
        help="Skip events whose page count exceeds this value at the minimum per_page (10). Skipped events are logged with SKIP_LARGE_EVENT prefix.",
    )
    parser.add_argument(
        "--skip_report_path",
        default=None,
        help="Path to write a JSON report of skipped large events.",
    )
    parser.add_argument(
        "--tournament_ids",
        default=None,
        help="Comma-separated tournament IDs to fetch directly, bypassing date-range pagination.",
    )
    args = parser.parse_args()

    set_indent_num(args.indent_num)
    configure_fetch_behavior(args)
    set_api_parameters(args.url, args.token)

    if args.tournament_ids:
        tournament_id_list = [int(tid.strip()) for tid in args.tournament_ids.split(",") if tid.strip()]
        download_by_ids(
            tournament_id_list,
            args.game_id,
            args.country_code,
            args.startgg_dir,
            args.done_file_path,
            args.users_file_path,
            args.tournament_file_path,
        )
        return

    if args.start_date is not None and args.start_date < args.finish_date:
        raise ValueError("--start_date must be greater than or equal to --finish_date.")

    download_all_tournaments(
        args.game_id,
        args.country_code,
        args.start_date,
        args.finish_date,
        args.startgg_dir,
        args.done_file_path,
        args.users_file_path,
        args.tournament_file_path,
        force_refresh=args.force_refresh,
        matches_only=args.matches_only,
        max_pages=args.max_pages,
        skip_report_path=args.skip_report_path,
    )

def event_files_complete(event_dir):
    return all(os.path.exists(os.path.join(event_dir, name)) for name in REQUIRED_EVENT_FILES)

def tournament_events_complete(tournament_entry):
    events = tournament_entry.get("events", [])
    if not events:
        return False
    for event in events:
        event_dir = event.get("path")
        if not event_dir or not event_files_complete(event_dir):
            return False
    return True

def should_skip_tournament(tournament_id, tournaments, done_tournaments, force_refresh, current_date_parts=None):
    if force_refresh:
        return False
    if tournament_id not in done_tournaments:
        return False
    tournament_entry = tournaments.get(tournament_id)
    if not tournament_entry or not tournament_events_complete(tournament_entry):
        return False
    if current_date_parts is not None:
        year, month, day = current_date_parts
        date_segment = f"/{year}/{month}/{day}/"
        for event in tournament_entry.get("events", []):
            path = event.get("path") or ""
            if date_segment not in path:
                # 大会の開催日が延期された(記録済みパスの日付と現在の開催日が食い違う)。
                return False
    return True

def record_event_path(tournaments, tournament_id, event_id, event_name, event_dir, matches_only=False):
    """tournaments[tournament_id]["events"] を実体に合わせて更新する。

    既知の event_id が記録済みと異なるパスで再取得された場合(大会の延期等)、新しい
    ディレクトリの必須ファイル一式が揃っていることを確認できてから初めてパスを更新し、
    ディスク上に残る古いディレクトリを削除する(揃うまでは両方を残し、データを失わない)。

    戻り値: エントリの内容が変化した(呼び出し元が保存処理を行うべき)場合 True。
    """
    existing_events = tournaments[tournament_id]["events"]
    existing_entry = next((e for e in existing_events if e.get("event_id") == event_id), None)

    if existing_entry is None:
        if matches_only:
            return False
        existing_events.append({
            "event_id": event_id,
            "event_name": event_name,
            "path": event_dir,
        })
        return True

    old_path = existing_entry.get("path")
    if old_path == event_dir:
        return False
    if matches_only or not event_files_complete(event_dir):
        return False

    existing_entry["path"] = event_dir
    if old_path and os.path.isdir(old_path):
        shutil.rmtree(old_path)
        print(f"Removed stale directory after relocation: {old_path}")
    return True

def _record_skip(skipped_events, tournament_id, tournament_name, event_id, event_name, exc):
    record = {
        "tournament_id": tournament_id,
        "tournament_name": tournament_name,
        "event_id": event_id,
        "event_name": event_name,
        "total_pages": exc.total_pages,
        "max_pages": exc.max_pages,
        "per_page": exc.per_page,
    }
    skipped_events.append(record)
    print(
        f"SKIP_LARGE_EVENT tournament_id={tournament_id} name={tournament_name} "
        f"event_id={event_id} event_name={event_name} "
        f"total_pages={exc.total_pages} max_pages={exc.max_pages}"
    )


def download_all_tournaments(
    game_id,
    country_code,
    start_date,
    finish_date,
    startgg_dir,
    done_file_path,
    users_file_path,
    tournament_file_path,
    force_refresh=False,
    matches_only=False,
    max_pages=None,
    skip_report_path=None,
):
    done_tournaments = read_set(done_file_path, as_int=True)
    users = read_users_jsonl(users_file_path)
    tournaments = read_tournaments_jsonl(tournament_file_path)
    print(f"done_tournaments: {len(done_tournaments)}")
    print(f"users: {len(users)}")
    print(f"tournaments: {len(tournaments)}")
    rewrite_tournaments = False
    existing_tournament_ids = set(tournaments.keys())
    skipped_events = []

    page = 1
    reached_finish_date = False
    while True:
        try:
            tournaments_info, total_pages = fetch_latest_tournaments_by_game(game_id, country_code=country_code, limit=TOURNAMENTS_PER_PAGE, page=page)
        except FetchError as e:
            print(e)
            continue
        print(f"Progress: {page}/{total_pages}")
        if not tournaments_info:
            break

        for tournament in tournaments_info:
            try:
                tournament_id = tournament["id"]
                tournament_name = tournament["name"]
                timestamp = tournament["startAt"]
                end_timestamp = tournament["endAt"]

                _country_code = tournament["countryCode"]
                city = tournament["city"]
                lat = tournament["lat"]
                lng = tournament["lng"]
                venue_name = tournament["venueName"]
                timezone = tournament["timezone"]
                postal_code = tournament["postalCode"]
                venue_address = tournament["venueAddress"]
                maps_place_id = tournament["mapsPlaceId"]
                url = tournament["url"]
                place = {
                    "country_code": _country_code,
                    "city": city,
                    "lat": lat,
                    "lng": lng,
                    "venue_name": venue_name,
                    "timezone": timezone,
                    "postal_code": postal_code,
                    "venue_address": venue_address,
                    "maps_place_id": maps_place_id
                }

                now_timestamp = int(datetime.now().timestamp())
                if end_timestamp is None or end_timestamp > now_timestamp:
                    print(f"({tournament_name} {datetime.fromtimestamp(timestamp)}) is not finished yet.")
                    continue

                tournament_dt = datetime.fromtimestamp(timestamp)
                if start_date is not None and tournament_dt > start_date:
                    print(f"({tournament_name} {tournament_dt}) is newer than start_date. Skipping.")
                    continue

                year, month, day = get_date_parts(timestamp)
                if should_skip_tournament(
                    tournament_id, tournaments, done_tournaments, force_refresh,
                    current_date_parts=(year, month, day),
                ):
                        print(f"({tournament_name} {datetime.fromtimestamp(timestamp)}) already downloaded.")
                        continue
                if force_refresh and tournament_id in done_tournaments:
                    print(f"({tournament_name} {datetime.fromtimestamp(timestamp)}) force refresh enabled. Re-downloading.")
                elif tournament_id in done_tournaments:
                    print(f"({tournament_name} {datetime.fromtimestamp(timestamp)}) is marked done but files are missing. Re-downloading.")

                print(f"Download {tournament_name}, date: {tournament_dt}")

                if tournament_dt < finish_date:
                    print("!!!downloaded all!!!")
                    reached_finish_date = True
                    break

                if tournament_id in tournaments:
                    tournaments[tournament_id]["name"] = tournament_name
                    tournaments[tournament_id].setdefault("events", [])
                else:
                    tournaments[tournament_id] = {
                        "tournament_id": tournament_id,
                        "name": tournament_name,
                        "events": []
                    }
                events_info = fetch_event_ids_from_tournament(tournament_id, game_id)
                print(
                    f"Tournament {tournament_id}: fetched {len(events_info)} events for {tournament_name}."
                )

                for event_id, event_name, is_online, state, event_type in events_info:
                    print(
                        f"Tournament {tournament_id}: processing event {event_id} ({event_name}) matches_only={matches_only}."
                    )
                    event_dir = get_event_directory(startgg_dir, country_code, year, month, day, tournament_name, event_name)

                    # event_id とディレクトリの対応関係は、取得処理が始まる前の時点で
                    # 判明しているため、その後の取得(seeds/matches/attr.json)が途中で
                    # 失敗しても記録が残るよう、ここで先に記録しておく。
                    if record_event_path(tournaments, tournament_id, event_id, event_name, event_dir, matches_only=matches_only):
                        if tournament_id in existing_tournament_ids:
                            rewrite_tournaments = True

                    if matches_only:
                        if not os.path.isdir(event_dir):
                            print(
                                f"Skip matches-only refresh for {event_name}: existing event_dir not found ({event_dir})."
                            )
                            continue
                        entrant2user = fetch_entrant_user_map(event_id)
                        download_all_set(event_id, entrant2user, event_dir, lightweight=True)
                    else:
                        try:
                            user_data, player_data, entrant2user = download_standings(event_id, event_dir, max_pages=max_pages)
                        except MaxPagesExceededError as e:
                            _record_skip(skipped_events, tournament_id, tournament_name, event_id, event_name, e)
                            continue
                        num_entrants = len(user_data)
                        try:
                            download_seeds(event_id, user_data, player_data, entrant2user, event_dir, max_pages=max_pages)
                        except NoPhaseError:
                            print(f"No phase found for event {event_name}. Skipping.")
                            continue
                        except MaxPagesExceededError as e:
                            _record_skip(skipped_events, tournament_id, tournament_name, event_id, event_name, e)
                            continue
                        extend_user_info(user_data, player_data, users, users_file_path)
                        try:
                            download_all_set(event_id, entrant2user, event_dir, max_pages=max_pages)
                        except MaxPagesExceededError as e:
                            _record_skip(skipped_events, tournament_id, tournament_name, event_id, event_name, e)
                            continue
                        labels = {}
                        guest_entrant_count = count_guest_entrants(user_data)
                        write_event_attributes(num_entrants, event_id, event_name, tournament_name, timestamp, place, url, labels, is_online, event_dir, guest_entrant_count=guest_entrant_count, end_at=end_timestamp, state=state, event_type=event_type)
                    print(
                        f"Tournament {tournament_id}: finished event {event_id} ({event_name})."
                    )

                    if record_event_path(tournaments, tournament_id, event_id, event_name, event_dir, matches_only=matches_only):
                        if tournament_id in existing_tournament_ids:
                            rewrite_tournaments = True
                # ファイルを保存
                if len(tournaments[tournament_id]["events"]) > 0:
                    if rewrite_tournaments:
                        pass
                    else:
                        extend_tournament_info(tournaments[tournament_id], tournament_file_path)
                    if tournament_id not in done_tournaments:
                        done_tournaments.add(tournament_id)
                        write_done_tournaments(tournament_id, done_file_path)

            except FetchError as e:
                print(f"Tournament {tournament_id}: fetch failed, skipping. Error: {e}")
                continue

        if reached_finish_date:
            break

        if page >= total_pages:
            break
        page += 1

    if rewrite_tournaments:
        write_jsonl(list(tournaments.values()), tournament_file_path, with_version=True)

    if skipped_events:
        print(f"Skipped {len(skipped_events)} event(s) due to max_pages={max_pages}.")
        if skip_report_path:
            with open(skip_report_path, "w", encoding="utf-8") as f:
                json.dump(skipped_events, f, ensure_ascii=False, indent=2)
            print(f"Skip report written to {skip_report_path}")


# イベントのセットデータを保存する関数
def download_all_set(event_id, entrant2user, event_dir, lightweight=False, max_pages=None):
    all_sets = fetch_all_sets(event_id, lightweight=lightweight, max_pages=max_pages)
    if not all_sets:
        return

    os.makedirs(event_dir, exist_ok=True)
    write_matches(all_sets, entrant2user, event_dir)

def dedupe_set_nodes(all_sets, event_id=None):
    unique_sets = []
    seen_set_ids = set()
    duplicate_ids = []
    for node in all_sets:
        set_id = node.get("id")
        if set_id is None:
            unique_sets.append(node)
            continue
        if set_id in seen_set_ids:
            duplicate_ids.append(set_id)
            continue
        seen_set_ids.add(set_id)
        unique_sets.append(node)

    if duplicate_ids:
        prefix = f"Event {event_id}: " if event_id is not None else ""
        print(
            f"{prefix}skipped {len(duplicate_ids)} duplicate sets while normalizing fetched nodes."
        )
    return unique_sets

def load_excluded_phase_ids(path=EXCLUDED_PHASES_PATH):
    """data/startgg/excluded_phases.json を読み込み、event_id -> {phase_id, ...} を返す。
    ファイルが存在しない場合は空辞書を返す(通常運用ではこのファイルは無くても動く)。"""
    try:
        raw = read_json(path)
    except (FileNotFoundError, ValueError):
        return {}
    result = {}
    for event_id_str, entries in (raw or {}).items():
        phase_ids = {entry["phase_id"] for entry in entries if "phase_id" in entry}
        if phase_ids:
            result[int(event_id_str)] = phase_ids
    return result


def fetch_all_phase_groups(event_id):
    """イベント配下の全 phase / phaseGroup を列挙する。
    event.phases[].phaseGroups[] は phase ごとに個別にページングされるため、
    単一の nodes リストを前提とする fetch_all_nodes は使えず専用実装にしている。
    戻り値: (phase_id, phase_group_id, display_identifier) のタプルのリスト。"""
    collected = {}
    page = 1
    for _ in range(MAX_PHASE_GROUPS_FETCH_ITERATIONS):
        response_data = fetch_data_with_retries(
            get_phase_groups_query(),
            {"eventId": event_id, "page": page, "perPage": PHASE_GROUPS_PER_PAGE},
        )
        if "data" not in response_data or response_data["data"] is None or "event" not in response_data["data"]:
            raise FetchError(
                f"Error: 'data' or 'event' key not found in response for event {event_id}. "
                f"Response data: {response_data}\n in fetch_all_phase_groups"
            )
        event_data = response_data["data"]["event"]
        if event_data is None or event_data.get("phases") is None:
            raise FetchError(
                f"Error: no phases found for event {event_id} in fetch_all_phase_groups. "
                f"Response data: {response_data}"
            )

        any_more = False
        for phase in event_data["phases"]:
            phase_id = phase["id"]
            phase_groups = phase.get("phaseGroups") or {}
            for node in phase_groups.get("nodes") or []:
                phase_group_id = node.get("id")
                if phase_group_id is not None and phase_group_id not in collected:
                    collected[phase_group_id] = (phase_id, node.get("displayIdentifier"))
            total = (phase_groups.get("pageInfo") or {}).get("total")
            collected_for_phase = sum(1 for pid, _ in collected.values() if pid == phase_id)
            if total is not None and collected_for_phase < total:
                any_more = True

        if not any_more:
            return [
                (phase_id, phase_group_id, display_identifier)
                for phase_group_id, (phase_id, display_identifier) in collected.items()
            ]
        page += 1
        time.sleep(get_page_delay())

    raise FetchError(
        f"Event {event_id}: phase groups pagination did not converge after "
        f"{MAX_PHASE_GROUPS_FETCH_ITERATIONS} iterations in fetch_all_phase_groups."
    )


def _fetch_sets_with_fallback(query, variables, keys, fallback_values, default_page_size, event_id, max_pages=None):
    """per_page を縮めながら sets を取得し、重複set idが解消しない場合は API の
    pageInfo.total と重複除去後の件数を照合して、ページネーションの副作用による
    見かけ上の重複か本当のデータ欠落かを判定する。本当に欠落がある場合のみ FetchError。"""
    tried = []
    min_per_page = min(fallback_values)
    for per_page in fallback_values:
        tried.append(per_page)
        effective_max = max_pages if (max_pages is not None and per_page == min_per_page) else None
        page_info = {}
        try:
            all_sets = fetch_all_nodes(
                query, variables, keys, per_page=per_page, max_pages=effective_max, page_info_out=page_info
            )
        except MaxPagesExceededError:
            raise
        except FetchError as exc:
            message = str(exc).lower()
            if "query complexity is too high" not in message:
                raise
            print(
                f"Event {event_id}: sets query hit complexity limits with per_page={per_page}. Retrying with a smaller page size."
            )
            continue
        set_ids = [node.get("id") for node in all_sets if node.get("id") is not None]
        duplicate_ids = [set_id for set_id, count in Counter(set_ids).items() if count > 1]
        if not duplicate_ids:
            if per_page != default_page_size:
                print(
                    f"Event {event_id}: duplicate set ids disappeared after retrying with per_page={per_page}."
                )
            return dedupe_set_nodes(all_sets, event_id=event_id)

        deduped_sets = dedupe_set_nodes(all_sets, event_id=event_id)
        total = page_info.get("total")
        if total is not None and len(deduped_sets) >= total:
            print(
                f"Event {event_id}: {len(duplicate_ids)} duplicate set ids found with per_page={per_page}, "
                f"but deduplicated count ({len(deduped_sets)}) matches the API total ({total}). "
                "Treating as a pagination artifact and accepting the deduplicated result."
            )
            return deduped_sets

        print(
            f"Event {event_id}: detected {len(duplicate_ids)} duplicate set ids with per_page={per_page}. Retrying with a smaller page size."
        )

    raise FetchError(
        f"Duplicate set ids remained for event {event_id} after retries with per_page values {tried}."
    )


def _fetch_all_sets_by_phase_group(event_id, excluded_phase_ids, lightweight=False, max_pages=None):
    """event.sets の一括ページングでは解決できない(または既知に問題がある)イベントについて、
    phaseGroup ごとに sets を取得して集約する。excluded_phase_ids に含まれる phase 配下の
    phaseGroup は取得対象から除外する。"""
    phase_groups = fetch_all_phase_groups(event_id)

    included = [pg for pg in phase_groups if pg[0] not in excluded_phase_ids]
    excluded = [pg for pg in phase_groups if pg[0] in excluded_phase_ids]

    if excluded:
        excluded_desc = ", ".join(
            f"phase={phase_id} phaseGroup={phase_group_id}({display_identifier})"
            for phase_id, phase_group_id, display_identifier in excluded
        )
        print(f"Event {event_id}: excluding known-problematic phase groups from sets fetch: {excluded_desc}")

    if not included:
        raise FetchError(
            f"Event {event_id}: no phase groups remain after excluding {excluded_phase_ids}."
        )

    query = get_phase_group_sets_light_query() if lightweight else get_phase_group_sets_query()
    fallback_values = LIGHTWEIGHT_SETS_PER_PAGE_FALLBACKS if lightweight else SETS_PER_PAGE_FALLBACKS
    default_page_size = LIGHTWEIGHT_SETS_PER_PAGE if lightweight else SETS_PER_PAGE

    all_sets = []
    for phase_id, phase_group_id, display_identifier in included:
        group_sets = _fetch_sets_with_fallback(
            query,
            {"phaseGroupId": phase_group_id},
            ["phaseGroup", "sets"],
            fallback_values,
            default_page_size,
            event_id,
            max_pages=max_pages,
        )
        all_sets.extend(group_sets)

    return dedupe_set_nodes(all_sets, event_id=event_id)


def fetch_all_sets(event_id, lightweight=False, max_pages=None):
    excluded_phase_ids = load_excluded_phase_ids().get(event_id)
    if excluded_phase_ids:
        # 既知の問題イベントは event 単位の無駄な試行をせず直接 phaseGroup 単位で取得する。
        return _fetch_all_sets_by_phase_group(event_id, excluded_phase_ids, lightweight=lightweight, max_pages=max_pages)

    query = get_event_sets_light_query() if lightweight else get_event_sets_query()
    fallback_values = LIGHTWEIGHT_SETS_PER_PAGE_FALLBACKS if lightweight else SETS_PER_PAGE_FALLBACKS
    default_page_size = LIGHTWEIGHT_SETS_PER_PAGE if lightweight else SETS_PER_PAGE

    try:
        return _fetch_sets_with_fallback(
            query, {"eventId": event_id}, ["event", "sets"], fallback_values, default_page_size, event_id,
            max_pages=max_pages,
        )
    except FetchError as exc:
        if "duplicate set ids remained" not in str(exc).lower():
            raise
        print(
            f"Event {event_id}: event-level set pagination could not be reconciled; "
            "falling back to phaseGroup-scoped fetching."
        )
        return _fetch_all_sets_by_phase_group(event_id, set(), lightweight=lightweight, max_pages=max_pages)


def fetch_entrant_user_map(event_id):
    query = get_event_entrants_query()
    variables = {"eventId": event_id}
    keys = ["event", "entrants"]
    entrants = fetch_with_page_fallback(
        query,
        variables,
        keys,
        ENTRANTS_PER_PAGE_FALLBACKS,
        "entrants",
        event_id,
    )
    entrant2user = {}
    for entrant in entrants:
        participants = entrant.get("participants") or []
        if not participants:
            continue
        user = participants[0].get("user")
        if user is None:
            continue
        entrant_id = entrant.get("id")
        user_id = user.get("id")
        if entrant_id is not None and user_id is not None:
            entrant2user[entrant_id] = user_id
    return entrant2user


def fetch_with_page_fallback(query, variables, keys, per_page_values, label, event_id, max_pages=None):
    last_error = None
    per_page_list = list(per_page_values)
    min_per_page = min(per_page_list)
    for per_page in per_page_list:
        effective_max = max_pages if (max_pages is not None and per_page == min_per_page) else None
        try:
            return fetch_all_nodes(query, variables, keys, per_page=per_page, max_pages=effective_max)
        except MaxPagesExceededError:
            raise
        except FetchError as exc:
            last_error = exc
            message = str(exc).lower()
            if "query complexity is too high" not in message:
                raise
            print(
                f"Event {event_id}: {label} query hit complexity limits with per_page={per_page}. Retrying with a smaller page size."
            )
    raise AllFallbacksExhaustedError(
        f"Event {event_id}: {label} query failed at all page sizes {per_page_list}. Last error: {last_error}"
    ) from last_error

def build_match_dedupe_key(match_data):
    return (
        match_data.get("winner_id"),
        match_data.get("loser_id"),
        match_data.get("winner_score"),
        match_data.get("loser_score"),
        match_data.get("round_text"),
        match_data.get("round"),
        match_data.get("phase"),
        match_data.get("phase_order"),
        match_data.get("wave"),
        match_data.get("dq"),
        match_data.get("cancel"),
        match_data.get("state"),
    )

def write_matches(all_nodes, entrant2user, event_dir):
    """マッチデータを保存する関数"""
    json_data = {"data": []}
    seen_set_ids = set()
    seen_match_keys = set()
    for node in all_nodes:
        set_id = node.get("id")
        if set_id is not None:
            if set_id in seen_set_ids:
                continue
            seen_set_ids.add(set_id)
        slots = node.get('slots')
        if slots is None or len(slots) != 2:
            continue

        slot0 = slots[0]
        slot1 = slots[1]
        if slot0.get('entrant') is None or slot1.get('entrant') is None or slot0.get('standing') is None or slot1.get('standing') is None:
            continue
        
        # スコアがNoneの場合は0を設定
        score0 = slot0['standing']['stats']['score']['value'] if slot0['standing']['stats']['score']['value'] is not None else 0
        score1 = slot1['standing']['stats']['score']['value'] if slot1['standing']['stats']['score']['value'] is not None else 0
        
        winner_slot = slot0 if score0 > score1 else slot1
        loser_slot = slot1 if winner_slot == slot0 else slot0
        winner_score = score0 if winner_slot == slot0 else score1
        loser_score = score1 if winner_slot == slot0 else score0
        
        dq = (score0 < 0 or score1 < 0)
        cancel = score0 == 0 and score1 == 0
        
        games = node.get('games')
        details = [
                    {
                        "game_id": game.get('id'),
                        "order_num": game.get('orderNum'),
                        "winner_id": entrant2user[game['winnerId']] if game.get('winnerId') in entrant2user else None,
                        "entrant1_score": game.get('entrant1Score'),
                        "entrant2_score": game.get('entrant2Score'),
                        "stage": game['stage']['name'] if game.get('stage') else None,
                        "selections": [
                            {
                                "user_id": entrant2user[selection['entrant']['id']] if selection['entrant']['id'] in entrant2user else None,
                                "selection_id": selection['id'],
                                "character_id": selection['character']['id'],
                                "character_name": selection['character']['name']
                            }
                            for i, selection in enumerate(game.get('selections') or [])
                            if selection.get('entrant') is not None and selection.get('character') is not None
                        ]
                    }
                    for game in games
                ] if games is not None else []

        phase = None
        phase_order = None
        wave = None
        phase_group = node.get('phaseGroup')
        if phase_group is not None:
            phase = phase_group.get('displayIdentifier')
            phase_info = phase_group.get('phase')
            if phase_info is not None:
                phase_order = phase_info.get('phaseOrder')
            wave_info = phase_group.get('wave')
            if wave_info is not None:
                wave = wave_info.get('identifier')
        match_data = {
                "winner_id": entrant2user[winner_slot['entrant']['id']] if winner_slot['entrant']['id'] in entrant2user else None,
                "loser_id": entrant2user[loser_slot['entrant']['id']] if loser_slot['entrant']['id'] in entrant2user else None,
                "winner_score": winner_score,
                "loser_score": loser_score,
                "round_text": node.get('fullRoundText'),
                "round": node.get('round'),
                "phase": phase,
                "phase_order": phase_order,
                "wave": wave,
                "dq": dq,
                "cancel": cancel,
                "state": node.get('state'),
                "details": details
            }
        match_key = build_match_dedupe_key(match_data)
        if match_key in seen_match_keys:
            continue
        seen_match_keys.add(match_key)
        json_data["data"].append(match_data)
        
    write_json(json_data, f"{event_dir}/matches.json", with_version=True)

def count_guest_entrants(user_data):
    """user_data (download_standings が返す user 辞書のリスト) のうち、
    start.gg アカウントにリンクされていない(user が None の)エントラント数を返す。"""
    return sum(1 for user in user_data if user is None)


def write_event_attributes(num_entrants, event_id, event_name, tournament_name, timestamp, place, url, labels, is_online, event_dir, guest_entrant_count=None, end_at=None, state=None, event_type=None):
    json_data = {
        "event_id": event_id,
        "tournament_name": tournament_name,
        "event_name": event_name,
        "region": country_code2region(place["country_code"]),
        "place": place,
        "num_entrants": num_entrants,
        "offline": not is_online,
        "url": url,
        "labels": labels,
        # start.gg APIのevent.state(ACTIVE/COMPLETEDなど大会進行状況)とは別概念で、
        # このスクリプトによるデータ取得処理自体が完了したことを表すマーカー。
        # 以前は "status" という紛らわしい名前だったため archive_status に改名した。
        "archive_status": "completed",
        "state": state,
        "type": event_type,
        "timestamp": timestamp,
        "end_at": end_at,
        "fetched_at": int(datetime.now().timestamp()),
        "event_data_version": EVENT_DATA_VERSION,
        "guest_entrant_count": guest_entrant_count,
    }
    write_json(json_data, f"{event_dir}/attr.json", with_version=True)

def download_standings(event_id, event_dir, max_pages=None):
    """スタンディングデータを保存する関数"""
    standings_data = []
    user_data = []

    query = get_standings_query()
    variables = {"eventId": event_id}
    keys = ["event", "standings"]
    standings_data = fetch_with_page_fallback(
        query,
        variables,
        keys,
        STANDINGS_PER_PAGE_FALLBACKS,
        "standings",
        event_id,
        max_pages=max_pages,
    )

    user_data = []
    player_data = []
    entrant2user = {}
    for node in standings_data:
        if node['entrant']['participants'] is not None:
            user_data.append(node['entrant']['participants'][0]['user'])
            player_data.append(node['entrant']['participants'][0]['player'])
            if node['entrant']['participants'][0]['user'] is not None and node['entrant']['participants'][0]['player'] is not None:
                entrant2user[node['entrant']['id']] = node['entrant']['participants'][0]['user']['id']

    placements = [
        (node['placement'], entrant2user[node['entrant']['id']] if node['entrant']['id'] in entrant2user else None)
        for node in standings_data
        if node['entrant']['participants'] is not None
    ]
    placements.sort(key=lambda x: x[0])
    placements_dicts = [
        {"placement": placement, "user_id": user_id}
        for placement, user_id in placements
    ]
    
    os.makedirs(event_dir, exist_ok=True)
    json_data = {
        "data": placements_dicts
    }
    write_json(json_data, f"{event_dir}/standings.json", with_version=True)
    return user_data, player_data, entrant2user

def download_seeds(event_id, user_data, player_data, entrant2user, event_dir, max_pages=None):
    phase_id = fetch_phase_id(event_id)
    query = get_seeds_query()
    variables = {"phaseId": phase_id}
    keys = ["phase", "seeds"]
    seeds_data = fetch_with_page_fallback(
        query,
        variables,
        keys,
        SEEDS_PER_PAGE_FALLBACKS,
        "seeds",
        event_id,
        max_pages=max_pages,
    )

    for seed in seeds_data:
        if seed['entrant']['participants'] is not None:
            if seed['entrant']['id'] not in entrant2user:
                user_data.append(seed['entrant']['participants'][0]['user'])
                player_data.append(seed['entrant']['participants'][0]['player'])
                if seed['entrant']['participants'][0]['user'] is not None and seed['entrant']['participants'][0]['player'] is not None:
                    entrant2user[seed['entrant']['id']] = seed['entrant']['participants'][0]['user']['id']

    seeds_numbers = [(seed['seedNum'], entrant2user[seed['entrant']['id']] if seed['entrant']['id'] in entrant2user else None) for seed in seeds_data]
    seeds_numbers.sort(key=lambda x: x[0])
    seeds_dicts = [
        {"seed_num": seed_num, "user_id": user_id}
        for seed_num, user_id in seeds_numbers
    ]
    json_data = {
        "data": seeds_dicts
    }
    write_json(json_data, f"{event_dir}/seeds.json", with_version=True)

def extend_user_info(user_data, player_data, users, users_file_path):
    new_users = []
    
    for user, player in zip(user_data, player_data):
        if user is None or player is None:
            continue
        user_id = user['id']
        player_id = player['id']
        gamer_tag = player['gamerTag']
        prefix = player['prefix']
        gender_pronoun = user['genderPronoun'] if user['genderPronoun'] is not None else "unknown"
        startgg_discriminator = user.get('discriminator')
        x_id = None
        x_name = None
        discord_id = None
        discord_name = None
        if user['authorizations'] is not None:
            for authorization in user['authorizations']:
                if authorization['type'] == 'TWITTER':
                    x_id = authorization['externalId']
                    x_name = authorization['externalUsername']
                elif authorization['type'] == 'DISCORD':
                    discord_id = authorization['externalId']
                    discord_name = authorization['externalUsername']

        if user_id not in users:
            new_user = {
                "user_id": user_id,
                "player_id": player_id,
                "gamer_tag": gamer_tag,
                "prefix": prefix,
                "gender_pronoun": gender_pronoun,
                "startgg_discriminator": startgg_discriminator,
                "x_id": x_id,
                "x_name": x_name,
                "discord_id": discord_id,
                "discord_name": discord_name
            }
            users[user_id] = new_user
            new_users.append(new_user)

    extend_jsonl(new_users, users_file_path, with_version=True)

def extend_tournament_info(new_tournament_info, tournament_file_path):
    extend_jsonl([new_tournament_info], tournament_file_path, with_version=True)

# 特定のゲームのトーナメントを最新のものから取得する関数
def fetch_latest_tournaments_by_game(game_id, country_code, limit=5, page=1):
    response_data = fetch_data_with_retries(
        get_tournaments_by_game_query(country_code),
        {"gameId": game_id, "perPage": limit, "page": page},
    )
    if "data" not in response_data or response_data["data"] is None or "tournaments" not in response_data["data"] or response_data["data"]["tournaments"] is None:
        raise FetchError(f"Error: 'data' or 'tournament' key not found in response for game {game_id}. Response data: {response_data}\n in fetch_latest_tournaments_by_game")
        
    tournaments = response_data["data"]["tournaments"]["nodes"]
    total_pages = response_data["data"]["tournaments"]["pageInfo"]["totalPages"]
    return tournaments, total_pages

def fetch_event_ids_from_tournament(tournament_id, game_id):
    response_data = fetch_data_with_retries(
        get_tournament_events_query(),
        {"tournamentId": tournament_id, "gameId": game_id},
    )
    if "data" not in response_data or response_data["data"] is None or "tournament" not in response_data["data"] or response_data["data"]["tournament"] is None:
        raise FetchError(f"Error: 'data' or 'tournament' key not found in response for tournament {tournament_id}. Response data: {response_data}\n in fetch_event_ids_from_tournament")
    
    events = response_data["data"]["tournament"]["events"]
    if events is None:
        if response_data.get("errors"):
            # errors が付いている場合は解決に失敗した(=確認不能)ため、通常の FetchError とする。
            raise FetchError(
                f"Error: tournament {tournament_id} events field errored for game_id={game_id}. "
                f"Response data: {response_data}\n in fetch_event_ids_from_tournament"
            )
        # errors が無いのに events だけ null ということは、クエリ自体は正常に完了した上で
        # 対象ゲームに紐づくイベントが0件だったと判断できる(GraphQLの仕様上、フィールド
        # 解決エラーには通常 errors が伴うため)。「確認できなかった」のではなく
        # 「確認した結果0件だった」ことを表す専用の例外を送出する。
        raise NoEventsForGameError(
            f"Tournament {tournament_id} has no events for game_id={game_id} "
            f"(events is null in response, no GraphQL errors present). Response data: {response_data}\n in fetch_event_ids_from_tournament"
        )
    return [(event["id"], event["name"], event["isOnline"], event.get("state"), event.get("type")) for event in events]

def fetch_phase_id(event_id):
    page = 1
    per_page = 10
    while True:
        response_data = fetch_data_with_retries(
            get_phase_groups_query(),
            {"eventId": event_id, "page": page, "perPage": per_page}
        )
        if "data" not in response_data or "event" not in response_data["data"]:
            raise FetchError(f"Error: 'data' or 'event' key not found in response for event {event_id}. Response data: {response_data}\n in fetch_phase_id")
        event_data = response_data["data"]["event"]
        if event_data and event_data["phases"]:
            return event_data["phases"][0]["id"]
        else:
            raise NoPhaseError(f"Error: No phases found for event {event_id}. Response data: {response_data}\n in fetch_phase_id")

def write_done_tournaments(tournament_id, file_path):
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(f"{tournament_id}\n")
        f.flush()


def fetch_tournament_by_id(tournament_id):
    response_data = fetch_data_with_retries(
        get_tournament_by_id_query(),
        {"tournamentId": tournament_id},
    )
    if "data" not in response_data or response_data["data"] is None or "tournament" not in response_data["data"]:
        raise FetchError(
            f"Error: 'data' or 'tournament' key not found in response for tournament {tournament_id}. "
            f"Response data: {response_data}\n in fetch_tournament_by_id"
        )
    return response_data["data"]["tournament"]


def download_by_ids(
    tournament_id_list,
    game_id,
    country_code,
    startgg_dir,
    done_file_path,
    users_file_path,
    tournament_file_path,
):
    done_tournaments = read_set(done_file_path, as_int=True)
    users = read_users_jsonl(users_file_path)
    tournaments = read_tournaments_jsonl(tournament_file_path)
    print(f"download_by_ids: fetching {len(tournament_id_list)} tournament(s)")

    for tournament_id in tournament_id_list:
        try:
            tournament = fetch_tournament_by_id(tournament_id)
        except FetchError as e:
            print(f"Tournament {tournament_id}: failed to fetch metadata, skipping. Error: {e}")
            continue

        tournament_name = tournament["name"]
        timestamp = tournament["startAt"]
        end_timestamp = tournament["endAt"]
        _country_code = tournament["countryCode"] or country_code
        place = {
            "country_code": _country_code,
            "city": tournament["city"],
            "lat": tournament["lat"],
            "lng": tournament["lng"],
            "venue_name": tournament["venueName"],
            "timezone": tournament["timezone"],
            "postal_code": tournament["postalCode"],
            "venue_address": tournament["venueAddress"],
            "maps_place_id": tournament["mapsPlaceId"],
        }
        url = tournament["url"]

        print(f"Tournament {tournament_id}: {tournament_name}")

        if tournament_id in tournaments:
            tournaments[tournament_id]["name"] = tournament_name
            tournaments[tournament_id].setdefault("events", [])
        else:
            tournaments[tournament_id] = {
                "tournament_id": tournament_id,
                "name": tournament_name,
                "events": [],
            }

        try:
            events_info = fetch_event_ids_from_tournament(tournament_id, game_id)
        except FetchError as e:
            print(f"Tournament {tournament_id}: failed to fetch events, skipping. Error: {e}")
            continue

        print(f"Tournament {tournament_id}: fetched {len(events_info)} event(s).")

        for event_id, event_name, is_online, state, event_type in events_info:
            print(f"Tournament {tournament_id}: processing event {event_id} ({event_name}).")
            year, month, day = get_date_parts(timestamp)
            event_dir = get_event_directory(startgg_dir, _country_code, year, month, day, tournament_name, event_name)

            # event_id とディレクトリの対応関係は、取得処理が始まる前の時点で判明している
            # ため、その後の取得(seeds/matches/attr.json)が途中で失敗しても記録が残るよう、
            # ここで先に記録しておく。
            record_event_path(tournaments, tournament_id, event_id, event_name, event_dir)

            try:
                user_data, player_data, entrant2user = download_standings(event_id, event_dir)
            except FetchError as e:
                print(f"Tournament {tournament_id}: event {event_id} standings failed, skipping. Error: {e}")
                continue

            num_entrants = len(user_data)
            try:
                download_seeds(event_id, user_data, player_data, entrant2user, event_dir)
            except NoPhaseError:
                print(f"No phase found for event {event_name}. Skipping.")
                continue
            except FetchError as e:
                print(f"Tournament {tournament_id}: event {event_id} seeds failed, skipping. Error: {e}")
                continue

            extend_user_info(user_data, player_data, users, users_file_path)

            try:
                download_all_set(event_id, entrant2user, event_dir)
            except FetchError as e:
                print(f"Tournament {tournament_id}: event {event_id} sets failed, skipping. Error: {e}")
                continue

            labels = {}
            guest_entrant_count = count_guest_entrants(user_data)
            write_event_attributes(num_entrants, event_id, event_name, tournament_name, timestamp, place, url, labels, is_online, event_dir, guest_entrant_count=guest_entrant_count, end_at=end_timestamp, state=state, event_type=event_type)
            print(f"Tournament {tournament_id}: finished event {event_id} ({event_name}).")

            record_event_path(tournaments, tournament_id, event_id, event_name, event_dir)

        if tournaments[tournament_id]["events"]:
            extend_tournament_info(tournaments[tournament_id], tournament_file_path)
            if tournament_id not in done_tournaments:
                done_tournaments.add(tournament_id)
                write_done_tournaments(tournament_id, done_file_path)


if __name__ == "__main__":
    main()
