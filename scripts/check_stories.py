"""Quality report for the reading stories.

    python scripts/check_stories.py            # all stories
    python scripts/check_stories.py 3a-01      # stories whose id starts with this

Checks, without any NLP: every declared target word/grammar pattern is marked at least once in the text with the
inline markup ([[surface|word]] / <<surface|pattern>>), every mark refers to a declared target, every target exists in
the textbook database, marks do not overlap and no markup is left unparsed. Exit code 1 if any story has a problem.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import db  # noqa: E402
from backend.app.services import stories  # noqa: E402


def main(argv) -> int:
    prefix = argv[0] if argv else ""
    bad = 0
    with db.session() as conn:
        for s in stories.load_all():
            if not s["id"].startswith(prefix):
                continue
            r = stories.check(conn, s)
            bad += bool(r["problems"])
            print(f"{'OK ' if not r['problems'] else '!! '}{r['id']:20} [{r['level']}] {r['chars']:4} chars, {r['marks']:3} marks "
                  f"({sum(r['vocab'].values())} word, {sum(r['grammar'].values())} grammar)")
            for p in r["problems"]:
                print("     PROBLEM:", p)
    print(f"\n{bad} stories with problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
