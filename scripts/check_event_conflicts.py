#!/usr/bin/env python3
"""
check_event_conflicts.py

data/startgg/events 以下の競合 JSON ファイルに対して、
「配列要素の順序が変わっているだけで、値は変わっていないか」を検証するツール。

git add は一切行わない。読み取り専用の確認ツール。

使い方:
    python3 scripts/check_event_conflicts.py

出力:
    [OK]   <path>  ours=N theirs=N  → 順序のみの差。値は同一。
    [DIFF] <path>                   → 値の差分あり。詳細を表示。
    [SKIP] <path>                   → stage 2/3 の取得に失敗。
"""

import json
import subprocess
import sys


# ---------------------------------------------------------------------------
# ヘルパー: git インデックスから特定ステージの内容を取得
# ---------------------------------------------------------------------------

def git_show(stage: int, path: str) -> bytes | None:
    """
    git show :<stage>:<path> を実行してファイル内容を bytes で返す。
    失敗した場合は None を返す。

    bytes で返す理由: JSON は UTF-8 で書かれているが、
    パスの decode より先にエラー有無を確認したいため。
    """
    result = subprocess.run(
        ["git", "show", f":{stage}:{path}"],
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


# ---------------------------------------------------------------------------
# ヘルパー: 競合ファイルの列挙
# ---------------------------------------------------------------------------

def list_conflicting_event_paths() -> list[str]:
    """
    git ls-files -z --unmerged を NUL 区切りで取得し、
    data/startgg/events を含むパスだけを返す。

    -z オプションを使う理由:
      git ls-files のデフォルト出力は非 ASCII パスを "..." で引用するが、
      -z を使うと NUL 区切りで引用符なしに出力されるため、
      日本語などのパスでも安全に処理できる。
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", "--unmerged"],
        capture_output=True,
    )
    if result.returncode != 0:
        print("git ls-files の実行に失敗しました", file=sys.stderr)
        sys.exit(1)

    # NUL で分割し、空エントリを除く
    # 各行の形式: "<mode> <hash> <stage>\t<path>"
    entries = result.stdout.split(b"\x00")
    paths = set()
    for entry in entries:
        if not entry:
            continue
        # タブ以降がパス
        if b"\t" not in entry:
            continue
        path_bytes = entry.split(b"\t", 1)[1]
        path = path_bytes.decode("utf-8")
        # events ディレクトリ以下のみ対象
        if "data/startgg/events" in path:
            paths.add(path)

    return sorted(paths)


# ---------------------------------------------------------------------------
# ヘルパー: JSON 値を順序非依存の正規化形式（ハッシュ可能なタプル）に変換
# ---------------------------------------------------------------------------

def canonicalize(value) -> tuple:
    """
    JSON 値を再帰的に「順序に依存しない正規化形式」へ変換する。

    dict  → (key, value) ペアをキーでソートしたタプル（再帰）
    list  → 各要素を canonicalize した後にソートしたタプル
              ※ リストの元の順序は無視する（順序差分を検出しないため）
    その他 → そのまま

    この変換後の値は hashable なので set に入れてセット比較できる。
    """
    if isinstance(value, dict):
        return tuple(
            sorted((k, canonicalize(v)) for k, v in value.items())
        )
    elif isinstance(value, list):
        # None と int など異なる型が混在するリストは sorted() で TypeError になるため、
        # 型名を先頭キーにして比較できるようにする
        def sort_key(x):
            return (type(x).__name__, str(x))
        return tuple(sorted((canonicalize(item) for item in value), key=sort_key))
    else:
        return value


# ---------------------------------------------------------------------------
# ヘルパー: canonicalize 済みタプルを人間が読める形に戻す
# ---------------------------------------------------------------------------

def decanonicalize(canon: tuple) -> dict | list | object:
    """
    canonicalize() の逆変換。差分表示のために使う。
    完全な逆変換ではなく、dict/list の判別のみ行う簡易版。
    """
    if isinstance(canon, tuple) and all(
        isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
        for item in canon
    ):
        # (key, value) ペアのタプル → dict
        return {k: decanonicalize(v) for k, v in canon}
    elif isinstance(canon, tuple):
        return [decanonicalize(item) for item in canon]
    else:
        return canon


# ---------------------------------------------------------------------------
# ヘルパー: 特定ブランチ・特定ファイルの最終コミット日時を取得
# ---------------------------------------------------------------------------

def get_last_commit_info(branch: str, path: str) -> str:
    """
    指定ブランチ上で指定ファイルを最後に変更したコミットの
    日時とメッセージを返す。

    tournaments.jsonl は event ファイルと同じコミットで更新されることが多いため、
    ここでは matches.json ファイル自体の履歴を参照する。
    これにより「ours / theirs それぞれでいつそのファイルが更新されたか」がわかる。

    branch: "HEAD" または "MERGE_HEAD"
    戻り値例: "2026-06-25 20:01:36 +0900  chore(data): update tournament data"
    """
    result = subprocess.run(
        ["git", "log", branch, "-1", "--format=%ai  %s", "--", path],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip() or "(コミット履歴なし)"


# ---------------------------------------------------------------------------
# メイン処理: 1ファイルのチェック
# ---------------------------------------------------------------------------

def check_file(path: str) -> str:
    """
    指定パスの matches.json を stage 2 / stage 3 から取得し、
    data 配列の要素セットを比較する。

    戻り値: "ok" | "diff" | "skip"
    """
    raw2 = git_show(2, path)
    raw3 = git_show(3, path)

    if raw2 is None or raw3 is None:
        print(f"[SKIP] {path}")
        if raw2 is None:
            print(f"       stage 2 (ours) を取得できませんでした")
        if raw3 is None:
            print(f"       stage 3 (theirs) を取得できませんでした")
        return "skip"

    # JSON パース
    try:
        obj2 = json.loads(raw2.decode("utf-8"))
        obj3 = json.loads(raw3.decode("utf-8"))
    except json.JSONDecodeError as e:
        print(f"[SKIP] {path}")
        print(f"       JSON parse エラー: {e}")
        return "skip"

    # data 配列を取り出す
    # matches.json のトップレベルは {"data": [...]} の形式
    data2 = obj2.get("data", [])
    data3 = obj3.get("data", [])

    # 各要素を正規化してセット化
    # → 順序を無視した「要素の集合」として比較できる
    set2 = set(canonicalize(m) for m in data2)
    set3 = set(canonicalize(m) for m in data3)

    # コミット日時を取得（どちらが新しいか判断材料にする）
    ours_commit   = get_last_commit_info("HEAD",       path)
    theirs_commit = get_last_commit_info("MERGE_HEAD", path)

    if set2 == set3:
        # セットが一致 → 順序のみの差
        print(f"[OK]   {path}")
        print(f"       ours={len(data2)} theirs={len(data3)} 件（順序のみの差・値は同一）")
        print(f"       ours   (HEAD):       {ours_commit}")
        print(f"       theirs (MERGE_HEAD): {theirs_commit}")
        return "ok"
    else:
        # セットが不一致 → 値の差分あり
        print(f"[DIFF] {path}")
        print(f"       ours   (HEAD):       {ours_commit}")
        print(f"       theirs (MERGE_HEAD): {theirs_commit}")
        only_in_ours   = set2 - set3
        only_in_theirs = set3 - set2
        if only_in_ours:
            print(f"       ours のみに存在する要素 ({len(only_in_ours)} 件):")
            for item in only_in_ours:
                print(f"         {json.dumps(decanonicalize(item), ensure_ascii=False)}")
        if only_in_theirs:
            print(f"       theirs のみに存在する要素 ({len(only_in_theirs)} 件):")
            for item in only_in_theirs:
                print(f"         {json.dumps(decanonicalize(item), ensure_ascii=False)}")
        return "diff"


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("events 競合ファイル チェックツール（順序変更のみか検証）")
    print("※ git add は行いません。")
    print("=" * 70)

    paths = list_conflicting_event_paths()

    if not paths:
        print("\n競合中の events ファイルは見つかりませんでした。")
        return

    print(f"\n対象ファイル数: {len(paths)} 件\n")

    results = {"ok": 0, "diff": 0, "skip": 0}
    for path in paths:
        status = check_file(path)
        results[status] += 1
        print()

    print("=" * 70)
    print(f"結果サマリー: OK={results['ok']}  DIFF={results['diff']}  SKIP={results['skip']}")
    if results["diff"] == 0 and results["skip"] == 0:
        print("すべてのファイルで値は同一です。順序のみの差でした。")
        print("ours / theirs のどちらを採用してもデータは同じです。")
    elif results["diff"] > 0:
        print("[!] 値の差分があるファイルがあります。上記の DIFF 詳細を確認してください。")


if __name__ == "__main__":
    main()
