#!/usr/bin/env python3
"""Generate DASHBOARD.md: a categorized index of every repository of the account.

Categories and short descriptions come from dashboard/config.json. When the
GitHub API is reachable, each entry is enriched with language, stars, last
update and upstream (for forks); repositories missing from the config are
listed under "Non classés" so nothing is forgotten.

Usage:
    python dashboard/generate.py            # fetch metadata from the GitHub API
    python dashboard/generate.py --offline  # use config.json only
Set GITHUB_TOKEN to raise the API rate limit.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "dashboard" / "config.json"
OUTPUT = ROOT / "DASHBOARD.md"
API = "https://api.github.com"


def api_get(path):
    req = urllib.request.Request(API + path, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_repos(owner):
    repos, page = {}, 1
    while True:
        batch = api_get(f"/users/{owner}/repos?per_page=100&type=owner&page={page}")
        for repo in batch:
            repos[repo["name"]] = repo
        if len(batch) < 100:
            return repos
        page += 1


def fetch_parent(owner, name):
    try:
        return api_get(f"/repos/{owner}/{name}").get("parent", {}).get("full_name")
    except urllib.error.URLError:
        return None


def row(owner, name, note, meta):
    link = f"[**{name}**](https://github.com/{owner}/{name})"
    if not meta:
        return f"| {link} | {note} |"
    desc = note or meta.get("description") or ""
    if meta.get("parent"):
        desc += f" <sub>fork de [{meta['parent']}](https://github.com/{meta['parent']})</sub>"
    lang = meta.get("language") or "—"
    stars = meta.get("stargazers_count", 0)
    updated = (meta.get("pushed_at") or "")[:10]
    return f"| {link} | {desc.strip()} | {lang} | {stars} | {updated} |"


def render(config, repos):
    owner = config["owner"]
    online = repos is not None
    header = (
        "| Dépôt | Description | Langage | ⭐ | Mis à jour |\n|---|---|---|---:|---|"
        if online
        else "| Dépôt | Description |\n|---|---|"
    )

    categories = [dict(c) for c in config["categories"]]
    if online:
        known = {n for c in categories for n in c["repos"]} | set(config.get("exclude", []))
        extra = {n: "" for n in sorted(repos, key=str.lower) if n not in known}
        if extra:
            categories.append({"name": "📦 Non classés", "repos": extra})
        # Drop entries listed in the config but no longer on GitHub, and empty categories.
        for c in categories:
            c["repos"] = {n: d for n, d in c["repos"].items() if n in repos}
        categories = [c for c in categories if c["repos"]]

    total = sum(len(c["repos"]) for c in categories)
    out = [
        f"# {config['title']}",
        "",
        f"Point d'entrée vers les **{total} dépôts** de [@{owner}](https://github.com/{owner}), "
        "classés par thème.",
        "",
        "> Généré automatiquement par `dashboard/generate.py`. Pour classer un dépôt ou "
        "modifier sa description, éditez `dashboard/config.json`.",
        "",
        "## Sommaire",
        "",
        "| Catégorie | Dépôts |",
        "|---|---:|",
    ]
    for c in categories:
        anchor = "".join(ch for ch in c["name"].lower() if ch.isalnum() or ch in " -_")
        anchor = anchor.replace(" ", "-")
        out.append(f"| [{c['name']}](#{anchor}) | {len(c['repos'])} |")

    for c in categories:
        out += ["", f"## {c['name']}", "", header]
        for name, note in c["repos"].items():
            meta = repos.get(name) if online else None
            out.append(row(owner, name, note, meta))

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out += ["", "---", "", f"<sub>Dernière génération : {stamp}</sub>", ""]
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="do not call the GitHub API")
    args = parser.parse_args()

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    repos = None
    if not args.offline:
        try:
            repos = fetch_repos(config["owner"])
            for name, meta in repos.items():
                if meta.get("fork"):
                    meta["parent"] = fetch_parent(config["owner"], name)
        except urllib.error.URLError as exc:
            print(f"GitHub API unavailable ({exc}); falling back to --offline", file=sys.stderr)
            repos = None

    OUTPUT.write_text(render(config, repos), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
