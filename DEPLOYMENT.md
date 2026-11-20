# Deployment guide (Vercel)

How the public, **read-only** edition of the app is built, deployed, updated and taken down.
Current production URL: **https://korean-reading-beta.vercel.app** (Vercel project `korean-reading`).

## 1. What gets deployed

| | Local app | Vercel edition |
|---|---|---|
| Database | `data/app.sqlite` (read/write) | `deploy/app.sqlite`, bundled and opened **read-only** |
| Passages, saved words, study progress | stored in the database | stored in **each visitor's browser** (`localStorage`) |
| Editing, Review tab, imports, admin | yes | **no** (every write/admin endpoint returns 403) |
| Translation | Google Translate, requested by the visitor's browser | same (the server never calls Google) |
| Workbook exercises and listening scripts | yes | **included** (section 5) |
| Raw OCR text, page images, PDFs | yes | **never** deployed |

The deployed database is a slim copy built by `scripts/build_deploy_db.py`. It keeps the Korean vocabulary (headword, level, unit), grammar items, examples and workbook, and removes the Uzbek meanings, raw OCR columns, OCR pages and any personal tables.

**Why read-only:** Vercel functions cannot keep a writable SQLite file between requests, so nothing the server stores would survive. Vercel always runs the app in read-only mode (it sets the `VERCEL` environment variable); no configuration is needed for that.

## 2. Prerequisites (one time)

1. A Vercel account, and Node.js installed (`npx` is used so you don't need a global install).
2. Log in: `npx vercel@latest login`.
3. The textbook data already imported locally (README step 3), so `data/app.sqlite` exists.
4. The Vercel CLI must be **≥ 48.1.8** for FastAPI. `npx vercel@latest` always satisfies this. An old global `vercel` (v44 was found on this machine) does not.

Files that make the deployment work (already in the repo):

| File | Purpose |
|---|---|
| `app.py` | Vercel entrypoint; it just imports the FastAPI `app` |
| `vercel.json` | function settings (60 s max duration, excluded files) |
| `.vercelignore` | what is **not** uploaded (`.venv`, `data`, PDFs, tests, `.env*`, …) |
| `.python-version` | Python 3.12 |
| `requirements.txt` | runtime-only dependency (`fastapi`). Dev tools live in `requirements-dev.txt` |
| `public/` | the web page; Vercel serves it from its CDN |
| `content/stories/` | the reading stories (bundled into the function; served through `/api/stories`) |

## 3. First deployment

Run from the project folder:

```bash
# 1. Build the slim read-only database
.venv/bin/python scripts/build_deploy_db.py
#    (the books' content incl. workbook exercises ships by default; --exclude-workbook leaves the workbook out)

# 2. Create/link the project. The name must be lowercase.
npx vercel@latest link --yes --project korean-reading

# 3. IMPORTANT: link connects your GitHub repo. Disconnect it (see section 4 for why).
npx vercel@latest git disconnect --yes

# 4. Deploy to production
npx vercel@latest deploy --prod --yes
```

The last command prints the production URL. A brand-new project's first deployment always goes to production.

## 4. Why you must deploy from your machine, not from Git

`deploy/app.sqlite` is **git-ignored on purpose**: it contains text taken from the textbooks and should not be pushed to GitHub. A deployment triggered by a `git push` would therefore have **no database** and every data endpoint would fail.

So keep the GitHub integration **disconnected** (step 3 above) and always deploy with the CLI. If you ever see a Vercel build triggered by a push, run `npx vercel@latest git disconnect --yes` again.

## 5. What is published

The site exists to make your books usable. It ships the **15 reading stories** (`content/stories/`, written for this app) and a database that contains everything extracted from your books: vocabulary, grammar items with their original explanations and examples, and the **workbook exercises and listening scripts** (Workbook tab, exercises under each grammar item, Workbook practice in the Study tab).

- Not published: the PDFs, page images, raw OCR text, the Uzbek glosses, and anything personal (saved words, passages, study progress).
- `build_deploy_db.py --exclude-workbook` leaves the bulk workbook text out if you ever want a lighter edition.
- **Copyright:** this is verbatim text from the books, readable by anyone with the link. You decided to publish it; if that changes, use `--exclude-workbook`, enable Vercel Authentication (section 8), or take the site down (section 9).

## 5b. Visitors' data in the cloud (optional)

By default each visitor's passages and progress live in their own browser. To let people sign in with Google and have that data stored in their own private Firestore space, follow **[FIREBASE.md](FIREBASE.md)**. It needs a Firebase project, a config pasted into `public/firebase-config.js`, the security rules deployed, and a redeploy.

## 6. Updating the live site

Whenever you change code or the textbook data (for example after reviewing items in the Review tab):

```bash
.venv/bin/python -m pytest -q                      # 1. tests must pass
.venv/bin/python scripts/build_deploy_db.py        # 2. rebuild the slim DB from data/app.sqlite
npx vercel@latest deploy --prod --yes              # 3. publish
```

Visitors' passages and study progress live in their own browsers, so redeploying never touches them.

## 7. Verify a deployment

`vercel curl` works even if Deployment Protection is on. Replace the URL with the one the deploy printed:

```bash
U=https://korean-reading-beta.vercel.app
npx vercel@latest curl /api/config   --deployment $U          # expect {"read_only":true}
npx vercel@latest curl /api/overview --deployment $U          # expect your vocabulary/grammar counts
npx vercel@latest curl /api/stories  --deployment $U          # expect 15 stories
npx vercel@latest curl /api/vocab/lookup --deployment $U -- -s -X POST \
  -H 'Content-Type: application/json' -d '{"tokens":["영화를"]}'      # expect a match
npx vercel@latest curl /api/vocab --deployment $U -- -s -X POST \
  -H 'Content-Type: application/json' -d '{"headword":"x"}'           # expect 403 "read-only"
```

Then open the site in a browser and check: open a story, click a coloured word and a grammar span (the panel should show a Google translation), switch the language menu, save a word, and open the Study tab. If the translation shows an error line, Google rate-limited you; the link below it still works.

## 8. Who can open it, and how to change that

- The **production URL** (`korean-reading-beta.vercel.app`) is open to anyone with the link. Vercel's Deployment Protection only covers the per-deployment URLs (`korean-reading-<hash>-….vercel.app`).
- To require a Vercel login for the whole project: `npx vercel@latest project protection enable korean-reading`, or dashboard → Project → Settings → Deployment Protection.
- A custom domain: `npx vercel@latest domains add <your-domain> korean-reading`.

## 9. Roll back, inspect, take down

```bash
npx vercel@latest ls                                   # list deployments
npx vercel@latest rollback <deployment-url>            # point production at an earlier deployment
npx vercel@latest logs                                 # recent function logs (errors, timeouts)
npx vercel@latest remove korean-reading --confirm-name korean-reading   # delete the deployments; the site stops working
```

To delete the project completely, use the dashboard (Project → Settings → Delete Project).

## 10. Limits and costs

- Function bundle: a few MB (FastAPI, the 1.7 MB database and the stories), so cold starts are short.
- The server does no heavy work (database reads, the small stateless lookup and scheduling calls). Google Translate load is carried by each visitor's browser, not by your plan.
- Maximum function duration is set to 60 s in `vercel.json`.

## 11. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Project names … must be lowercase` | Use `--project korean-reading` with `vercel link` (the folder name has capitals). |
| Every API call returns 500 after a Git-triggered deploy | The database is not in Git. Disconnect Git (`git disconnect`) and deploy from your machine. |
| `read-only database not found … build_deploy_db.py` | Run `build_deploy_db.py` before deploying. |
| Deploy says FastAPI needs a newer CLI | Use `npx vercel@latest`, not an old global `vercel`. |
| First request is slow or times out | Cold start. Retry; check `npx vercel@latest logs`. |
| Panel says it couldn't reach Google Translate | The unofficial endpoint was blocked or rate-limited for that visitor; it is requested by the browser, not by your server. The panel links to translate.google.com. |
| Workbook tab missing on the live site | The deployed database was built with `--exclude-workbook`, or not rebuilt. Run `build_deploy_db.py` and redeploy. |
| Browser shows old passages/progress | They are stored per browser; clearing site data in that browser removes them. |
| Changes made locally don't appear online | You must rebuild the DB and redeploy (section 6); the live site never reads your local `data/`. |

## 12. Checklist before announcing the link

- [ ] `pytest` passes and you rebuilt `deploy/app.sqlite` from the latest data
- [ ] You are comfortable publishing the books' content, including the workbook (section 5)
- [ ] `vercel curl` checks in section 7 behave as described
- [ ] The GitHub integration is disconnected
- [ ] You know how to roll back or take the site down (section 9)
