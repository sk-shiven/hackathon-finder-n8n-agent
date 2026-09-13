#!/usr/bin/env python3
import os
import sys
import time
import requests
from collections import defaultdict

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")

if not NOTION_TOKEN or not DATABASE_ID:
    print("Missing NOTION_TOKEN or DATABASE_ID env var", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def notion_post(url, payload):
    r = requests.post(url, headers=HEADERS, json=payload, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"POST {url} failed: {r.status_code} {r.text}")
    return r.json()

def notion_patch(url, payload):
    r = requests.patch(url, headers=HEADERS, json=payload, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"PATCH {url} failed: {r.status_code} {r.text}")
    return r.json()

def get_title_exact(page):
    """
    Extract the Notion title property value as a plain string.
    Works for typical database title property.
    """
    props = page.get("properties", {})
    # Find the title-type property (usually "Name")
    for _, v in props.items():
        if v.get("type") == "title":
            parts = v.get("title") or []
            return "".join(p.get("plain_text", "") for p in parts)
    return ""

def query_all_pages(database_id):
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    all_pages = []
    cursor = None

    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor

        data = notion_post(url, payload)
        all_pages.extend(data.get("results", []))

        if data.get("has_more"):
            cursor = data.get("next_cursor")
        else:
            break

    return all_pages

def archive_page(page_id):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    notion_patch(url, {"archived": True})

def main():
    pages = query_all_pages(DATABASE_ID)
    print(f"Fetched {len(pages)} pages")

    groups = defaultdict(list)
    for p in pages:
        name = get_title_exact(p)
        if name is None:
            name = ""
        created_time = p.get("created_time") or ""
        groups[name].append((created_time, p["id"]))

    to_archive = []
    for name, items in groups.items():
        # Only dedupe exact matches; empty names are also grouped together
        if len(items) <= 1:
            continue
        items_sorted = sorted(items, key=lambda x: x[0])  # oldest first
        keep = items_sorted[0]
        duplicates = items_sorted[1:]
        for ct, pid in duplicates:
            to_archive.append((name, ct, pid, keep[1]))

    print(f"Found {len(to_archive)} duplicate rows to archive")

    # Archive with a small delay to avoid rate limits
    for i, (name, ct, pid, keep_id) in enumerate(to_archive, start=1):
        print(f"[{i}/{len(to_archive)}] Archiving duplicate: name='{name}' page_id={pid} (keeping {keep_id})")
        archive_page(pid)
        time.sleep(0.35)

    print("Done.")

if __name__ == "__main__":
    main()