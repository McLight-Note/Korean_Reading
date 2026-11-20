#!/bin/bash
# Run by `firebase emulators:exec` (see the README, "Tests"): publishes the stories to the emulator, serves public/ and runs the browser test.
set -e
cd "$(dirname "$0")/../.."
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 .venv/bin/python scripts/publish_stories.py --project demo-kr
.venv/bin/python -m http.server 8769 --bind 127.0.0.1 --directory public >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
for i in 1 2 3 4 5 6 7 8 9 10; do curl -s -o /dev/null http://127.0.0.1:8769/ && break; sleep 0.5; done
node tests/e2e/site.e2e.js http://127.0.0.1:8769
