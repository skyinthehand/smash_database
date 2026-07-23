#!/usr/bin/env python3
"""
resolve_merge_conflicts.py

git merge 中に発生した競合ファイルを、重複排除ルールに従ってワーキングツリーに書き出す。

【重要】このスクリプトは git add を一切行わない。
        解消結果を確認してから、手動で git add → git merge --continue すること。

対象ファイル:
  - data/startgg/done.csv         … ID（数値）の一覧。IDベースで重複削除。
  - data/startgg/tournaments.jsonl … tournament_id をキーとした JSONL。IDベースで重複削除。
  - data/startgg/users.jsonl       … user_id をキーとした JSONL。IDベースで重複削除。
  - docs/chore-tornament/checked_dates.json … 日付をキーとした JSON。日付ベースで重複削除。
  - docs/chore-tornament/README.md          … Markdown テーブル。日付ベースで重複削除。

重複時の優先ルール:
  - CSV / JSONL  : ours（stage 2 = 現ブランチ）優先。theirs（stage 3 = origin/main）は新規IDのみ追加。
  - JSON / README: checked_at_utc（または Last Checked At 列）が新しい方を採用。

オプション: --redownload-conflicts
  data/startgg/events 以下で競合している matches.json を、ours/theirs の
  マージではなく start.gg からの再取得で上書きする。
  scripts/check_event_conflicts.py で競合イベントを検出し、
  scripts/fix/redownload_event.py の再取得ロジックを呼び出す。
  --token が必須。デフォルトでは無効（何もしない）。
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


# ---------------------------------------------------------------------------
# ヘルパー: git のインデックスから特定ステージのファイル内容を取得
# ---------------------------------------------------------------------------

def git_show(stage: int, path: str) -> str:
    """
    git show :<stage>:<path> を実行してファイル内容を返す。

    stage=2 → ours  (現ブランチ / HEAD)
    stage=3 → theirs (マージ元 / MERGE_HEAD / origin/main)

    競合マーカーを含まないクリーンな内容が得られる点が重要。
    ワーキングツリーのファイルは競合マーカーが混入しているため使わない。
    """
    result = subprocess.run(
        ["git", "show", f":{stage}:{path}"],
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"  [WARN] git show :{stage}:{path} failed: {result.stderr.decode().strip()}")
        return ""
    return result.stdout.decode("utf-8")


# ---------------------------------------------------------------------------
# 1. done.csv — ID（数値）の一覧
# ---------------------------------------------------------------------------

def resolve_done_csv(path: str) -> None:
    """
    done.csv は「処理済みイベントID」を1行1IDで並べたファイル。

    scripts/fetch/download.py の write_done_tournaments() が追記（append）するだけで
    ソートは行っていないため、ファイルの並びは「処理した順（挿入順）」になっている。

    マージ方針:
      - ours（現ブランチ）の行を先頭に、元の挿入順のまま保持する。
      - theirs（origin/main）のうち ours に存在しない新規IDのみを末尾に追記する。
      - ソートは行わない（挿入順を壊さないようにするため）。

    同じIDが両側に存在しても内容（数値）は同一なので、ours 側を採用すれば十分。
    """
    print(f"\n[1] {path}")

    # 空行を除外しつつ順序を保持するため list で読み込む
    ours_lines   = [l for l in git_show(2, path).splitlines() if l.strip()]
    theirs_lines = [l for l in git_show(3, path).splitlines() if l.strip()]

    # ours を順序付き集合として扱うために OrderedDict を利用
    seen: OrderedDict = OrderedDict.fromkeys(ours_lines)

    # theirs の新規IDのみ末尾に追加
    added = 0
    for line in theirs_lines:
        if line not in seen:
            seen[line] = None
            added += 1

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(seen.keys()) + "\n")

    print(f"  ours={len(ours_lines)}  theirs={len(theirs_lines)}  merged={len(seen)}"
          f"  (theirs新規追加={added})")


# ---------------------------------------------------------------------------
# 2. *.jsonl — JSON Lines 形式（1行1オブジェクト）
# ---------------------------------------------------------------------------

def resolve_jsonl(path: str, id_key: str) -> None:
    """
    JSONL ファイルを id_key（例: tournament_id / user_id）で重複排除してマージする。

    優先ルール: ours（現ブランチ）のエントリを先に確定させ、
                theirs（origin/main）は ours に存在しない新規IDのみ末尾に追加する。

    ours を優先する理由:
      現ブランチで更新・修正した可能性があるエントリを上書きされないようにするため。
      theirs 側に「更新済みの同一ID」があっても、現ブランチの内容を正とみなす。
    """
    print(f"\n[2] {path}  (id_key={id_key})")

    ours_lines   = [l for l in git_show(2, path).splitlines() if l.strip()]
    theirs_lines = [l for l in git_show(3, path).splitlines() if l.strip()]

    # ours を OrderedDict に投入（挿入順を保持）
    seen: OrderedDict = OrderedDict()
    for line in ours_lines:
        obj = json.loads(line)
        key = obj[id_key]
        if key not in seen:
            seen[key] = line  # 同一IDが ours 内に重複していても最初の1件を採用

    # theirs は新規IDのみ追加
    added_from_theirs = 0
    for line in theirs_lines:
        obj = json.loads(line)
        key = obj[id_key]
        if key not in seen:
            seen[key] = line
            added_from_theirs += 1

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(seen.values()) + "\n")

    print(f"  ours={len(ours_lines)}  theirs={len(theirs_lines)}  merged={len(seen)}"
          f"  (theirs新規追加={added_from_theirs})")


# ---------------------------------------------------------------------------
# 3. checked_dates.json — 日付をキーとした JSON オブジェクト
# ---------------------------------------------------------------------------

def resolve_checked_dates(path: str) -> None:
    """
    checked_dates.json は { "YYYY-MM-DD": { "checked_at_utc": "...", "workflow": "..." } } の形式。

    同一日付が両ブランチに存在する場合は checked_at_utc が新しい方を採用する。
    これにより「より最近チェックされた」情報が残る。
    片方にしか存在しない日付はそのまま採用。

    最終的に日付キーで昇順ソートして書き出す（JSON の可読性・差分の見やすさのため）。
    """
    print(f"\n[3] {path}")

    ours_raw   = git_show(2, path)
    theirs_raw = git_show(3, path)

    ours_dict   = json.loads(ours_raw)   if ours_raw   else {}
    theirs_dict = json.loads(theirs_raw) if theirs_raw else {}

    all_dates = sorted(set(ours_dict) | set(theirs_dict))

    merged: dict = {}
    newer_from_theirs = 0
    newer_from_ours   = 0

    for date in all_dates:
        if date in ours_dict and date in theirs_dict:
            # 両側に存在 → checked_at_utc を文字列比較（ISO 8601 形式なので辞書順＝時系列順）
            ours_ts   = ours_dict[date].get("checked_at_utc", "")
            theirs_ts = theirs_dict[date].get("checked_at_utc", "")
            if theirs_ts > ours_ts:
                merged[date] = theirs_dict[date]
                newer_from_theirs += 1
            else:
                merged[date] = ours_dict[date]
                newer_from_ours += 1
        elif date in ours_dict:
            merged[date] = ours_dict[date]
        else:
            merged[date] = theirs_dict[date]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"  ours={len(ours_dict)}  theirs={len(theirs_dict)}  merged={len(merged)}")
    print(f"  重複日付: ours採用={newer_from_ours}  theirs採用={newer_from_theirs}")


# ---------------------------------------------------------------------------
# 4. README.md — Markdown テーブル（日付行）
# ---------------------------------------------------------------------------

def resolve_readme(path: str) -> None:
    """
    README.md には2箇所の競合がある。

    【競合1】「最終更新 (UTC)」行
      - 両側のタイムスタンプを比較し、新しい方を採用する。

    【競合2】Markdown テーブルの末尾行群
      - ours と theirs がそれぞれ異なるワークフローで追記した行が重複している。
      - 日付（1列目）をキーとして重複排除する。
      - 同一日付が両側にある場合は「Last Checked At（4列目）」が新しい方を採用。
      - 片方にしか存在しない行はそのまま採用。
      - 最終的に日付昇順でテーブルを並べ直す。

    処理方針:
      競合マーカーを含むワーキングツリーのファイルではなく、
      git show :2: / :3: のクリーンな内容を使って両側のテーブルを個別解析する。
      競合マーカーのパースは行わない（複雑で壊れやすいため）。
    """
    print(f"\n[4] {path}")

    ours_raw   = git_show(2, path)
    theirs_raw = git_show(3, path)

    def parse_readme(text: str):
        """
        README テキストを解析して以下を返す:
          header_lines : テーブル開始前の全行（最終更新行を含む）
          table_rows   : OrderedDict { date_str -> full_line }
        """
        lines = text.splitlines()
        header_lines = []
        table_rows: OrderedDict = OrderedDict()
        in_table = False

        for line in lines:
            if not in_table:
                # テーブルヘッダー行を検出したら in_table モードへ
                if re.match(r"^\| Date\b", line) or re.match(r"^\| ---", line):
                    in_table = True
                    header_lines.append(line)
                else:
                    header_lines.append(line)
            else:
                # テーブルのデータ行（先頭が "| YYYY-MM-DD |" の形式）
                m = re.match(r"^\| (\d{4}-\d{2}-\d{2}) \|", line)
                if m:
                    date = m.group(1)
                    table_rows[date] = line
                else:
                    # テーブル終了（通常は EOF）
                    in_table = False
                    header_lines.append(line)

        return header_lines, table_rows

    ours_header,   ours_table   = parse_readme(ours_raw)
    theirs_header, theirs_table = parse_readme(theirs_raw)

    # ── 最終更新行の解決 ──────────────────────────────────────────────────
    # 「- 最終更新 (UTC): `YYYY-MM-DD HH:MM:SS UTC`」行を比較して新しい方を採用
    def extract_updated(lines):
        for l in lines:
            m = re.match(r"^- 最終更新 \(UTC\): `(.+)`", l)
            if m:
                return m.group(1), l
        return "", ""

    ours_ts,   ours_upd_line   = extract_updated(ours_header)
    theirs_ts, theirs_upd_line = extract_updated(theirs_header)
    winning_upd_line = ours_upd_line if ours_ts >= theirs_ts else theirs_upd_line
    print(f"  最終更新: ours={ours_ts!r}  theirs={theirs_ts!r}  → 採用={'ours' if ours_ts >= theirs_ts else 'theirs'}")

    # ── テーブル行のマージ ────────────────────────────────────────────────
    # 同一日付では Last Checked At（パイプ区切り4列目）が新しい方を採用

    def last_checked_at(row: str) -> str:
        """テーブル行から Last Checked At（4列目）を抽出する"""
        parts = [p.strip() for p in row.split("|")]
        # parts[0]=""  parts[1]=date  parts[2]=folder  parts[3]=checked  parts[4]=last_checked_at
        return parts[4] if len(parts) > 4 else ""

    merged_table: OrderedDict = OrderedDict()
    newer_from_theirs = 0
    newer_from_ours   = 0

    all_dates = sorted(set(ours_table) | set(theirs_table))
    for date in all_dates:
        if date in ours_table and date in theirs_table:
            ours_lca   = last_checked_at(ours_table[date])
            theirs_lca = last_checked_at(theirs_table[date])
            if theirs_lca > ours_lca:
                merged_table[date] = theirs_table[date]
                newer_from_theirs += 1
            else:
                merged_table[date] = ours_table[date]
                newer_from_ours += 1
        elif date in ours_table:
            merged_table[date] = ours_table[date]
        else:
            merged_table[date] = theirs_table[date]

    print(f"  テーブル行: ours={len(ours_table)}  theirs={len(theirs_table)}  merged={len(merged_table)}")
    print(f"  重複行: ours採用={newer_from_ours}  theirs採用={newer_from_theirs}")

    # ── 出力 ─────────────────────────────────────────────────────────────
    # ours のヘッダーをベースにしつつ、最終更新行だけ勝者に差し替える
    out_lines = []
    for line in ours_header:
        if re.match(r"^- 最終更新 \(UTC\): `", line):
            out_lines.append(winning_upd_line)
        else:
            out_lines.append(line)

    # テーブルデータ行を日付昇順で追加
    for date in sorted(merged_table.keys()):
        out_lines.append(merged_table[date])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")


# ---------------------------------------------------------------------------
# 5. data/startgg/events 以下の競合イベント — start.gg から再取得して上書き
# ---------------------------------------------------------------------------

def resolve_events_by_redownload(token: str, events_root: str, users_file_path: str, only_event_ids: list | None) -> list:
    """
    data/startgg/events 以下で競合している matches.json を検出し、
    該当イベントを scripts/fix/redownload_event.py の再取得ロジックで
    削除 → start.gg から再取得することで解消する。

    ours/theirs のどちらかを選ぶのではなく、start.gg 上の最新データを
    正として上書きするため、値そのものが食い違う [DIFF] ケースにも対応できる。

    only_event_ids が指定された場合は、競合イベントのうち該当する event_id のみを対象にする。
    戻り値: 実際に再取得を試みたイベントディレクトリのパス一覧（git add 対象の案内に使う）。
    """
    from scripts.check_event_conflicts import get_event_id, list_conflicting_event_paths
    from scripts.fix.redownload_event import redownload_event
    from scripts.utils import read_users_jsonl, set_api_parameters, set_indent_num, set_retry_parameters

    print(f"\n[5] data/startgg/events 以下の競合イベントを再取得")

    paths = list_conflicting_event_paths()
    if not paths:
        print("  競合中の events ファイルは見つかりませんでした。")
        return []

    conflicts = []
    for path in paths:
        event_id_str = get_event_id(path)
        if event_id_str == "unknown":
            print(f"  [WARN] event_id を特定できませんでした: {path}")
            continue
        conflicts.append((int(event_id_str), path))

    if only_event_ids is not None:
        conflicts = [(eid, path) for eid, path in conflicts if eid in only_event_ids]

    if not conflicts:
        print("  再取得対象のイベントはありませんでした。")
        return []

    set_indent_num(2)
    set_retry_parameters(20, 5)
    set_api_parameters("https://api.start.gg/gql/alpha", token)
    users = read_users_jsonl(users_file_path)
    events_root_path = Path(events_root)

    touched_dirs = []
    for event_id, path in conflicts:
        print(f"\n  -- event_id={event_id} ({path}) --")
        ok = redownload_event(event_id, events_root_path, users, users_file_path, apply=True)
        if ok:
            touched_dirs.append(os.path.dirname(path))
        else:
            print(f"  [WARN] event_id={event_id} の再取得に失敗しました。")

    return touched_dirs


# ---------------------------------------------------------------------------
# 後検証: 競合マーカーが残っていないか確認
# ---------------------------------------------------------------------------

def verify_no_conflict_markers(paths: list) -> bool:
    """
    解消後のファイルに競合マーカー（<<<<<<<）が残っていないか確認する。
    残っていた場合は警告を出す。
    """
    print("\n[検証] 競合マーカーの残存チェック")
    ok = True
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            count = content.count("<<<<<<<")
            if count > 0:
                print(f"  [NG] {path}: 競合マーカーが {count} 件残存")
                ok = False
            else:
                print(f"  [OK] {path}")
        except FileNotFoundError:
            print(f"  [WARN] {path}: ファイルが見つかりません")
    return ok


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="git merge 中の競合ファイルを解消する")
    parser.add_argument(
        "--redownload-conflicts",
        action="store_true",
        help="data/startgg/events 以下の競合イベントを ours/theirs マージではなく "
             "start.gg からの再取得で上書きする（デフォルトでは無効）",
    )
    parser.add_argument("--token", default="", help="start.gg API token（--redownload-conflicts 使用時は必須）")
    parser.add_argument("--events-root", default="data/startgg/events", help="Events root directory")
    parser.add_argument("--users-file-path", default="data/startgg/users.jsonl", help="Path to users.jsonl")
    parser.add_argument(
        "--event-id",
        type=int,
        nargs="+",
        default=None,
        help="--redownload-conflicts と併用: 競合イベントのうち、指定した event_id のみを再取得対象にする"
             "（省略時は競合中の全イベントが対象）",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.redownload_conflicts and not args.token:
        print("[ERROR] --redownload-conflicts には --token が必須です。", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("競合ファイル解消スクリプト")
    print("※ git add は行いません。内容確認後、手動で git add してください。")
    print("=" * 60)

    # -- done.csv --
    resolve_done_csv("data/startgg/done.csv")

    # -- tournaments.jsonl --
    resolve_jsonl("data/startgg/tournaments.jsonl", "tournament_id")

    # -- users.jsonl --
    resolve_jsonl("data/startgg/users.jsonl", "user_id")

    # -- checked_dates.json --
    resolve_checked_dates("docs/chore-tornament/checked_dates.json")

    # -- README.md --
    resolve_readme("docs/chore-tornament/README.md")

    # -- 後検証 --
    all_paths = [
        "data/startgg/done.csv",
        "data/startgg/tournaments.jsonl",
        "data/startgg/users.jsonl",
        "docs/chore-tornament/checked_dates.json",
        "docs/chore-tornament/README.md",
    ]
    ok = verify_no_conflict_markers(all_paths)

    # -- events 以下の競合イベント再取得（オプトイン） --
    redownloaded_dirs = []
    if args.redownload_conflicts:
        redownloaded_dirs = resolve_events_by_redownload(
            args.token, args.events_root, args.users_file_path, args.event_id
        )

    print("\n" + "=" * 60)
    if ok:
        print("完了。競合マーカーはすべて解消されました。")
        print()
        print("次のステップ（手動で実行してください）:")
        git_add_targets = [
            "data/startgg/done.csv",
            "data/startgg/tournaments.jsonl",
            "data/startgg/users.jsonl",
            "docs/chore-tornament/checked_dates.json",
            "docs/chore-tornament/README.md",
        ] + [f'"{d}"' for d in redownloaded_dirs]
        print("  git add " + " \\\n          ".join(git_add_targets))
        print("  git merge --continue")
    else:
        print("[WARNING] 競合マーカーが残存しているファイルがあります。手動で確認してください。")
        sys.exit(1)


if __name__ == "__main__":
    main()
