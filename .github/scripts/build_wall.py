#!/usr/bin/env python3
"""Rebuild wall.json, the public blessing wall on Ivika's page.

Runs in GitHub Actions every 30 minutes (see ../workflows/refresh-wall.yml).
Reads the Google Sheet through the Apps Script admin endpoint (key from the
SHEET_KEY secret) and writes only what the page shows: first name + last
initial, Family/Friend, the message, and when a blessing was sent.

Filters (the sheet itself is never changed):
  * Status "Hidden" in the sheet        -> never shown
  * blank, test and junk names          -> never shown
  * removed-on-request names/fragments  -> never shown
  * swear words or links                -> held back, unless Status says "Approved"
"""
import hashlib, json, os, re, sys, urllib.request
from datetime import datetime, timezone

SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwXuUsGkQSibQVm_SmWBTfT6siLTtd4XuqVvgMt6iOssC5W2BWk6JX9ACzCaqH-XoK42Q/exec"
OUT = "wall.json"

SEEN, UPDATED, STATUS, NAME, WISH, RELATION = 0, 1, 2, 4, 12, 13

KIN = {"nani", "dadi", "nana", "dada", "bua", "mama", "masi", "mausi", "chachi", "chacha", "chachu",
       "taiji", "tauji", "phupa", "bhabhi", "bhaiya", "didi", "ji"}
JUNK_NAMES = {"testing", "test", "admin", "abcd", "hehe", "abd", "ab", "yu", "pan", "hmmm",
              "kyu batau", "asdf", "xyz", "claude"}
# removed on request; stored as hashes so the names don't appear in this public file
HIDDEN_NAME_HASHES = {"3329df4eed8d7b4faf28"}
# half-typed wishes the old game autosaved
FRAGMENTS = {"phupa", "may your", "hey future advika"}
UNKIND = re.compile(
    r"\b(fuck\w*|f\*+k|shit\w*|bitch\w*|asshole\w*|bastard\w*|dick|dickhead|porn\w*|slut\w*|whore\w*|"
    r"chutiy\w*|chut|madar\s?chod\w*|maderchod\w*|behen\s?chod\w*|bhen\s?chod\w*|benchod\w*|bsdk|bhosd\w*|"
    r"gaand\w*|gandu|lund|lauda|laude|lawda|lawde|randi|harami\w*|kamina|kamine|mc|bc)\b", re.I)
LINK = re.compile(r"https?://|www\.|\.com\b", re.I)


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def short_name(raw):
    parts = [w[:1].upper() + w[1:].lower() for w in norm(raw).split(" ") if w]
    if len(parts) == 1:
        return parts[0]
    if parts[-1].lower() in KIN:
        return " ".join(parts)
    return f"{parts[0]} {parts[-1][0]}."


def iso(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return ""


def main():
    key = os.environ.get("SHEET_KEY")
    if not key:
        sys.exit("SHEET_KEY is not set")
    with urllib.request.urlopen(f"{SCRIPT_URL}?stats=full&key={key}", timeout=60) as r:
        data = json.load(r)
    if not data.get("ok"):
        sys.exit("The sheet did not answer (wrong key or script error)")

    seen, blessings, wishes, held = set(), [], [], 0
    for row in data["rows"]:
        row = list(row) + [""] * (14 - len(row))
        name, text, status = norm(row[NAME]), norm(row[WISH]), norm(row[STATUS]).lower()
        lower = name.lower()
        if not name or len(text) < 6 or "hidden" in status:
            continue
        if lower in JUNK_NAMES or "delete me" in lower or lower.startswith("test "):
            continue
        if hashlib.sha256(lower.encode()).hexdigest()[:20] in HIDDEN_NAME_HASHES:
            continue
        if re.sub(r"[^\w\s]", "", text).strip().lower() in FRAGMENTS:
            continue
        if "approved" not in status and (UNKIND.search(text) or UNKIND.search(name) or LINK.search(text)):
            held += 1
            continue
        k = lower + "|" + text[:40].lower()
        if k in seen:
            continue
        seen.add(k)
        entry = {"n": short_name(name), "r": "Friend" if norm(row[RELATION]).lower() == "friend" else "Family", "t": text[:600]}
        if status.startswith("blessing"):
            entry["b"] = 1
            entry["at"] = iso(row[UPDATED] or row[SEEN])
            blessings.append(entry)
        else:
            entry["b"] = 0
            wishes.append(entry)

    blessings.sort(key=lambda e: e["at"], reverse=True)          # newest first
    wishes.sort(key=lambda e: len(e["t"]), reverse=True)          # the long, heartfelt ones first
    wall = blessings + wishes

    old = None
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding="utf-8")).get("wall")
        except (ValueError, OSError):
            pass
    if old == wall:
        print(f"No change: {len(blessings)} blessings, {len(wishes)} wishes, {held} held back.")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"), "wall": wall},
                  f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"Updated: {len(blessings)} blessings, {len(wishes)} wishes, {held} held back.")


if __name__ == "__main__":
    main()
