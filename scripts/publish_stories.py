"""Check the stories in content/stories/ and publish them to Firebase (Firestore collection `stories`).

    .venv/bin/python scripts/publish_stories.py                 check everything, then publish all stories
    .venv/bin/python scripts/publish_stories.py --only 4a-05    only stories whose id starts with this
    .venv/bin/python scripts/publish_stories.py --dry-run       check only, publish nothing (needs no key and no Firebase)
    .venv/bin/python scripts/publish_stories.py --prune         also delete stories from Firebase that no longer have a file

Publishing needs a service-account key (README, Part 3f): by default secrets/firebase-service-account.json, or the path in
--key / the GOOGLE_APPLICATION_CREDENTIALS environment variable. The key is private: it is git-ignored and never deployed.
With FIRESTORE_EMULATOR_HOST set (automatic tests) no key is needed. Publishing again simply overwrites: it is safe to repeat.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import storylib  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEY = ROOT / "secrets" / "firebase-service-account.json"


def check(prefix: str) -> list[dict]:
    """Load and check the stories; exits with status 1 and a list of problems when something is wrong."""
    stories, bad = [], 0
    for path in sorted(storylib.STORIES_DIR.glob("*.json")):
        try:
            s = storylib.load_file(path)
        except Exception as e:                        # broken JSON or a missing field
            print(f"!! {path.name}: {e}")
            bad += 1
            continue
        if not s["id"].startswith(prefix) and not path.stem.startswith(prefix):
            continue
        probs = storylib.problems(s, path.stem)
        marks = len(s["highlights"])
        print(f"{'OK ' if not probs else '!! '}{s['id']:24} [{s['level']}] {len(s['text']):4} chars, {marks:3} marks, "
              f"{len(s['target_vocab'])} words, {len(s['target_grammar'])} grammar")
        for p in probs:
            print("     PROBLEM:", p)
        bad += bool(probs)
        stories.append(s)
    if bad:
        raise SystemExit(f"\n{bad} story file(s) have problems. Nothing was published.")
    ids = [s["id"] for s in stories]
    if len(ids) != len(set(ids)):
        raise SystemExit("two stories share the same id. Nothing was published.")
    return stories


def client(key: str | None, project: str | None):
    try:
        from google.cloud import firestore
    except ImportError:
        raise SystemExit("The Firebase library is missing. Run:  .venv/bin/pip install -r requirements-dev.txt")
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        from google.auth.credentials import AnonymousCredentials
        return firestore.Client(project=project or os.environ.get("GCLOUD_PROJECT") or "demo-kr", credentials=AnonymousCredentials()), firestore
    path = Path(key or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or DEFAULT_KEY)
    if not path.is_file():
        raise SystemExit(f"Service-account key not found: {path}\n"
                         "Download it in the Firebase console (Project settings → Service accounts → Generate new private key) "
                         f"and save it as {DEFAULT_KEY.relative_to(ROOT)} (README, Part 3f).")
    return firestore.Client.from_service_account_json(str(path)), firestore


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="publish only stories whose id starts with this")
    ap.add_argument("--dry-run", action="store_true", help="check the stories, publish nothing")
    ap.add_argument("--prune", action="store_true", help="delete stories from Firebase that no longer have a file")
    ap.add_argument("--key", help="path to the service-account key (default: secrets/firebase-service-account.json)")
    ap.add_argument("--project", help="Firebase project id (only needed with the emulator)")
    args = ap.parse_args(argv)

    stories = check(args.only)
    if not stories:
        raise SystemExit("no stories matched")
    if args.dry_run:
        print(f"\n{len(stories)} stories are fine (dry run: nothing published).")
        return 0

    db, firestore = client(args.key, args.project)
    col = db.collection("stories")
    for s in stories:
        doc = storylib.firestore_doc(s)
        doc["updatedAt"] = firestore.SERVER_TIMESTAMP
        col.document(s["id"]).set(doc)
    print(f"\npublished {len(stories)} stories to Firebase project '{db.project}'.")

    local_ids = {p.stem for p in storylib.STORIES_DIR.glob("*.json")}
    extra = sorted(d.id for d in col.stream() if d.id not in local_ids)
    if extra and args.prune and not args.only:
        for sid in extra:
            col.document(sid).delete()
        print(f"deleted {len(extra)} story(ies) that have no file any more: {', '.join(extra)}")
    elif extra:
        print(f"note: {len(extra)} story(ies) in Firebase have no file here: {', '.join(extra)}  (add --prune to delete them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
