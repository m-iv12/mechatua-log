"""ページの「追加」から作られた GitHub Issue の本文を読み、data/*.json に書き足す。

本文の形式（1行1項目）:
  type: collab | schedule | post | deadline | exclude
  url: ...
  start: 2026-11-03T20:00:00+09:00   (schedule)
  title: ... / game: ... / own: yes|no (schedule)
  time: ... / announce: yes|no        (post)
  deadline: ... / title: ...          (deadline)
  start: 2026-12-05 / end: ... / title: ... / time: ... / note: ... (plan：予定メモ)
  dates: 2026-11-08 20:00 予選 / 2026-11-22 本番   (plan：飛び飛びの日程のとき。時刻と一言は任意)
  start: ... / title: ...             (unplan：予定メモを消す)
"""
import json
import os
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent
NO_YOUTUBE = "/tmp/shared/no_youtube"   # fetch_streams.py への合図


def load(name, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def prune_plans(items):
    """予定メモのうち、終了日（なければ開始日）が日本時間で今日より前のものを除く。"""
    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    out = []
    for x in items:
        if x.get("dates"):
            # 飛び飛びの日程は、過ぎた日を一覧から外す（全部過ぎたらメモごと消す）
            days = [d for d in x["dates"] if d.get("date", "9999") >= today]
            if not days:
                continue
            x = dict(x, dates=days, start=days[0]["date"])
            if days[-1]["date"] != days[0]["date"]:
                x["end"] = days[-1]["date"]
            else:
                x.pop("end", None)
        if (x.get("end") or x.get("start") or "9999") >= today:
            out.append(x)
    return out


def main():
    body = os.environ.get("ISSUE_BODY", "")
    f = {}
    for line in body.splitlines():
        m = re.match(r"\s*([a-z]+):\s*(.+?)\s*$", line)
        if m and m.group(1) not in f:
            f[m.group(1)] = m.group(2)
    t = f.get("type")

    if t == "collab":
        url = f.get("url", "")
        if not re.search(r"(?:v=|youtu\.be/|/live/|/shorts/)[A-Za-z0-9_-]{11}", url):
            sys.exit("YouTube の URL が読み取れません")
        items = load("collab_videos.json", [])
        if url not in items:
            items.append(url)
        save("collab_videos.json", items)
        # 以前に除外していたら除外を解除
        vid = re.search(r"(?:v=|youtu\.be/|/live/|/shorts/)([A-Za-z0-9_-]{11})", url).group(1)
        ex = [x for x in load("collab_exclude.json", []) if vid not in x]
        save("collab_exclude.json", ex)

    elif t == "schedule":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00", f.get("start", "")):
            sys.exit("開始日時が読み取れません")
        item = {"start": f["start"], "title": f.get("title", "配信予定")[:200],
                "game": f.get("game", "その他"), "own": f.get("own", "yes") == "yes"}
        if f.get("url", "").startswith("https://"):
            item["url"] = f["url"]
        items = load("schedule.json", [])
        if item not in items:
            items.append(item)
        save("schedule.json", items)

    elif t == "post":
        url = f.get("url", "")
        if not re.search(r"(?:x|twitter)\.com/[^/]+/status/\d+", url):
            sys.exit("X の URL が読み取れません")
        announce = f.get("announce") == "yes"
        item = {"time": f.get("time"), "text": "配信告知" if announce else "ポスト", "url": url}
        if announce:
            item["kind"] = "announce"
        items = [p for p in load("posts.json", []) if p.get("url") != url]
        items.append(item)
        items.sort(key=lambda p: p.get("time") or "")
        save("posts.json", items)

    elif t == "exclude":
        url = f.get("url", "")
        m = re.search(r"(?:v=|youtu\.be/|/live/|/shorts/)([A-Za-z0-9_-]{11})", url)
        if not m:
            sys.exit("YouTube の URL が読み取れません")
        vid = m.group(1)
        ex = load("collab_exclude.json", [])
        if not any(vid in x for x in ex):
            ex.append(f"https://www.youtube.com/watch?v={vid}")
        save("collab_exclude.json", ex)
        # 手動で登録していた場合は登録も外す
        save("collab_videos.json", [x for x in load("collab_videos.json", []) if vid not in x])

    elif t == "plan":
        # 予定メモ：まだ枠のない先の予定（大会・サーバー企画など）。終了日（なければ開始日）が過ぎたら消す
        start, end = f.get("start", ""), f.get("end", "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start):
            sys.exit("開始日が読み取れません")
        if end and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end) or end < start):
            sys.exit("終了日が読み取れません")
        item = {"title": f.get("title", "予定")[:200], "start": start}
        if end and end != start:
            item["end"] = end
        # 複数の日（飛び飛び）：「dates: 2026-11-08 予選 / 2026-11-15 予選 / 2026-11-22 本番」
        if f.get("dates"):
            days = []
            for part in f["dates"].split("/"):
                m = re.match(r"\s*(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}:\d{2}))?\s*(.*?)\s*$", part)
                if m:
                    d = {"date": m.group(1)}
                    if m.group(2):
                        d["time"] = m.group(2)
                    if m.group(3):
                        d["label"] = m.group(3)[:40]
                    days.append(d)
            if not days:
                sys.exit("日付が読み取れません")
            days.sort(key=lambda d: d["date"])
            item["dates"] = days
            item["start"], start = days[0]["date"], days[0]["date"]
            if days[-1]["date"] != start:
                item["end"] = days[-1]["date"]
        if re.fullmatch(r"\d{1,2}:\d{2}", f.get("time", "")):
            item["time"] = f["time"]
        if f.get("note"):
            item["note"] = f["note"][:300]
        if f.get("url", "").startswith("https://"):
            item["url"] = f["url"]
        items = [x for x in prune_plans(load("plans.json", [])) if (x.get("title"), x.get("start")) != (item["title"], start)]
        items.append(item)
        items.sort(key=lambda x: x["start"])
        save("plans.json", items)

    elif t == "unplan":
        start, title = f.get("start", ""), f.get("title", "")
        before = load("plans.json", [])
        def same(x):
            starts = {x.get("start")} | {d.get("date") for d in x.get("dates", [])}
            return x.get("title") == title and start in starts
        items = [x for x in prune_plans(before) if not same(x)]
        if len(items) == len(prune_plans(before)):
            print("消す予定メモが見つかりませんでした（すでに消えている可能性があります）")
        save("plans.json", items)

    elif t == "deadline":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00", f.get("deadline", "")):
            sys.exit("締切日時が読み取れません")
        item = {"title": f.get("title", "締切")[:200], "deadline": f["deadline"]}
        if f.get("url", "").startswith("https://"):
            item["url"] = f["url"]
        items = load("deadlines.json", [])
        if item not in items:
            items.append(item)
        items.sort(key=lambda d: d["deadline"])
        save("deadlines.json", items)

    else:
        sys.exit("type が読み取れません")
    print("追加しました:", t)
    # ポスト・締切は YouTube のデータを使わないので、このあとの取得では YouTube に問い合わせない（API の使用量を節約）
    if t in ("post", "deadline", "schedule", "plan", "unplan"):
        Path(NO_YOUTUBE).parent.mkdir(parents=True, exist_ok=True)
        Path(NO_YOUTUBE).touch()


if __name__ == "__main__":
    main()
