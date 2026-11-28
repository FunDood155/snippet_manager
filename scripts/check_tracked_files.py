"""Reject tracked runtime data and recognizable credentials without printing their contents."""
import re
import subprocess
from pathlib import PurePosixPath


PUBLIC_FILES = {".env.example"}
CREDENTIALS = re.compile(
    rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"
    rb"|\bsb_secret_[A-Za-z0-9_-]{20,}"
    rb"|\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"
    rb"|postgres(?:ql)?://[^\s:'\"/@]+:[^\s'\"]+@[^\s'\"]+",
    re.IGNORECASE,
)
FIXTURE_CONNECTIONS = {
    "tests/test_authentication.py": b"postgresql" b"://snippet_app:fixture-only@{url.hostname}:{url.port}/wp01_fixture",
    ".github/workflows/security-checks.yml": b"postgresql" b"://postgres:fixture-only@127.0.0.1:",
}


def blocked_file(path):
    if path in PUBLIC_FILES:
        return False
    name = PurePosixPath(path).name.lower()
    return (name == "snippets.json" or name in {".env", ".envrc", ".pgpass", ".netrc"}
            or name.startswith(".env.") or name.endswith((".db", ".db-wal", ".db-shm", ".db-journal",
                                                            ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx")))


def contains_credential(path, content):
    if content.startswith(b"SQLite format 3\x00"):
        return True
    fixture = FIXTURE_CONNECTIONS.get(path)
    if fixture:
        content = content.replace(fixture, b"")
    return bool(CREDENTIALS.search(content))


def main():
    # Read staged blobs, so an edited worktree cannot conceal a staged secret.
    listing = subprocess.check_output(["git", "ls-files", "--stage", "-z"])
    rejected = []
    for item in listing.split(b"\0"):
        if not item:
            continue
        metadata, filename = item.split(b"\t", 1)
        mode, oid, stage = metadata.split()
        path = filename.decode("utf-8", "surrogateescape")
        if blocked_file(path):
            rejected.append(path)
        elif stage == b"0" and mode.startswith(b"100"):
            content = subprocess.check_output(["git", "cat-file", "blob", oid.decode("ascii")])
            if contains_credential(path, content):
                rejected.append(path)
    for path in rejected:
        print(f"Review tracked file: {path!r}")
    return bool(rejected)


if __name__ == "__main__":
    raise SystemExit(main())
