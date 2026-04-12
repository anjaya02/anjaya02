#!/usr/bin/env python3
"""Generate profile `stats.svg` and `streak.svg` using GitHub GraphQL data.

Produces cyberpunk-themed SVG cards with grid patterns, scanlines,
corner accents, glow filters, and subtle animations.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

USERNAME = "anjaya02"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "User-Agent": "anjaya02-profile-generator",
}

STATS_QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      nodes { stargazerCount }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
          }
        }
      }
    }
    repositoriesContributedTo(
      first: 1
      contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]
    ) {
      totalCount
    }
  }
}
"""

LANG_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def gql(query: str, variables: dict | None = None) -> dict:
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is missing.")

    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request("https://api.github.com/graphql", data=payload, headers=HEADERS)

    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub GraphQL HTTP {exc.code}: {details}") from exc

    if data.get("errors"):
        raise RuntimeError(f"GitHub GraphQL errors: {data['errors']}")

    return data


def fetch_stats() -> dict:
    user = gql(STATS_QUERY, {"login": USERNAME})["data"]["user"]

    stars = sum(repo["stargazerCount"] for repo in user["repositories"]["nodes"])
    collection = user["contributionsCollection"]
    calendar = collection["contributionCalendar"]

    days: list[tuple[str, int]] = []
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            days.append((day["date"], day["contributionCount"]))
    days.sort()

    today = datetime.now(timezone.utc).date().isoformat()

    current_streak = 0
    for date, count in reversed(days):
        if date > today:
            continue
        if count > 0:
            current_streak += 1
        else:
            break

    longest_streak = 0
    running = 0
    longest_start = ""
    longest_end = ""
    run_start = ""
    for date, count in days:
        if count > 0:
            if running == 0:
                run_start = date
            running += 1
            if running > longest_streak:
                longest_streak = running
                longest_start = run_start
                longest_end = date
        else:
            running = 0

    streak_dates: list[str] = []
    for date, count in reversed(days):
        if date > today:
            continue
        if count > 0:
            streak_dates.append(date)
        else:
            break

    streak_start = streak_dates[-1] if streak_dates else today
    streak_end = streak_dates[0] if streak_dates else today

    def fmt_date(value: str) -> str:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%b %-d")

    return {
        "stars": stars,
        "commits": collection["totalCommitContributions"],
        "prs": collection["totalPullRequestContributions"],
        "issues": collection["totalIssueContributions"],
        "contributed_to": user["repositoriesContributedTo"]["totalCount"],
        "total_contribs": calendar["totalContributions"],
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "streak_start": fmt_date(streak_start),
        "streak_end": fmt_date(streak_end),
        "longest_start": fmt_date(longest_start) if longest_start else "",
        "longest_end": fmt_date(longest_end) if longest_end else "",
        "year": datetime.now(timezone.utc).year,
    }


def fetch_languages() -> list[dict]:
    language_sizes: dict[str, dict[str, float | str]] = {}
    after: str | None = None

    while True:
        data = gql(LANG_QUERY, {"login": USERNAME, "after": after})
        repos = data["data"]["user"]["repositories"]

        for repo in repos["nodes"]:
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                color = edge["node"]["color"] or "#8b949e"
                size = edge["size"]

                if name not in language_sizes:
                    language_sizes[name] = {"size": 0, "color": color}
                language_sizes[name]["size"] += size

        if not repos["pageInfo"]["hasNextPage"]:
            break
        after = repos["pageInfo"]["endCursor"]

    total_size = sum(v["size"] for v in language_sizes.values())
    if total_size == 0:
        return []

    top_languages = sorted(language_sizes.items(), key=lambda item: item[1]["size"], reverse=True)[:5]
    result: list[dict] = []

    for name, info in top_languages:
        pct = round((info["size"] / total_size) * 100, 1)
        result.append({"name": name, "pct": pct, "color": info["color"]})

    return result


# ─── Determine rank based on activity ───────────────────────────────

def compute_rank(stats: dict) -> str:
    score = (
        stats["stars"] * 2
        + stats["commits"]
        + stats["prs"] * 3
        + stats["issues"] * 2
        + stats["contributed_to"] * 5
    )
    if score >= 500:
        return "S+"
    if score >= 300:
        return "A+"
    if score >= 200:
        return "A"
    if score >= 100:
        return "B+"
    return "B"


# ─── SVG builders ───────────────────────────────────────────────────

def make_stats_svg(stats: dict, langs: list[dict]) -> str:
    bar_total_width = 157
    rank = compute_rank(stats)

    def bar_width(percent: float) -> int:
        return round((percent / 100) * bar_total_width)

    rows = ""
    start_y = 68
    for index, lang in enumerate(langs):
        y = start_y + index * 23
        width = bar_width(lang["pct"])
        color = lang["color"] or "#8b949e"
        rows += f"""
  <text x=\"320\" y=\"{y}\" class=\"lang-label\">{lang['name']}</text>
  <text x=\"477\" y=\"{y}\" text-anchor=\"end\" class=\"lang-pct\">{lang['pct']}%</text>
  <rect x=\"320\" y=\"{y + 4}\" width=\"{bar_total_width}\" height=\"6\" rx=\"3\" class=\"bar-bg\" fill=\"#161b22\"/>
  <rect x=\"320\" y=\"{y + 4}\" width=\"{width}\" height=\"6\" rx=\"3\" fill=\"{color}\"/>"""

    return f"""<svg width=\"495\" height=\"210\" viewBox=\"0 0 495 210\" xmlns=\"http://www.w3.org/2000/svg\">
  <defs>
    <style>
      @keyframes pulse {{
        0%, 100% {{ opacity: 0.4; }}
        50% {{ opacity: 1; }}
      }}
      .title {{ font: 700 13px 'Segoe UI', Ubuntu, sans-serif; fill: #e6edf3; letter-spacing: 0.5px; }}
      .subtitle {{ font: 400 10px 'Segoe UI', Ubuntu, sans-serif; fill: #21c55d; letter-spacing: 2px; }}
      .stat-label {{ font: 400 11.5px 'Segoe UI', Ubuntu, sans-serif; fill: #8b949e; }}
      .stat-value {{ font: 700 13px 'Segoe UI', Ubuntu, sans-serif; fill: #e6edf3; }}
      .icon {{ fill: #21c55d; }}
      .border {{ fill: none; stroke: #21c55d; stroke-width: 1; opacity: 0.15; }}
      .bg {{ fill: #0d1117; }}
      .bar-bg {{ fill: #161b22; rx: 3; }}
      .lang-label {{ font: 500 10.5px 'Segoe UI', Ubuntu, sans-serif; fill: #8b949e; }}
      .lang-pct {{ font: 700 10.5px 'Segoe UI', Ubuntu, sans-serif; fill: #e6edf3; }}
      .rank-text {{ font: 800 13px 'Segoe UI', Ubuntu, sans-serif; fill: #21c55d; }}
      .section-label {{ font: 600 10px 'Segoe UI', Ubuntu, sans-serif; fill: #58a6ff; letter-spacing: 1.5px; }}
      .pulse-dot {{ animation: pulse 2s ease-in-out infinite; }}
    </style>
    <pattern id=\"grid\" width=\"30\" height=\"30\" patternUnits=\"userSpaceOnUse\">
      <path d=\"M 30 0 L 0 0 0 30\" fill=\"none\" stroke=\"#21c55d\" stroke-width=\"0.15\" opacity=\"0.12\"/>
    </pattern>
    <pattern id=\"scan\" width=\"4\" height=\"4\" patternUnits=\"userSpaceOnUse\">
      <line x1=\"0\" y1=\"0\" x2=\"4\" y2=\"0\" stroke=\"#21c55d\" stroke-width=\"0.1\" opacity=\"0.08\"/>
    </pattern>
    <filter id=\"glow\">
      <feGaussianBlur stdDeviation=\"2\" result=\"coloredBlur\"/>
      <feMerge>
        <feMergeNode in=\"coloredBlur\"/>
        <feMergeNode in=\"SourceGraphic\"/>
      </feMerge>
    </filter>
    <linearGradient id=\"rankGrad\" x1=\"0%\" y1=\"0%\" x2=\"100%\" y2=\"100%\">
      <stop offset=\"0%\" stop-color=\"#21c55d\" stop-opacity=\"0.2\"/>
      <stop offset=\"100%\" stop-color=\"#21c55d\" stop-opacity=\"0.05\"/>
    </linearGradient>
  </defs>

  <rect width=\"495\" height=\"210\" rx=\"10\" class=\"bg\"/>
  <rect width=\"495\" height=\"210\" rx=\"10\" fill=\"url(#grid)\"/>
  <rect width=\"495\" height=\"210\" rx=\"10\" fill=\"url(#scan)\"/>
  <rect width=\"495\" height=\"210\" rx=\"10\" class=\"border\"/>

  <path d=\"M 0 12 L 0 0 L 12 0\" fill=\"none\" stroke=\"#21c55d\" stroke-width=\"1.5\" opacity=\"0.3\" transform=\"translate(4,4)\"/>
  <path d=\"M 0 -12 L 0 0 L 12 0\" fill=\"none\" stroke=\"#21c55d\" stroke-width=\"1.5\" opacity=\"0.3\" transform=\"translate(4,206)\"/>
  <path d=\"M 0 0 L -12 0 M 0 0 L 0 12\" fill=\"none\" stroke=\"#21c55d\" stroke-width=\"1.5\" opacity=\"0.3\" transform=\"translate(491,4)\"/>

  <rect x=\"0\" y=\"35\" width=\"3\" height=\"80\" rx=\"1.5\" fill=\"#21c55d\" opacity=\"0.5\"/>

  <text x=\"20\" y=\"24\" class=\"subtitle\">GITHUB STATS</text>
  <text x=\"20\" y=\"38\" class=\"title\">Anjaya Induwara</text>

  <circle cx=\"470\" cy=\"18\" r=\"3\" fill=\"#21c55d\" class=\"pulse-dot\"/>
  <text x=\"460\" y=\"22\" text-anchor=\"end\" font-family=\"'Segoe UI', Ubuntu, sans-serif\" font-size=\"9\" fill=\"#21c55d\" opacity=\"0.6\">LIVE</text>

  <line x1=\"15\" y1=\"46\" x2=\"480\" y2=\"46\" stroke=\"#21262d\" stroke-width=\"1\"/>

  <svg x=\"18\" y=\"56\" width=\"14\" height=\"14\" viewBox=\"0 0 16 16\" class=\"icon\">
    <path d=\"M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z\"/>
  </svg>
  <text x=\"38\" y=\"67\" class=\"stat-label\">Total Stars Earned</text>
  <text x=\"200\" y=\"67\" class=\"stat-value\">{stats['stars']}</text>

  <svg x=\"18\" y=\"78\" width=\"14\" height=\"14\" viewBox=\"0 0 16 16\" class=\"icon\">
    <path d=\"M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z\"/>
  </svg>
  <text x=\"38\" y=\"89\" class=\"stat-label\">Total Commits ({stats['year']})</text>
  <text x=\"200\" y=\"89\" class=\"stat-value\">{stats['commits']}</text>

  <svg x=\"18\" y=\"100\" width=\"14\" height=\"14\" viewBox=\"0 0 16 16\" class=\"icon\">
    <path d=\"M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354Z\"/>
  </svg>
  <text x=\"38\" y=\"111\" class=\"stat-label\">Total PRs</text>
  <text x=\"200\" y=\"111\" class=\"stat-value\">{stats['prs']}</text>

  <svg x=\"18\" y=\"122\" width=\"14\" height=\"14\" viewBox=\"0 0 16 16\" class=\"icon\">
    <path d=\"M8 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z\"/>
    <path d=\"M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Z\"/>
  </svg>
  <text x=\"38\" y=\"133\" class=\"stat-label\">Total Issues</text>
  <text x=\"200\" y=\"133\" class=\"stat-value\">{stats['issues']}</text>

  <svg x=\"18\" y=\"144\" width=\"14\" height=\"14\" viewBox=\"0 0 16 16\" class=\"icon\">
    <path d=\"M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8Z\"/>
  </svg>
  <text x=\"38\" y=\"155\" class=\"stat-label\">Contributed to (last year)</text>
  <text x=\"200\" y=\"155\" class=\"stat-value\">{stats['contributed_to']}</text>

  <rect x=\"235\" y=\"52\" width=\"65\" height=\"28\" rx=\"6\" fill=\"url(#rankGrad)\" stroke=\"#21c55d\" stroke-width=\"0.5\" opacity=\"0.8\"/>
  <text x=\"267\" y=\"70\" text-anchor=\"middle\" class=\"rank-text\" filter=\"url(#glow)\">{rank} Rank</text>

  <line x1=\"310\" y1=\"50\" x2=\"310\" y2=\"195\" stroke=\"#21262d\" stroke-width=\"1\"/>

  <text x=\"320\" y=\"59\" class=\"section-label\">MOST USED LANGUAGES</text>
  {rows}

  <line x1=\"15\" y1=\"195\" x2=\"480\" y2=\"195\" stroke=\"#21262d\" stroke-width=\"1\"/>
  <text x=\"15\" y=\"206\" font-family=\"'Segoe UI', Ubuntu, sans-serif\" font-size=\"9\" fill=\"#3d444d\">github.com/anjaya02 · {stats['year']}</text>
  <text x=\"480\" y=\"206\" text-anchor=\"end\" font-family=\"'Segoe UI', Ubuntu, sans-serif\" font-size=\"9\" fill=\"#21c55d\" opacity=\"0.7\">⬡ reputify.lk</text>
</svg>"""


def make_streak_svg(stats: dict) -> str:
    return f"""<svg width=\"495\" height=\"145\" viewBox=\"0 0 495 145\" xmlns=\"http://www.w3.org/2000/svg\">
  <defs>
    <style>
      @keyframes pulse {{
        0%, 100% {{ opacity: 0.4; }}
        50% {{ opacity: 1; }}
      }}
      @keyframes flicker {{
        0%, 19%, 21%, 23%, 25%, 54%, 56%, 100% {{ opacity: 1; }}
        20%, 24%, 55% {{ opacity: 0.6; }}
      }}
      .bg {{ fill: #0d1117; }}
      .border {{ fill: none; stroke: #21c55d; stroke-width: 1; opacity: 0.15; }}
      .label {{ font: 400 10.5px 'Segoe UI', Ubuntu, sans-serif; fill: #8b949e; }}
      .big-num {{ font: 800 38px 'Segoe UI', Ubuntu, sans-serif; fill: #21c55d; }}
      .section-title {{ font: 700 10px 'Segoe UI', Ubuntu, sans-serif; fill: #58a6ff; letter-spacing: 2px; }}
      .fire {{ animation: flicker 3s ease-in-out infinite; }}
      .pulse-ring {{ animation: pulse 2s ease-in-out infinite; }}
    </style>
    <pattern id=\"grid2\" width=\"30\" height=\"30\" patternUnits=\"userSpaceOnUse\">
      <path d=\"M 30 0 L 0 0 0 30\" fill=\"none\" stroke=\"#21c55d\" stroke-width=\"0.15\" opacity=\"0.12\"/>
    </pattern>
    <pattern id=\"scan2\" width=\"4\" height=\"4\" patternUnits=\"userSpaceOnUse\">
      <line x1=\"0\" y1=\"0\" x2=\"4\" y2=\"0\" stroke=\"#21c55d\" stroke-width=\"0.1\" opacity=\"0.08\"/>
    </pattern>
    <filter id=\"glow2\">
      <feGaussianBlur stdDeviation=\"3\" result=\"coloredBlur\"/>
      <feMerge>
        <feMergeNode in=\"coloredBlur\"/>
        <feMergeNode in=\"SourceGraphic\"/>
      </feMerge>
    </filter>
    <linearGradient id=\"centerGrad\" x1=\"0%\" y1=\"0%\" x2=\"0%\" y2=\"100%\">
      <stop offset=\"0%\" stop-color=\"#21c55d\" stop-opacity=\"0.05\"/>
      <stop offset=\"50%\" stop-color=\"#21c55d\" stop-opacity=\"0.02\"/>
      <stop offset=\"100%\" stop-color=\"#21c55d\" stop-opacity=\"0\"/>
    </linearGradient>
  </defs>

  <rect width=\"495\" height=\"145\" rx=\"10\" class=\"bg\"/>
  <rect width=\"495\" height=\"145\" rx=\"10\" fill=\"url(#grid2)\"/>
  <rect width=\"495\" height=\"145\" rx=\"10\" fill=\"url(#scan2)\"/>
  <rect width=\"495\" height=\"145\" rx=\"10\" class=\"border\"/>

  <path d=\"M 0 10 L 0 0 L 10 0\" fill=\"none\" stroke=\"#21c55d\" stroke-width=\"1.5\" opacity=\"0.3\" transform=\"translate(4,4)\"/>
  <path d=\"M 0 0 L -10 0 M 0 0 L 0 10\" fill=\"none\" stroke=\"#21c55d\" stroke-width=\"1.5\" opacity=\"0.3\" transform=\"translate(491,4)\"/>

  <rect x=\"0\" y=\"25\" width=\"3\" height=\"60\" rx=\"1.5\" fill=\"#21c55d\" opacity=\"0.4\"/>

  <rect x=\"165\" y=\"10\" width=\"165\" height=\"120\" fill=\"url(#centerGrad)\"/>

  <text x=\"82\" y=\"24\" text-anchor=\"middle\" class=\"section-title\">TOTAL CONTRIBUTIONS</text>
  <text x=\"82\" y=\"76\" text-anchor=\"middle\" class=\"big-num\">{stats['total_contribs']}</text>
  <text x=\"82\" y=\"90\" text-anchor=\"middle\" class=\"label\">Jan 1 – Dec 31, {stats['year']}</text>

  <line x1=\"165\" y1=\"18\" x2=\"165\" y2=\"125\" stroke=\"#21262d\" stroke-width=\"1\"/>

  <text x=\"247\" y=\"24\" text-anchor=\"middle\" class=\"section-title\">CURRENT STREAK 🔥</text>

  <text x=\"247\" y=\"76\" text-anchor=\"middle\" class=\"big-num\" filter=\"url(#glow2)\">{stats['current_streak']}</text>
  <text x=\"247\" y=\"96\" text-anchor=\"middle\" class=\"label\">{stats['streak_start']} – {stats['streak_end']}</text>

  <rect x=\"225\" y=\"100\" width=\"44\" height=\"16\" rx=\"4\" fill=\"#21c55d\" opacity=\"0.1\" stroke=\"#21c55d\" stroke-width=\"0.5\"/>
  <text x=\"247\" y=\"112\" text-anchor=\"middle\" font-family=\"'Segoe UI', Ubuntu, sans-serif\" font-size=\"8\" font-weight=\"700\" fill=\"#21c55d\" opacity=\"0.8\">DAYS</text>

  <line x1=\"330\" y1=\"18\" x2=\"330\" y2=\"125\" stroke=\"#21262d\" stroke-width=\"1\"/>

  <text x=\"412\" y=\"24\" text-anchor=\"middle\" class=\"section-title\">LONGEST STREAK 🏆</text>
  <text x=\"412\" y=\"76\" text-anchor=\"middle\" class=\"big-num\">{stats['longest_streak']}</text>
  <text x=\"412\" y=\"90\" text-anchor=\"middle\" class=\"label\">{stats.get('longest_start', 'All time')}{' – ' + stats['longest_end'] if stats.get('longest_end') else ''}</text>

  <line x1=\"15\" y1=\"125\" x2=\"480\" y2=\"125\" stroke=\"#21262d\" stroke-width=\"1\"/>
  <text x=\"247\" y=\"138\" text-anchor=\"middle\" font-family=\"'Segoe UI', Ubuntu, sans-serif\" font-size=\"9\" fill=\"#3d444d\">github.com/anjaya02 · {stats['year']}</text>
</svg>"""

def update_readme(stats: dict) -> None:
    readme_path = "README.md"
    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"File {readme_path} not found.")
        return

    import re
    from datetime import datetime
    
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # Calculate exact age
    birth_date = datetime(2002, 2, 25)
    now = datetime.now()
    age = now.year - birth_date.year - ((now.month, now.day) < (birth_date.month, birth_date.day))
    
    new_neofetch = f"""```text
        .--.          anjaya02@github
       |o_o |         ──────────────────
       |:_/ |         OS: Engineer v{current_year}.{current_month}
      //   \ \        Uptime: {age} years (since 2002)
     (|     | )       Shell: Python | TypeScript | Java
    /'\_   _/`\       Resolution: 1920x1080 @ 60fps
    \___)=(___/       DE: VS Code + GitHub Copilot
                      WM: Windows 11
  ┌─────────────┐     Terminal: Windows Terminal
  │ 🔋 caffeine │     Role: Software Developer @ SLTMobitel
  │ ⚡ shipping  │     Task: Building Reputify
  │ 🎯 building │     CPU: {stats['current_streak']}-day focus streak
  └─────────────┘     Memory: Coffee-fueled, never enough RAM
                      GPU: GPT-4o + HuggingFace
```"""

    pattern = r'(<!-- NEOFETCH START -->)(.*?)(<!-- NEOFETCH END -->)'
    
    if re.search(pattern, content, flags=re.DOTALL):
        updated_content = re.sub(
            pattern,
            f"\\1\n{new_neofetch}\n\\3",
            content,
            flags=re.DOTALL
        )
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
        print("Updated README.md with live neofetch stats.")
    else:
        print("Could not find NEOFETCH tags in README.md")

def main() -> None:
    print("Fetching stats...")
    stats = fetch_stats()
    print(f"  Stars: {stats['stars']}, Commits: {stats['commits']}, PRs: {stats['prs']}")
    print(
        f"  Streak: {stats['current_streak']} days, Longest: {stats['longest_streak']} days"
    )

    print("Fetching languages...")
    languages = fetch_languages()
    for lang in languages:
        print(f"  {lang['name']}: {lang['pct']}%")

    with open("stats.svg", "w", encoding="utf-8", newline="\n") as file:
        file.write(make_stats_svg(stats, languages))

    with open("streak.svg", "w", encoding="utf-8", newline="\n") as file:
        file.write(make_streak_svg(stats))

    update_readme(stats)

    print("Done — cyberpunk SVGs generated ⚡")

if __name__ == "__main__":
    main()
