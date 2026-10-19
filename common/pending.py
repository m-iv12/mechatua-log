"""開いたままの「[追加]」Issue をまとめて登録する（8人共通）。

自動更新や手動実行のたびに動き、ページの「追加」から作られたのに登録されていない Issue
（同時に追加して失敗したもの、順番待ちで取り消されたものなど）を拾い直す。
  python pending.py add    … 開いている Issue の内容を add_item.py で書き足す（リポジトリのフォルダで実行）
  python pending.py close  … 書き足した Issue を閉じる（保存が終わったあとに実行）
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SHARED = Path("/tmp/shared")
LIST = SHARED / "pending_issues.json"   # 取得した Issue の一覧（やり直しのときも同じものを使う）
DONE = SHARED / "done_issues.json"      # 書き足せた Issue の番号
NO_YOUTUBE = SHARED / "no_youtube"      # add_item.py が置く合図（自動更新では YouTube も取得するので消す）


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def add():
    repo, owner = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_REPOSITORY_OWNER"]
    if not LIST.exists():
        r = gh("issue", "list", "-R", repo, "--state", "open", "--author", owner, "--limit", "1000",
               "--json", "number,title,body")
        if r.returncode != 0:
            print("Issue の一覧を取得できませんでした:", r.stderr.strip())
            return
        LIST.write_text(r.stdout)
    issues = sorted((i for i in json.loads(LIST.read_text()) if i["title"].startswith("[追加]")), key=lambda i: i["number"])
    done, failed = [], []
    for i in issues:
        r = subprocess.run([sys.executable, "add_item.py"], env=dict(os.environ, ISSUE_BODY=i.get("body") or ""),
                           capture_output=True, text=True)
        (done if r.returncode == 0 else failed).append(i["number"])
        if r.returncode != 0:
            print(f"#{i['number']} を登録できませんでした:", (r.stderr or r.stdout).strip())
    DONE.write_text(json.dumps(done))
    NO_YOUTUBE.unlink(missing_ok=True)
    print(f"開いたままの [追加]: {len(issues)} 件 → 登録 {len(done)} 件" + (f"、失敗 {len(failed)} 件" if failed else ""))


def close():
    if not DONE.exists():
        return
    repo = os.environ["GITHUB_REPOSITORY"]
    for n in json.loads(DONE.read_text()):
        gh("issue", "close", str(n), "-R", repo, "--comment", "まとめて反映しました。数分後にカレンダーに表示されます。")
    print(f"{len(json.loads(DONE.read_text()))} 件の Issue を閉じました")


if __name__ == "__main__":
    {"add": add, "close": close}[sys.argv[1] if len(sys.argv) > 1 else "add"]()
