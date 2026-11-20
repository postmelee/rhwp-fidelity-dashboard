#!/usr/bin/env python3
"""Trusted resolver, append-only ledger and HTML builder (Python standard library)."""
import argparse
import base64
import datetime as dt
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from core import *

ROOT = Path(__file__).resolve().parent.parent
PLAN_KEYS = "schema_version run_id attempt resolved_at dashboard_sha upstream_sha source_kind source_ref corpus_sha256 font_sha256 adapter_sha256 protocol"
REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")
TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

def api(path):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "rhwp-fidelity-dashboard"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    req = urllib.request.Request("https://api.github.com/repos/edwardkim/rhwp/" + path, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

def resolve_ref(ref):
    match(REF, ref)
    if ".." in ref or "//" in ref or ref.endswith("/"):
        raise ValueError("unsafe ref")
    if SHA.fullmatch(ref):
        sha = api("commits/" + ref)["sha"]
        if sha != ref:
            raise ValueError("commit mismatch")
        return sha, "manual-sha"
    obj = api("git/ref/tags/" + urllib.parse.quote(ref, safe=""))["object"]
    seen = set()
    while obj["type"] == "tag":
        sha = match(SHA, obj["sha"])
        if sha in seen or len(seen) >= 16:
            raise ValueError("tag cycle")
        seen.add(sha)
        obj = api("git/tags/" + sha)["object"]
    if obj["type"] != "commit":
        raise ValueError("tag is not a commit")
    return match(SHA, obj["sha"]), "manual-tag"

def validate_plan(p):
    exact(p, PLAN_KEYS)
    if p["schema_version"] != 1 or p["protocol"] != PROTOCOL:
        raise ValueError("plan schema")
    integer(p["run_id"], 10**16)
    integer(p["attempt"], 10**6)
    match(TIME, p["resolved_at"])
    match(SHA, p["upstream_sha"])
    match(SHA, p["dashboard_sha"])
    match(REF, p["source_ref"])
    if p["source_kind"] not in ("manual-tag", "manual-sha", "stable-release"):
        raise ValueError("source kind")
    for k in ("corpus_sha256", "font_sha256", "adapter_sha256"):
        match(HASH, p[k])
    return p

def make_plan(ref, corpus, resolved=None):
    m = manifest(corpus, verify=False)
    if resolved is not None:
        sha, kind = resolved
    else:
        sha, kind = resolve_ref(ref)
    p = {"schema_version": 1, "run_id": int(os.environ.get("GITHUB_RUN_ID", "0")),
         "attempt": int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")),
         "resolved_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "dashboard_sha": os.environ.get("GITHUB_SHA", "0"*40),
         "upstream_sha": sha, "source_ref": ref, "source_kind": kind, "protocol": PROTOCOL,
         "corpus_sha256": digest(canonical(m)),
         "font_sha256": digest(canonical([{k:d[k] for k in ("id", "fonts", "font_environment")} for d in m["documents"]])),
         "adapter_sha256": digest(b"".join((ROOT/f).read_bytes() for f in (
             "scripts/core.py", "scripts/adapter.py", "scripts/pipeline.py", ".github/workflows/fidelity.yml")))}
    return validate_plan(p)

def identity(p):
    return tuple(p[k] for k in ("source_ref", "upstream_sha", "corpus_sha256", "font_sha256", "adapter_sha256", "protocol"))


def stable_releases():
    """Read every page; never infer absence from /releases/latest or a truncated page."""
    releases = {}
    page = 1
    while True:
        batch = api(f"releases?per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("invalid release listing")
        if not batch:
            break
        for release in batch:
            if not release["draft"] and not release["prerelease"]:
                releases[integer(release["id"], 10**16)] = release
        page += 1
        if page > 10000:
            raise ValueError("release listing exceeds safety bound; no partial selection")
    return sorted(releases.values(), key=lambda r:(r["published_at"], r["id"]))

MAX_AUTOMATIC_ATTEMPTS = 3

def choose_plan(ref, corpus, past, latest_only=False):
    if ref:
        return make_plan(ref, corpus), True
    releases = stable_releases()
    if not releases:
        raise ValueError("no stable releases")
    if latest_only:
        releases = releases[-1:]
    unseen, retries = [], []
    latest = None
    for order, release in enumerate(releases):
        tag = release["tag_name"]
        sha, _ = resolve_ref(tag)
        plan = make_plan(tag, corpus, resolved=(sha, "stable-release"))
        latest = plan
        attempts = [r for r in past if identity(r) == identity(plan)]
        if not attempts:
            unseen.append(plan)
            continue
        last = attempts[-1]  # history() supplies chronological immutable records.
        if last["status"] not in {"complete", "empty"} and len(attempts) < MAX_AUTOMATIC_ATTEMPTS:
            retries.append((last.get("resolved_at", ""), order, plan))
    # Never let retrying an old failure starve an unmeasured stable release.
    if unseen:
        return unseen[0], True
    if retries:
        return min(retries, key=lambda item:(item[0],item[1]))[2], True
    return latest, False

def history(folder, documents):
    result = []
    folder = Path(folder)
    for path in sorted(folder.glob("*.json")):
        row = read_json(path)
        exact(row, PLAN_KEYS + " status measurement")
        p = validate_plan({k:row[k] for k in PLAN_KEYS.split()})
        # Each record carries corpus identity. Only current corpus is aggregated.
        if row["corpus_sha256"] != digest(canonical(manifest(ROOT/"corpus", verify=False))):
            continue
        validated = public_record(p, row["measurement"], documents)
        if validated != row:
            raise ValueError("ledger status mismatch")
        result.append(row)
    return sorted(result, key=lambda r:(r["resolved_at"], r["run_id"], r["attempt"]))

def build(folder, out, corpus):
    from presentation import render_site

    docs = manifest(corpus, verify=False)["documents"]
    records = history(folder, docs)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for record in records:
        name = f'{record["run_id"]}-{record["attempt"]}.json'
        write_json(out / "records" / name, record)
    render_site(out, records, docs)
    write_json(out / "summary.json", {
        "latest_attempted": records[-1] if records else None,
        "last_complete": next((r for r in reversed(records) if r["status"] == "complete"), None),
        "target_documents": len(docs),
        "target_pages": sum(d["pages"] for d in docs),
    })

def git(args, cwd, env=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, env=env, text=True, capture_output=True, check=check)

def ledger_repository(destination, write=False):
    repo = os.environ["GITHUB_REPOSITORY"]
    if repo != "postmelee/rhwp-fidelity-dashboard":
        raise ValueError("unexpected repository")
    env = dict(os.environ)
    if write:
        token = env.pop("GH_TOKEN")
        env.update({"GIT_CONFIG_COUNT":"1", "GIT_CONFIG_KEY_0":"http.https://github.com/.extraheader",
                    "GIT_CONFIG_VALUE_0":"AUTHORIZATION: basic " + base64.b64encode(("x-access-token:"+token).encode()).decode()})
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    git(["init", "-b", "data"], destination, env)
    git(["remote", "add", "origin", "https://github.com/"+repo+".git"], destination, env)
    # ls-remote --exit-code distinguishes absent branch (2) from network/auth failures.
    exists = git(["ls-remote", "--exit-code", "--heads", "origin", "data"], destination, env, check=False)
    if exists.returncode == 0:
        git(["fetch", "--depth=1", "origin", "data"], destination, env)
        # Only read JSON blobs; never checkout branch-supplied code, hooks or symlinks.
        files = git(["ls-tree", "-r", "--name-only", "FETCH_HEAD"], destination, env).stdout.splitlines()
        for name in files:
            if not re.fullmatch(r"records/[0-9]+-[0-9]+\.json", name):
                raise ValueError("unexpected ledger path")
            mode = git(["ls-tree", "FETCH_HEAD", name], destination, env).stdout.split()[0]
            if mode != "100644":
                raise ValueError("unsafe ledger mode")
            data = git(["show", "FETCH_HEAD:"+name], destination, env).stdout
            p = destination/name
            p.parent.mkdir(exist_ok=True)
            p.write_text(data)
        git(["reset", "--mixed", "FETCH_HEAD"], destination, env)
    elif exists.returncode != 2:
        raise ValueError("cannot read durable ledger")
    return env

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("resolve")
    r.add_argument("--ref", default="")
    r.add_argument("--plan", default="plan.json")
    r.add_argument("--ledger", default="ledger")
    b = sub.add_parser("build")
    b.add_argument("--ledger", default="ledger")
    b.add_argument("--out", default="site")
    i = sub.add_parser("publish")
    i.add_argument("--plan", default="plan.json")
    i.add_argument("--measurement", default="incoming/result.json")
    i.add_argument("--ledger", default="ledger")
    i.add_argument("--out", default="site")
    i.add_argument("--reuse", action="store_true", help="Rebuild/deploy ledger without creating a measurement attempt")
    args = p.parse_args()
    corpus = ROOT/"corpus"
    docs = manifest(corpus, verify=False)["documents"]
    if args.command == "resolve":
        ledger_repository(args.ledger)
        past = history(Path(args.ledger)/"records", docs)
        plan, needed = choose_plan(args.ref, corpus, past, latest_only=os.environ.get("GITHUB_EVENT_NAME") == "push")
        write_json(args.plan, plan)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"sha={plan['upstream_sha']}\nneeded={'true' if needed else 'false'}\nhas_corpus={'true' if docs else 'false'}\n")
    elif args.command == "build":
        build(Path(args.ledger)/"records", args.out, corpus)
    else:
        if args.reuse:
            ledger_repository(args.ledger)
            build(Path(args.ledger)/"records", args.out, corpus)
            return
        plan = validate_plan(read_json(args.plan))
        if plan["corpus_sha256"] != digest(canonical(manifest(corpus, verify=False))):
            raise ValueError("trusted plan/corpus mismatch")
        try:
            measured = read_json(args.measurement)
            validate_measurement(measured, docs)
        except (OSError, ValueError, KeyError, TypeError):
            measured = {"schema_version":1, "environment_sha256":None, "build_sha256":None,
                        "backends":{b:empty_backend() for b in BACKENDS}}
        record = public_record(plan, measured, docs)
        env = ledger_repository(args.ledger, write=True)
        filename = f"records/{plan['run_id']}-{plan['attempt']}.json"
        target = Path(args.ledger)/filename
        if target.exists():
            if read_json(target) != record:
                raise ValueError("immutable record collision")
        else:
            write_json(target, record)
            git(["add", "--", filename], args.ledger, env)
            git(["-c", "user.name=github-actions[bot]", "-c",
                 "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                 "commit", "-m", "Record immutable fidelity attempt"], args.ledger, env)
            git(["push", "origin", "HEAD:refs/heads/data"], args.ledger, env)
        build(Path(args.ledger)/"records", args.out, corpus)

if __name__ == "__main__":
    main()
