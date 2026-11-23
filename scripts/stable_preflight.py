"""Check whether an exact release can use the current receipt-track producer."""
import ast
import base64
import hashlib
from urllib.error import HTTPError, URLError

from adapter import REQUIRED
from core import KEY, HASH, SHA, canonical, digest, exact, integer, match, read_json, write_json

ENTRYPOINT = "visual_sweep.py"
FILES = {
    ENTRYPOINT, "visual_sweep_workers.py", "visual_sweep_images.py",
    "visual_sweep_pdf.py", "visual_sweep_resume.py",
}
CONTRACT = digest(canonical({"version": 1, "files": sorted(FILES), "options": sorted(REQUIRED)}))
STATIC = {"static_pass", "unsupported"}
READ_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, SyntaxError)
TRANSIENT = {"authentication", "rate_limited", "timeout", "api_error"}


def tree_entries(api, sha):
    result = api("git/trees/" + match(SHA, sha))
    if result["sha"] != sha or result["truncated"] is not False or not isinstance(result["tree"], list):
        raise ValueError("incomplete tree response")
    entries = {}
    for row in result["tree"]:
        name = row["path"]
        if not isinstance(name, str) or name in entries:
            raise ValueError("malformed tree entry")
        match(SHA, row["sha"])
        if (row["type"], row["mode"]) not in {
            ("tree", "040000"), ("blob", "100644"), ("blob", "100755"),
            ("blob", "120000"), ("commit", "160000"),
        }:
            raise ValueError("invalid tree entry type")
        entries[name] = row
    return entries


def script_source(api, sha):
    row = api("git/blobs/" + sha)
    if row["sha"] != sha or row["encoding"] != "base64":
        raise ValueError("incorrect Sweep blob")
    data = base64.b64decode("".join(row["content"].splitlines()), validate=True)
    header = f"blob {len(data)}\0".encode()
    if row["size"] != len(data) or hashlib.sha1(header + data, usedforsecurity=False).hexdigest() != sha:
        raise ValueError("Sweep blob hash mismatch")
    return data.decode()


def error_status(error):
    if isinstance(error, HTTPError):
        try:
            headers = error.headers or {}
            if error.code == 429:
                return "rate_limited"
            if error.code == 403 and (headers.get("X-RateLimit-Remaining") == "0"
                    or headers.get("Retry-After") or b"secondary rate limit" in error.read(4096).lower()):
                return "rate_limited"
            if error.code in (401, 403):
                return "authentication"
            if error.code == 408:
                return "timeout"
        except OSError:
            return "api_error"
        finally:
            error.close()
    reason = error.reason if isinstance(error, URLError) else error
    return "timeout" if isinstance(reason, TimeoutError) else "api_error"


def inspect_commit(api, tag, sha):
    item = {"tag": tag, "engine_sha": match(SHA, sha), "status": "static_pass",
            "missing_files": [], "missing_options": []}
    try:
        commit = api("git/commits/" + sha)
        if commit["sha"] != sha:
            raise ValueError("incorrect commit")
        root = tree_entries(api, commit["tree"]["sha"])
        scripts = root.get("scripts", {})
        entries = tree_entries(api, scripts["sha"]) if scripts.get("type") == "tree" else {}
        missing = sorted(name for name in FILES if entries.get(name, {}).get("mode") not in {"100644", "100755"})
        if missing:
            return dict(item, status="unsupported", missing_files=missing)
        source = script_source(api, entries[ENTRYPOINT]["sha"])
        strings = {node.value for node in ast.walk(ast.parse(source))
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        options = sorted(REQUIRED - strings)
        return dict(item, status="unsupported", missing_options=options) if options else item
    except READ_ERRORS as error:
        return dict(item, status=error_status(error))


def validate(value, run_id=None, attempt=None, producer_sha=None):
    exact(value, "schema_version run_id attempt producer_sha contract_sha256 releases")
    if value["schema_version"] != 1:
        raise ValueError("unknown compatibility report schema")
    integer(value["run_id"], 10**16)
    integer(value["attempt"], 10**6)
    match(SHA, value["producer_sha"])
    match(HASH, value["contract_sha256"])
    for field, expected in (("run_id", run_id), ("attempt", attempt), ("producer_sha", producer_sha)):
        if expected is not None and value[field] != expected:
            raise ValueError("wrong compatibility report origin")
    if not isinstance(value["releases"], list) or not value["releases"]:
        raise ValueError("empty compatibility report")
    seen = set()
    for item in value["releases"]:
        exact(item, "tag engine_sha status missing_files missing_options")
        match(KEY, item["tag"].replace(".", "-"))
        if item["engine_sha"] is not None or item["status"] in STATIC:
            match(SHA, item["engine_sha"])
        key = item["tag"], item["engine_sha"]
        if key in seen or item["status"] not in STATIC | TRANSIENT:
            raise ValueError("invalid compatibility observation")
        seen.add(key)
        for key in ("missing_files", "missing_options"):
            names = item[key]
            if (not isinstance(names, list)
                    or any(not isinstance(name, str) or not name or len(name) > 128 for name in names)
                    or names != sorted(set(names))):
                raise ValueError("invalid missing producer requirements")
        if (item["status"] == "unsupported") != bool(item["missing_files"] or item["missing_options"]):
            raise ValueError("unproven compatibility rejection")
        if value["contract_sha256"] == CONTRACT and (set(item["missing_files"]) - FILES
                                                    or set(item["missing_options"]) - REQUIRED):
            raise ValueError("unknown producer requirement")
    return value


def reports(folder):
    values = []
    for path in sorted(folder.glob("*.json")):
        value = validate(read_json(path))
        if path.stem != f'{value["run_id"]}-{value["attempt"]}':
            raise ValueError("mislabeled compatibility report")
        values.append(value)
    return sorted(values, key=lambda value: (value["run_id"], value["attempt"]))


class StablePreflight:
    def __init__(self, api, history):
        self.api = api
        self.cache = {}
        self.observed_tags = set()
        self.observations = []
        self.blocked_status = None
        for report in history:
            if report["contract_sha256"] != CONTRACT:
                continue
            for item in report["releases"]:
                if item["status"] in STATIC:
                    self.remember(item)

    def remember(self, item):
        sha = item["engine_sha"]
        previous = self.cache.get(sha)
        if previous is not None and dict(previous, tag=item["tag"]) != item:
            raise ValueError("conflicting static evidence for immutable commit")
        self.cache[sha] = item
        self.observed_tags.add((item["tag"], sha))

    def finish(self, item):
        self.observations.append(item)
        if item["status"] in STATIC:
            self.remember(item)
        elif item["status"] in ("authentication", "rate_limited"):
            self.blocked_status = item["status"]

    def resolve(self, tag, resolve_ref):
        try:
            return match(SHA, resolve_ref(tag)[0])
        except READ_ERRORS as error:
            self.finish({"tag": tag, "engine_sha": None, "status": error_status(error),
                         "missing_files": [], "missing_options": []})
            return None

    def allows(self, tag, sha):
        prior = self.cache.get(sha)
        if (tag, sha) in self.observed_tags:
            return prior["status"] == "static_pass"
        item = dict(prior, tag=tag) if prior else inspect_commit(self.api, tag, sha)
        self.finish(item)
        return item["status"] == "static_pass"


DISPLAY = {
    "static_pass": "Static check passed",
    "unsupported": "Unsupported by this producer",
    "authentication": "Deferred · authentication or permissions",
    "rate_limited": "Deferred · rate limited",
    "timeout": "Deferred · timed out",
    "api_error": "Deferred · API error or incomplete evidence",
}


def build(folder, out):
    from cohort_site import page
    from preview_presentation import table

    latest = {}
    for report in reports(folder):
        if report["contract_sha256"] != CONTRACT:
            continue
        for item in report["releases"]:
            key = item["tag"], item["engine_sha"]
            if item["engine_sha"] is not None:
                latest.pop((item["tag"], None), None)
            if item["status"] in TRANSIENT and latest.get(key, {}).get("status") in STATIC:
                continue
            latest[key] = dict(item, run_id=report["run_id"], attempt=report["attempt"])
    value = list(latest.values())
    if not value:
        return ""
    value.sort(key=lambda row: (row["tag"], row["engine_sha"] or ""))
    rows = []
    for item in value:
        missing = ["scripts/" + name for name in item["missing_files"]] + item["missing_options"]
        rows.append([item["tag"], item["engine_sha"] or "Unresolved", DISPLAY[item["status"]],
                     ", ".join(missing) or "—", f'{item["run_id"]}-{item["attempt"]}'])
    name = "stable-compatibility"
    caption = table("Pinned stable producer checks",
                    ["Release", "Engine commit", "Preflight", "Missing requirement", "Run and attempt"], rows, cards=True)
    body = ('<p><a href="index.html#history">Run history</a> · '
            '<a href="stable-compatibility.json">Compatibility checks JSON</a></p>'
            '<p>Preflight checks the files and command-line options required by this dashboard’s producer. '
            'A passing check still requires a successful build and measurement. For deferred checks, the planner tries again on a later run.</p>'
            + caption)
    write_json(out / (name + ".json"),
               {"schema_version": 1, "contract_sha256": CONTRACT, "releases": value})
    (out / (name + ".html")).write_text(page("Stable release compatibility", body, section="history", section_label="Run history"))
    return '<p><a href="stable-compatibility.html">Stable release compatibility</a></p>'
