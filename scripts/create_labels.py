import os
import requests

repo = os.environ["GITHUB_REPOSITORY"]
token = os.environ["GITHUB_TOKEN"]

labels = {
    "review": ("FBCA04", "人間の確認待ち"),
    "approve": ("0E8A16", "公開を承認"),
    "reject": ("B60205", "公開しない"),
    "needs-fix": ("D93F0B", "修正が必要"),
}

for name, (color, description) in labels.items():
    r = requests.post(
        f"https://api.github.com/repos/{repo}/labels",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"name": name, "color": color, "description": description},
        timeout=30,
    )
    if r.status_code not in (201, 422):
        r.raise_for_status()
    print(name, r.status_code)
