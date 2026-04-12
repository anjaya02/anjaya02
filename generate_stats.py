#!/usr/bin/env python3
"""Generate profile `stats.svg` and `streak.svg` using GitHub GraphQL data."""

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
    for _, count in days:
        if count > 0:
            running += 1
            longest_streak = max(longest_streak, running)
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
        return datetime.strptime(value, "%Y-%m-%d").strftime("%b %d")

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


def make_stats_svg(stats: dict, langs: list[dict]) -> str:
    bar_total_width = 155

    def bar_width(percent: float) -> int:
        return round((percent / 100) * bar_total_width)

    rows = ""
    start_y = 62
    for index, lang in enumerate(langs):
        y = start_y + index * 23
        width = bar_width(lang["pct"])
        color = lang["color"] or "#8b949e"
        rows += f"""
  <text x=\"322\" y=\"{y - 2}\" class=\"lang-label\">{lang['name']}</text>
  <text x=\"477\" y=\"{y - 2}\" text-anchor=\"end\" class=\"lang-pct\">{lang['pct']}%</text>
  <rect x=\"322\" y=\"{y + 2}\" width=\"{bar_total_width}\" height=\"5\" rx=\"2.5\" class=\"bar-bg\"/>
  <rect x=\"322\" y=\"{y + 2}\" width=\"{width}\" height=\"5\" rx=\"2.5\" fill=\"{color}\"/>"""

    return f"""<svg width=\"495\" height=\"195\" viewBox=\"0 0 495 195\" xmlns=\"http://www.w3.org/2000/svg\">
  <defs>
    <style>
      .title {{ font: 600 14px 'Segoe UI', Ubuntu, sans-serif; fill: #58a6ff; }}
      .stat-label {{ font: 400 12px 'Segoe UI', Ubuntu, sans-serif; fill: #8b949e; }}
      .stat-value {{ font: 600 13px 'Segoe UI', Ubuntu, sans-serif; fill: #e6edf3; }}
      .icon {{ fill: #21c55d; }}
      .border {{ fill: none; stroke: #30363d; stroke-width: 1; }}
      .bg {{ fill: #0d1117; }}
      .bar-bg {{ fill: #21262d; }}
      .lang-label {{ font: 400 11px 'Segoe UI', Ubuntu, sans-serif; fill: #8b949e; }}
      .lang-pct {{ font: 600 11px 'Segoe UI', Ubuntu, sans-serif; fill: #e6edf3; }}
    </style>
    <pattern id=\"grid\" width=\"20\" height=\"20\" patternUnits=\"userSpaceOnUse\">
      <path d=\"M 20 0 L 0 0 0 20\" fill=\"none\" stroke=\"#21c55d\" stroke-width=\"0.1\" opacity=\"0.3\"/>
    </pattern>
  </defs>
  <rect width=\"495\" height=\"195\" rx=\"10\" class=\"bg\"/>
  <rect width=\"495\" height=\"195\" rx=\"10\" fill=\"url(#grid)\"/>
  <rect width=\"495\" height=\"195\" rx=\"10\" class=\"border\"/>
  <rect x=\"0\" y=\"30\" width=\"3\" height=\"60\" rx=\"1.5\" fill=\"#21c55d\" opacity=\"0.7\"/>
  <text x=\"25\" y=\"28\" class=\"title\">Anjaya Induwara's GitHub Stats</text>
  <line x1=\"18\" y1=\"38\" x2=\"477\" y2=\"38\" stroke=\"#21262d\" stroke-width=\"1\"/>

  <svg x=\"18\" y=\"52\" width=\"14\" height=\"14\" viewBox=\"0 0 16 16\" class=\"icon\">
    <path d=\"M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z\"/>
  </svg>
  <text x=\"38\" y=\"63\" class=\"stat-label\">Total Stars Earned:</text>
  <text x=\"210\" y=\"63\" class=\"stat-value\">{stats['stars']}</text>

  <svg x=\"18\" y=\"76\" width=\"14\" height=\"14\" viewBox=\"0 0 16 16\" class=\"icon\">
    <path d=\"M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z\"/>
  </svg>
  <text x=\"38\" y=\"87\" class=\"stat-label\">Total Commits ({stats['year']}):</text>
  <text x=\"210\" y=\"87\" class=\"stat-value\">{stats['commits']}</text>

  <svg x=\"18\" y=\"100\" width=\"14\" height=\"14\" viewBox=\"0 0 16 16\" class=\"icon\">
    <path d=\"M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354Z\"/>
  </svg>
  <text x=\"38\" y=\"111\" class=\"stat-label\">Total PRs:</text>
  <text x=\"210\" y=\"111\" class=\"stat-value\">{stats['prs']}</text>

  <svg x=\"18\" y=\"124\" width=\"14\" height=\"14\" viewBox=\"0 0 16 16\" class=\"icon\">
    <path d=\"M8 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z\"/>
    <path d=\"M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Z\"/>
  </svg>
  <text x=\"38\" y=\"135\" class=\"stat-label\">Total Issues:</text>
  <text x=\"210\" y=\"135\" class=\"stat-value\">{stats['issues']}</text>

  <svg x=\"18\" y=\"148\" width=\"14\" height=\"14\" viewBox=\"0 0 16 16\" class=\"icon\">
    <path d=\"M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8Z\"/>
  </svg>
  <text x=\"38\" y=\"159\" class=\"stat-label\">Contributed to (last year):</text>
  <text x=\"210\" y=\"159\" class=\"stat-value\">{stats['contributed_to']}</text>

  <line x1=\"310\" y1=\"42\" x2=\"310\" y2=\"183\" stroke=\"#21262d\" stroke-width=\"1\"/>
  <text x=\"395\" y=\"52\" text-anchor=\"middle\" font-family=\"'Segoe UI', Ubuntu, sans-serif\" font-size=\"12\" font-weight=\"600\" fill=\"#58a6ff\">Most Used Languages</text>
  {rows}
  <line x1=\"18\" y1=\"183\" x2=\"477\" y2=\"183\" stroke=\"#21262d\" stroke-width=\"1\"/>
  <text x=\"18\" y=\"192\" font-family=\"'Segoe UI', Ubuntu, sans-serif\" font-size=\"9\" fill=\"#3d444d\">github.com/anjaya02 · {stats['year']}</text>
  <text x=\"477\" y=\"192\" text-anchor=\"end\" font-family=\"'Segoe UI', Ubuntu, sans-serif\" font-size=\"9\" fill=\"#21c55d\">reputify.lk</text>
</svg>"""


def make_streak_svg(stats: dict) -> str:
    return f"""<svg width=\"495\" height=\"130\" viewBox=\"0 0 495 130\" xmlns=\"http://www.w3.org/2000/svg\">
  <defs>
    <style>
      .bg {{ fill: #0d1117; }}
      .border {{ fill: none; stroke: #30363d; stroke-width: 1; }}
      .label {{ font: 400 11px 'Segoe UI', Ubuntu, sans-serif; fill: #8b949e; }}
      .big-num {{ font: 700 36px 'Segoe UI', Ubuntu, sans-serif; fill: #21c55d; }}
      .section-title {{ font: 600 11px 'Segoe UI', Ubuntu, sans-serif; fill: #58a6ff; letter-spacing: 1px; }}
    </style>
    <pattern id=\"grid2\" width=\"20\" height=\"20\" patternUnits=\"userSpaceOnUse\">
      <path d=\"M 20 0 L 0 0 0 20\" fill=\"none\" stroke=\"#21c55d\" stroke-width=\"0.1\" opacity=\"0.25\"/>
    </pattern>
  </defs>
  <rect width=\"495\" height=\"130\" rx=\"10\" class=\"bg\"/>
  <rect width=\"495\" height=\"130\" rx=\"10\" fill=\"url(#grid2)\"/>
  <rect width=\"495\" height=\"130\" rx=\"10\" class=\"border\"/>
  <rect x=\"0\" y=\"20\" width=\"3\" height=\"50\" rx=\"1.5\" fill=\"#21c55d\" opacity=\"0.6\"/>

  <text x=\"82\" y=\"22\" text-anchor=\"middle\" class=\"section-title\">TOTAL CONTRIBUTIONS</text>
  <text x=\"82\" y=\"68\" text-anchor=\"middle\" class=\"big-num\">{stats['total_contribs']}</text>
  <text x=\"82\" y=\"85\" text-anchor=\"middle\" class=\"label\">Jan 1 - Dec 31, {stats['year']}</text>

  <line x1=\"165\" y1=\"18\" x2=\"165\" y2=\"112\" stroke=\"#21262d\" stroke-width=\"1\"/>

  <text x=\"247\" y=\"22\" text-anchor=\"middle\" class=\"section-title\">CURRENT STREAK</text>
  <text x=\"247\" y=\"68\" text-anchor=\"middle\" class=\"big-num\">{stats['current_streak']}</text>
  <text x=\"247\" y=\"85\" text-anchor=\"middle\" class=\"label\">{stats['streak_start']} - {stats['streak_end']}</text>

  <line x1=\"330\" y1=\"18\" x2=\"330\" y2=\"112\" stroke=\"#21262d\" stroke-width=\"1\"/>

  <text x=\"412\" y=\"22\" text-anchor=\"middle\" class=\"section-title\">LONGEST STREAK</text>
  <text x=\"412\" y=\"68\" text-anchor=\"middle\" class=\"big-num\">{stats['longest_streak']}</text>
  <text x=\"412\" y=\"85\" text-anchor=\"middle\" class=\"label\">All time</text>

  <line x1=\"18\" y1=\"112\" x2=\"477\" y2=\"112\" stroke=\"#21262d\" stroke-width=\"1\"/>
  <text x=\"247\" y=\"123\" text-anchor=\"middle\" font-family=\"'Segoe UI', Ubuntu, sans-serif\" font-size=\"9\" fill=\"#3d444d\">github.com/anjaya02 · {stats['year']}</text>
</svg>"""


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

    print("Done.")


if __name__ == "__main__":
    main()
