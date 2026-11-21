# 서울대 Reader: Korean stories you read, click and translate

This website does one thing: **you read Korean stories.** Click any word and its translation appears on the side. The stories are stored in **Firebase** (Google's free cloud database). When you finish reading a story, it joins your **read list**. Whenever you want more stories, you ask Claude to write them and publish them, and they show up on your site straight away.

This guide takes you from **nothing installed** to **a working site**, written for a complete beginner. Copy the commands exactly, one step at a time.

**What you will do**

| Part | What you get | Time |
|---|---|---|
| 1. Install the tools | Python and Node.js on your Mac | 10 min |
| 2. Get the project | The project folder, ready to use | 5 min |
| 3. Set up Firebase | Your cloud database, Google sign-in and a key for publishing stories | 25 min |
| 4. Publish the first stories | The 15 included stories in your database | 2 min |
| 5. Open the site on your computer | The site working at `localhost` | 1 min |
| 6. Put it on the internet (optional) | A web address you can open on your phone | 10 min |
| 7. Adding stories later | The part you'll do again and again | 1 min each time |

---

## Words you will see

- **Terminal**: the Mac app where you type commands. Open it with Spotlight (`⌘ Space`, type `Terminal`, press Enter).
- **Command**: a line you paste into the Terminal and run with Enter. Commands are in grey boxes in this guide.
- **Folder** = **directory**. `cd` means "go into this folder".
- **Project folder**: the folder named `Korean_Reading`. **Run every command from inside it.** If you open a new Terminal window, go back in first (Part 2b).
- **Firebase**: a free Google service. Here it holds your stories and your read list.
- **Firestore**: the database inside Firebase.
- **Story**: one text with its title, summary, list of words and grammar to learn, and a few questions.

**How to use the commands:** copy the whole grey box, paste it into the Terminal, press Enter. If something goes wrong, look at [Troubleshooting](#troubleshooting) at the end.

---

## What the site looks like

- **The front page** lists the stories by level (3A, 3B, 4A, 4B …) with a summary of each, and shows how many you have read ("3 of 15 read"). You can filter by level, and by "not read yet" or "read".
- **A story page** shows the story. Words you should learn are **green**, grammar you should learn is **orange**. There are no boxes or underlines, only colour, so it stays easy to read.
- **Click any word** and the side panel shows its translation (and the translation of the whole sentence). On a phone the panel slides up from the bottom.
- **The read list:** press **Mark as read**, or just scroll down to the end of a long story and it is added automatically ("added to your read list ✓"). Press the button again to undo it. Short stories that fit on the screen need the button.
- **Sign in with Google** (top right) saves your read list in your own private space in Firebase, so it follows you from your computer to your phone. Without signing in, the read list stays in the one browser you are using. When you sign in, what that browser already knew is added to your account.
- The **Translate to** menu changes the translation language: English (default), Uzbek, Russian or Turkish.

**About the translations:** they come from **Google Translate**, asked by your web browser when you click a word. You need internet for that. It uses the free, keyless endpoint that Google's own widgets use. That is unofficial, so Google could limit or change it. If it fails, the panel says so and gives you a link to open Google Translate yourself. Only the word or sentence you click is sent to Google.

---

## Part 1. Install the tools

**1a. Python 3.11 or newer** (used to publish stories)

```bash
python3 --version
```

If it prints `Python 3.11` or higher, you're done. If not, download the installer from https://www.python.org/downloads/ , run it, close and reopen the Terminal, and check again.

**1b. Node.js** (used for the Firebase and Vercel helper commands)

```bash
node --version
```

If it prints a version number, you're done. If it says `command not found`, download the "LTS" installer from https://nodejs.org/ , run it, and reopen the Terminal.

You do **not** need Xcode or the textbook PDFs any more.

---

## Part 2. Get the project

**2a.** Put the `Korean_Reading` folder somewhere easy, for example inside `Downloads/GitHub/`. If it is on GitHub:

```bash
cd ~/Downloads/GitHub
git clone <the address of your repository> Korean_Reading
```

**2b.** Go into the project folder (do this in every new Terminal window):

```bash
cd ~/Downloads/GitHub/Korean_Reading
```

Change the path if your folder is somewhere else. Tip: type `cd ` and drag the folder from Finder into the Terminal window.

**2c.** Install the project's Python tools. This makes a private Python environment (`.venv`) and installs what the publish script needs:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

Lots of text scrolls by; that's normal. Every Python command in this guide starts with `.venv/bin/…` so the project's own Python is used.

---

## Part 3. Set up Firebase

**What Firebase does for you:** it stores the stories (everyone who opens your site can read them, nobody can change them from the website) and each person's read list (only that person can see it). The free plan ("Spark") is plenty and needs no credit card. You need a normal Google account.

### 3a. Create the project

1. Go to https://console.firebase.google.com and sign in.
2. Click **Create a project** (or **Add project**), give it a name such as `korean-reading`, and click **Continue**.
3. Switch Google Analytics **off** (you don't need it), click **Create project**, wait, and click **Continue**.

### 3b. Turn on Google sign-in

1. In the left menu click **Build**, then **Authentication**, then **Get started**.
2. Open the **Sign-in method** tab, click **Google**, and switch **Enable** on.
3. Choose a **support email** (your own) and click **Save**.

### 3c. Create the database

1. In the left menu click **Build**, then **Firestore Database**, then **Create database**.
2. Pick a location close to you and click **Next**.
3. Choose **Start in production mode** and click **Create**. (Production mode is the safe choice; step 3e installs the right rules.)

### 3d. Copy your project's settings into the site

1. Click the **gear icon** next to *Project Overview* (top left), then **Project settings**.
2. Scroll down to **Your apps** and click the web icon **`</>`**.
3. Give it any nickname, leave "Firebase Hosting" unticked, and click **Register app**.
4. You'll see a block of code with `firebaseConfig`. You need four values from it: `apiKey`, `authDomain`, `projectId` and `appId`. Keep this page open.
5. Open the file **`public/firebase-config.js`** in a text editor (TextEdit works; VS Code is nicer). Near the bottom, find this line:

   ```js
   window.KR_FIREBASE = window.KR_FIREBASE || null;
   ```

   Replace that one line with the following and put **your four values** between the quotes:

   ```js
   window.KR_FIREBASE = {
     apiKey: "PASTE-YOUR-apiKey-HERE",
     authDomain: "PASTE-YOUR-authDomain-HERE",
     projectId: "PASTE-YOUR-projectId-HERE",
     appId: "PASTE-YOUR-appId-HERE"
   };
   ```

   Save the file.

   *Is it safe to put these in a file?* Yes. They only say "which Firebase project is this?" and are not passwords. What protects your data are the rules in the next step.

### 3e. Install the security rules (do not skip)

This sends the project's `firestore.rules` file to Firebase. Run these three commands, one at a time:

```bash
npx firebase-tools@latest login
```

A browser window opens. Sign in with the same Google account and allow access.

```bash
npx firebase-tools@latest use --add
```

Use the arrow keys to pick your project, press Enter, and type any short nickname when asked (for example `default`).

```bash
npx firebase-tools@latest deploy --only firestore:rules
```

You should see `Deploy complete!`.

The rules say: *everyone can read the stories, nobody can change them from the website, and each person can read and write only their own read list.*

### 3f. Get a key so Claude (or you) can publish stories

Adding stories to the database is done by a script on your Mac, not by the website. The script proves who it is with a **service-account key**: a small file that works like a password for your project.

1. Firebase console → **gear icon → Project settings → Service accounts** tab.
2. Click **Generate new private key**, confirm, and a `.json` file downloads.

   If that `mv` command says "No such file", find the downloaded file in Finder and drag it into the `secrets` folder, then rename it `firebase-service-account.json`.

**Keep this file private.** Anyone who has it can change your database. The project is set up so it is **never committed to Git and never uploaded to your website** (the `secrets` folder is ignored in both). Don't email it or paste it into a chat. If it ever leaks, delete the key in the same Firebase page and generate a new one.

---

## Part 4. Publish the first stories

The project comes with 15 stories (levels 3A–4B) in the folder `content/stories/`. Put them in your database:

```bash
.venv/bin/python scripts/publish_stories.py
```

It first **checks every story** (all the words and grammar are marked, nothing is broken), then uploads them. You should see a line per story starting with `OK`, and at the end:

```
published 15 stories to Firebase project 'your-project'.
```

You can look at them in the Firebase console → **Firestore Database → Data → `stories`**.

Running it again is always safe: it just overwrites the same stories.

---

## Part 5. Open the site on your computer

```bash
.venv/bin/python -m http.server 8765 --directory public
```

Open **http://localhost:8765** in your browser. (Use the word `localhost`, not `127.0.0.1`: Google sign-in only accepts `localhost`.)

You should see the list of 15 stories. Try this:

1. Click **Read** on a story.
2. Click a green word, then an orange one. The translation appears on the right.
3. Click **Sign in with Google** (top right), sign in, then press **Mark as read**.
4. In Firebase → Firestore → Data you'll now see `users → your id → read → the story`.

To stop the site, go to the Terminal and press `Ctrl C`. To start it again, open the Terminal, `cd` into the project (Part 2b) and run the command above again.

---

## Part 6. Put the site on the internet (optional)

This uses **Vercel**, a free service that hosts websites. The site is just the files in the `public` folder, so there is no server to run. After this, you can read your stories on your phone.

**6a.** Make a free account at https://vercel.com/signup, then log in from the Terminal:

```bash
npx vercel@latest login
```

**6b.** Create the project (the name must be lowercase) and publish:

```bash
npx vercel@latest link --yes --project korean-reading
npx vercel@latest deploy --prod --yes
```

At the end it prints your website address, for example `https://korean-reading-xxxx.vercel.app`.

**6c.** Tell Firebase about that address, or "Sign in with Google" will not work there:
Firebase console → **Authentication → Settings → Authorized domains → Add domain**. Type the address **without** `https://` (for example `korean-reading-xxxx.vercel.app`) and click **Add**.

**6d.** Open the address on your phone, sign in with the same Google account, and your read list is there.

**You only deploy the website again if you change the website itself** (for example `public/app.js` or the colours). **New stories do not need a redeploy**: they live in Firebase.

Useful extras:

- Undo a bad update: `npx vercel@latest ls` lists deployments; `npx vercel@latest rollback <that-address>` goes back to an older one.
- Take the site down: `npx vercel@latest remove korean-reading --confirm-name korean-reading`.
- Require a Vercel login to open it: `npx vercel@latest project protection enable korean-reading`.

---

## Part 7. Adding more stories (every time you want new ones)

**The easy way:** open this project in Claude Code and say something like:

> Write 5 new stories for level 4A about travel and shopping, and publish them.

Claude writes the story files into `content/stories/`, checks them, and runs the publish script for you. The new stories appear on your site the next time you refresh the page. You can also ask for things like "make them a bit easier", "a story about my university life", or "rewrite story 3a-02".

**What Claude needs from you:** only the key from Part 3f, saved at `secrets/firebase-service-account.json`.

**The manual way** (if you write a story yourself): add a file `content/stories/<id>.json` and run `.venv/bin/python scripts/publish_stories.py`. Useful options:

| Command | What it does |
|---|---|
| `.venv/bin/python scripts/publish_stories.py --dry-run` | Only checks the stories; publishes nothing. |
| `.venv/bin/python scripts/publish_stories.py --only 4a-05` | Publishes only stories whose id starts with `4a-05`. |
| `.venv/bin/python scripts/publish_stories.py --prune` | Also **deletes** stories from Firebase whose file you removed. |

**Removing a story:** delete its file, then run the publish command with `--prune`. (Your read list keeps the old id; it doesn't matter.)

### What a story file looks like

```json
{
  "id": "4a-05-travel",
  "level": "4A",
  "title": "...",
  "theme": "Travel",
  "summary_en": "One or two sentences in English.",
  "text": "저는 [[여행을|여행]] 갈 <<계획이에요|V+(으)ㄹ 계획이다>>. ...",
  "target_vocab": ["여행"],
  "target_grammar": ["V+(으)ㄹ 계획이다"],
  "questions": [{ "q": "질문?", "a": "대답" }]
}
```

- `id` is the file name without `.json`: lowercase letters, digits and dashes only.
- The colours are written **inside the text**: `[[shown text|word]]` makes a green word to learn, `<<shown text|pattern>>` makes an orange grammar point. The marks are removed before the story is shown.
- Every word in `target_vocab` and every pattern in `target_grammar` must be marked at least once, and every mark must refer to something in those lists. The publish script checks this and tells you exactly what's wrong, and then **publishes nothing** until it is fixed.
- Marks don't start or end with a space, and never overlap.

### Why the stories sit in a database and not in the website

Because that way a new story is one command and is live immediately for everybody, with no new version of the website to build and publish. The files in `content/stories/` stay as your master copy (and as backup).

---

## Troubleshooting

| What you see | What it means and what to do |
|---|---|
| The page says **"Firebase is not set up yet"** | `public/firebase-config.js` still says `|| null`. Do Part 3d, save, and reload the page. |
| **"Firebase refused to send the stories … rules have not been installed"** | Do Part 3e (`deploy --only firestore:rules`). |
| The page says "There are no stories yet" | Run Part 4 (`publish_stories.py`). |
| `Service-account key not found` | The key is missing or has the wrong name. Redo Part 3f; the path must be `secrets/firebase-service-account.json`. |
| `The Firebase library is missing` | Run `.venv/bin/pip install -r requirements-dev.txt` (Part 2c). |
| `No such file or directory: .venv/bin/…` | You skipped Part 2c, or you're not in the project folder. |
| The publish script prints `PROBLEM: …` and publishes nothing | A story file has a mistake. The line says which one and what. Fix that file and run it again. |
| `Permission denied` / `7 PERMISSION_DENIED` when publishing | The key belongs to a different Firebase project, or Firestore (Part 3c) was never created. |
| `Address already in use` when starting the site | Another copy is still running. Press `Ctrl C` in the other Terminal window, or use another number instead of `8765` (in the command and the address). |
| No "Sign in with Google" button | Firebase isn't set up yet (first row), or you didn't reload the page. |
| `auth/unauthorized-domain` | Add the address under Authentication → Settings → Authorized domains (Part 6c). On your computer, use `localhost`, not `127.0.0.1`. |
| `auth/operation-not-allowed` | Turn on the Google sign-in method (Part 3b). |
| The sign-in popup closes or doesn't open | Allow popups for the site and try again. |
| Signed in, but my read list is empty | You're signed in with a different Google account, or the stories were read in another browser before signing in. Sign in there once and it joins your account. |
| The translation shows an error | Google Translate is busy, blocked or you're offline. Use the link in the panel, or try again in a minute. |
| A story I published doesn't show up | Reload the page. Check the story id isn't the same as another one (the same id overwrites). |
| Vercel: "project names must be lowercase" | Use `--project korean-reading` exactly as written. |
| I changed `public/…` and the live site is unchanged | Deploy again: `npx vercel@latest deploy --prod --yes`. |

---

## For later

**The pieces.** The website is plain files in `public/` (no build step, no server): `index.html`, `app.js`, `core.js` (small helper functions), `theme.js` (the light/dark toggle), `translate.js` (Google Translate), `firebase-config.js` (your Firebase settings), `styles.css`. Stories and read lists are read and written straight from the browser to Firebase, protected by `firestore.rules`.

**What is stored where**

| Data | Where | Who can see it |
|---|---|---|
| Stories | Firestore `stories/<id>` | everyone can read; only the publish script writes |
| Your read list | Firestore `users/<your id>/read/<story id>` (signed in) or this browser (signed out) | only you |
| Translations | not stored; cached in your browser | n/a |

**Costs and limits.** The free Firebase plan allows about 50,000 document reads a day. Opening the front page reads every story once (15 reads today), so a few hundred visits a day with a few dozen stories is fine.

**Privacy.** The only outside requests the site makes are to Firebase, to Google Translate for the text you click, and to Google's servers that load the Firebase scripts. The service-account key never leaves your computer.

**Tests** (optional, for developers):

```bash
.venv/bin/python -m pytest -q
node --test tests/js/*.test.js
npm --prefix tests/firebase install
npx firebase-tools@13.35.1 emulators:exec --only firestore --project demo-kr "cd tests/firebase && node rules.test.js"
npm --prefix tests/e2e install && (cd tests/e2e && npx playwright install chromium)
npx firebase-tools@13.35.1 emulators:exec --only auth,firestore --project demo-kr "bash tests/e2e/run-site.sh"
```

The last command publishes the stories into a local Firebase emulator and drives the real site in a headless browser (34 checks: list, colours, translation panel, read list, two devices, sign-out, phone layout, security rules). No Google account is needed and Google Translate is mocked. Firebase tools version 13 needs Java 17.

**Older parts of the project.** Earlier versions of this project also had a textbook database built from your PDFs, flashcards, a grammar and workbook browser, and a Python server. The website no longer uses any of that. The code is still there if you want it: `backend/` (server and PDF importers), `scripts/build_deploy_db.py`, `scripts/check_stories.py` (checks stories against the textbook database), and the whole old web interface in `legacy/`. You can ignore these folders, or delete them if you don't need them.

**Project layout**

```
public/            the website (what Vercel serves)
content/stories/   your stories: the master copies
scripts/           publish_stories.py (check + publish), storylib.py (story format)
firestore.rules    Firebase security rules (Part 3e)
firebase.json      emulator settings for the tests
vercel.json        tells Vercel the site is just the public/ folder
secrets/           your service-account key (private, never uploaded)
tests/             automatic tests
legacy/ backend/   the earlier version (not used by the site)
```
