"""Download the local embedding model once, and verify it (ticket N3).

Usage:  python -m admin.fetch_model [--print-hashes]

Fetches sentence-transformers/all-MiniLM-L6-v2 (Apache-2.0) from its OFFICIAL
source, at the pinned revision in config.EMBED_MODEL_REVISION, into
config.EMBED_MODEL_DIR (models/, not in git). Each file's sha256 must match
config.EMBED_MODEL_SHA256; a mismatch deletes the file, and the app refuses
to use a model that doesn't verify (app/embedder.py), falling back to the
character matcher.
"""

import argparse
import hashlib
import sys

import httpx

from app import config

BASE = "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/{rev}/{path}"


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(print_hashes: bool = False) -> int:
    ok = True
    for rel, expected in config.EMBED_MODEL_SHA256.items():
        dest = config.EMBED_MODEL_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and sha256(dest) == expected:
            print(f"ok (cached): {rel}")
            continue
        url = BASE.format(rev=config.EMBED_MODEL_REVISION, path=rel)
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
        got = sha256(dest)
        if print_hashes:
            print(f"{rel}: {got}")
        if got != expected:
            dest.unlink()
            print(f"HASH MISMATCH for {rel}: expected {expected}, got {got} -- removed", file=sys.stderr)
            ok = False
        else:
            print(f"ok: {rel}")
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and verify the local embedding model")
    parser.add_argument("--print-hashes", action="store_true")
    args = parser.parse_args()
    sys.exit(fetch(args.print_hashes))


if __name__ == "__main__":
    main()
