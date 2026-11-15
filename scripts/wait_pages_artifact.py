"""Wait for GitHub's artifact listing to expose the exact uploaded Pages artifact."""
import json
import os
import time
import urllib.request

def ready(artifacts, expected_id):
    matches = [a for a in artifacts if a.get("name") == "github-pages" and not a.get("expired")]
    return len(matches) == 1 and matches[0].get("id") == expected_id

def wait(fetch, expected_id, pause=time.sleep, attempts=40):
    for _ in range(attempts):
        if ready(fetch(), expected_id):
            return
        pause(3)
    raise RuntimeError("Uploaded Pages artifact is not visible in the run artifact listing")

def main():
    run = os.environ["GITHUB_RUN_ID"]
    artifact = os.environ["PAGES_ARTIFACT_ID"]
    if not run.isdecimal() or not artifact.isdecimal():
        raise ValueError("invalid run/artifact identifier")
    url = "https://api.github.com/repos/postmelee/rhwp-fidelity-dashboard/actions/runs/" + run + "/artifacts?per_page=100"
    def fetch():
        request = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)["artifacts"]
    wait(fetch, int(artifact))
    print("Exact Pages artifact is visible to the deployment API.")

if __name__ == "__main__":
    main()
