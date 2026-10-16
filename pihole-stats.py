#!/usr/bin/env python3
"""
Pull summary numbers from Pi-hole's API and save them as stats.json
for the portfolio website to display.

Only totals and the top *blocked* domains are published. The full
query log (every site your devices visit) never leaves the Pi.

Run every 5 minutes from cron.
"""

import json
import os
import time
import urllib.parse
import urllib.request

PIHOLE = "http://localhost/api"
PASSWORD_FILE = os.path.expanduser("~/.pihole_app_password")
OUTPUT = "/var/www/html/stats.json"


def call(method, path, sid=None, body=None):
    url = PIHOLE + path
    if sid:
        sep = "&" if "?" in url else "?"
        url += sep + "sid=" + urllib.parse.quote(sid)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def hourly(history):
    """Pi-hole reports 10-minute slots; combine them into hours."""
    buckets = {}
    for slot in history:
        hour = int(slot["timestamp"]) // 3600 * 3600
        b = buckets.setdefault(hour, {"t": hour, "total": 0, "blocked": 0})
        b["total"] += slot.get("total", 0)
        b["blocked"] += slot.get("blocked", 0)
    return [buckets[h] for h in sorted(buckets)][-24:]


def main():
    with open(PASSWORD_FILE) as f:
        password = f.read().strip()

    sid = call("POST", "/auth", body={"password": password})["session"]["sid"]
    try:
        summary = call("GET", "/stats/summary", sid)
        top = call("GET", "/stats/top_domains?blocked=true&count=6", sid)
        try:
            history = hourly(call("GET", "/history", sid).get("history", []))
        except Exception:
            history = []
    finally:
        # Log out so we don't use up Pi-hole's limited session slots
        try:
            call("DELETE", "/auth", sid)
        except Exception:
            pass

    q = summary["queries"]
    stats = {
        "updated": int(time.time()),
        "total": q["total"],
        "blocked": q["blocked"],
        "percent_blocked": round(q["percent_blocked"], 1),
        "blocklist_size": summary["gravity"]["domains_being_blocked"],
        "top_blocked": [{"domain": d["domain"], "count": d["count"]}
                        for d in top.get("domains", [])],
        "hourly": history,
    }

    # Write to a temp file first, then swap it in, so visitors never
    # load a half-written file
    tmp = OUTPUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(stats, f)
    os.replace(tmp, OUTPUT)


if __name__ == "__main__":
    main()
