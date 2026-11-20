# Cloud storage with Firebase (optional)

By default the deployed site keeps each visitor's passages, saved words and study progress **in their own browser**. With Firebase configured, a visitor can **Sign in with Google** and the same data is stored in **their own private space in Firestore**, so it follows them across devices and survives clearing the browser.

Without the setup below nothing changes: the sign-in button stays hidden and no Google scripts are loaded.

## What is stored, and what is not

| Stored in Firestore (per signed-in user) | Path |
|---|---|
| Passages (title + text) | `users/{uid}/passages/{id}` |
| Saved words / grammar | `users/{uid}/saved/{kind}_{id}` |
| Study progress: read-state, questions, flashcards and review history | `users/{uid}/study/{meta, cards_0…15, log_YYYY-MM, ex_YYYY-MM}` |

- **Only your text is stored.** A passage is the title and text; the textbook word colouring is recomputed when it opens.
- **The textbook data is not in Firestore.** Vocabulary, grammar, examples and workbook content ship inside the site (the bundled read-only database). Corrections you make in the local Review tab still go: edit locally → rebuild → redeploy ([DEPLOYMENT.md](DEPLOYMENT.md)).
- A signed-out visitor still uses browser storage. When someone signs in for the first time and their account is empty, the app offers to upload what their browser already holds (the browser copy is kept).

## 1. Create the Firebase project (about 10 minutes, one time)

1. Open https://console.firebase.google.com → **Add project**. The free **Spark** plan is enough. Google Analytics is not needed.
2. **Build → Authentication → Get started → Sign-in method → Google → Enable** (choose a support email → Save).
3. **Authentication → Settings → Authorized domains → Add domain**: add your site's domain, e.g. `korean-reading-beta.vercel.app` (and any custom domain). `localhost` is already allowed. *Without this, sign-in fails with `auth/unauthorized-domain`.*
4. **Build → Firestore Database → Create database** → pick a location near you → **Production mode**.
5. **Project settings (gear) → General → Your apps → Web (`</>`) → register the app** → copy the `firebaseConfig` object.

## 2. Put the config into the site

Edit [public/firebase-config.js](public/firebase-config.js):

```js
window.KR_FIREBASE = {
  apiKey: "AIza…", authDomain: "your-project.firebaseapp.com", projectId: "your-project", appId: "1:…:web:…"
};
```

These values are **public identifiers, not secrets**; anyone can see them in the page source. What protects the data is the security rules in the next step.

## 3. Deploy the security rules (do not skip)

The rules in [firestore.rules](firestore.rules) let a signed-in user read and write **only** `users/<their own uid>/…`, cap a passage at 20,000 characters, whitelist the fields, and close every other path.

```bash
npx firebase-tools@latest login
npx firebase-tools@latest use --add          # choose your project (creates .firebaserc)
npx firebase-tools@latest deploy --only firestore:rules
```

(Alternative: paste the contents of `firestore.rules` into Console → Firestore → Rules → Publish.)

> If you created the database in *test mode* instead of production mode, deploy these rules anyway: test mode leaves the database open to everyone.

## 4. Redeploy the site

```bash
.venv/bin/python scripts/build_deploy_db.py
npx vercel@latest deploy --prod --yes
```

## 5. Check that it works

1. Open the site → the header shows **Sign in with Google to sync** → sign in.
2. Paste a passage, click a word and save it, grade a flashcard.
3. Open the site in a **different browser (or phone)**, sign in with the same account → the passage, saved word and progress are there.
4. In the Firebase console → Firestore you will see `users/<uid>/passages`, `saved`, `study`.

## Security notes

- Every Google account can sign in and store data under its own uid (up to your Firebase quota). Nobody can read another user's documents; this is enforced by Firestore, not by the app, and is covered by an automated rules test (below).
- Stored passages are plain text in Google's database. Treat them like any cloud note-taking app. Do not paste anything sensitive.
- To limit abuse of a public site you can enable **App Check** and set a **billing budget alert** (the Spark plan has hard free quotas and no charges).
- The Firebase scripts are loaded from Google's CDN (`gstatic.com`), pinned to version 10.14.1.

## Quotas and cost (Spark plan; check Google's current limits)

Roughly 1 GiB stored, 50,000 document reads and 20,000 writes per day. One study session reads at most about 20 documents; opening the reader lists up to 300 passages (one read each). One person's use stays far below the free limits.

## Testing (no Google account needed)

The repository tests everything against the Firebase **emulators**, including the real SDK in a real headless browser:

```bash
# 1. Pure logic (how study progress is split into documents)
node --test tests/js/*.test.js

# 2. Security rules against the Firestore emulator
npm --prefix tests/firebase install
npx firebase-tools@13.35.1 emulators:exec --only firestore --project demo-kr "node tests/firebase/rules.test.js"

# 3. End to end: real browser + real SDK + Auth/Firestore emulators (sign-in, migration, two devices, isolation, delete)
npm --prefix tests/e2e install && (cd tests/e2e && npx playwright install chromium)
KR_READ_ONLY=1 KR_DB_PATH=deploy/app.sqlite .venv/bin/uvicorn backend.app.main:app --port 8768 &      # the read-only app
npx firebase-tools@13.35.1 emulators:exec --only auth,firestore --project demo-kr "node tests/e2e/firebase.e2e.js http://localhost:8768"
```

`firebase-tools` 13 runs on Java 17; newer releases need Java 21. `public/firebase-config.js` can also be pre-set by a page or test (`window.KR_FIREBASE = {…, emulator: {auth, firestore}}`) to point the app at the emulators.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| No sign-in button | `public/firebase-config.js` is still `null`, or the site was not redeployed after editing it. |
| `auth/unauthorized-domain` | Add the site's domain under Authentication → Settings → Authorized domains (step 1.3). |
| `auth/operation-not-allowed` | Enable the Google provider (step 1.2). |
| Popup closes or is blocked | Allow popups for the site and try again. |
| "Missing or insufficient permissions" / `permission-denied` | The rules were not deployed (step 3), or you are signed out. |
| Signed in but data looks empty | You are on a different Google account, or the first-sign-in upload prompt was declined (the data is still in the original browser). |
