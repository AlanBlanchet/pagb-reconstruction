# GitHub issue reporting: attaching log files from a distributed desktop app

Researched 2026-07-21. Context: PySide6 app (repo AlanBlanchet/pagb-reconstruction)
distributed via GitHub Releases. Current "Report Bug" button opens
`https://github.com/.../issues/new?body=...` with the log inlined in the URL.
Question: attach the session log file to the issue instead.

## 1. Can a URL parameter attach a file to a new GitHub issue?

No. Confirmed. `issues/new` accepts `title`, `body`, `labels`, `assignee`,
`milestone`, `template`, `projects` as query params (see
`sindresorhus/new-github-issue-url` and GitHub community discussions #15477,
#22946, #47461) — no attachment/file param exists. File attachments are added
only via drag-and-drop, the paperclip/file picker, or clipboard paste, all of
which require a loaded, interactive issue-comment textarea — not reachable via
a URL query string. Long bodies via `body=` also silently truncate in some
clients (community discussion #22946), which is an extra reason to keep the
body short and attach the log separately.
Source: https://github.com/sindresorhus/new-github-issue-url (accessed 2026-07-21);
https://github.com/orgs/community/discussions/15477 (2026-07-21);
https://github.com/orgs/community/discussions/22946 (2026-07-21).

## 2. Drag-and-drop attachment file types accepted (2026)

Confirmed .log, .txt, .zip, .gz all accepted today. GitHub expanded the
allow-list on 2025-08-14 (github.blog changelog). Current list per
docs.github.com "Attaching files" page (accessed 2026-07-21):

- Text/data: `.txt, .md, .csv, .tsv, .log, .json, .jsonc, .copilotmd`
- Archives: `.zip, .gz, .tgz`
- Images/media: `.png, .gif, .jpg/.jpeg, .svg, .mp4, .mov, .webm, .bmp, .tif/.tiff, .mp3, .wav`
- Documents: `.pdf, .docx, .pptx, .xlsx, .xls, .xlsm, .odt/.fodt, .ods/.fods, .odp/.fodp, .odg/.fodg, .odf, .rtf, .doc`
- Code: `.c, .cs, .cpp, .css, .html, .htm, .java, .js, .php, .py, .sh, .sql, .ts, .tsx, .xml, .yaml, .yml`
- Misc: `.drawio, .dmp, .ipynb, .patch, .cpuprofile, .pdb, .debug, .msg, .eml`

Size limits: images/GIFs 10MB; video 10MB (free) / 100MB (paid plans); **all
other files (including .log/.zip/.gz) 25MB**. Uploads are served from GitHub's
user-attachments CDN (anonymized URL inserted into the textarea) — this is a
DOM/upload-API interaction, not a URL-prefill mechanism, so it requires either
a human dragging the file into the browser textarea, or the GitHub REST API
(`POST /repos/{owner}/{repo}/issues` with the asset uploaded first via the
attachments API path used by the web UI — note: as of this research there is
no simple public documented single-call REST endpoint for the anonymous
attachment CDN outside the web UI's own JS; the supported programmatic route
is the Issues API body text, not this CDN).
Source: https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files (accessed 2026-07-21);
https://github.blog/changelog/2025-08-13-expanded-file-type-support-for-attachments-across-issues-pull-requests-and-discussions/ (published 2025-08-14, accessed 2026-07-21).

## 3. Anonymous/tokenless upload paths

- **Anonymous Gist creation: removed.** GitHub disabled it 2018-03-19 19:00 UTC,
  citing spam. All gists (including single-file pastes) now require an
  authenticated account. Confirmed via GitHub's own blog post.
  Source: https://blog.github.com/2018-03-20-removing-anonymous-gist-creation/ (accessed 2026-07-21).
- **No other tokenless GitHub upload path found.** The web drag-and-drop
  attachment flow itself requires being logged in and viewing an issue/PR/
  discussion compose form — it is not anonymous, just not API-token-based (it
  rides the browser session cookie).
- **REST API issue creation requires auth**, confirmed:
  `POST /repos/{owner}/{repo}/issues` needs a token (PAT, OAuth token, or GitHub
  App installation/user token) with `issues: write` (fine-grained) or
  `public_repo`/`repo` (classic OAuth scope) permission. No anonymous/unauthenticated
  path exists for creating an issue via API on any repo, public or private.
- **Body length limit: 65536 characters**, confirmed, GitHub-wide (issues, PRs,
  comments) — enforced on the gzipped payload size passed to the API, not raw
  char count (so a much longer body can still fit if it compresses well), but
  the literal ceiling and error text is "Body is too long (maximum is 65536
  characters)".
  Source: https://github.com/orgs/community/discussions/41331 (accessed 2026-07-21);
  multiple corroborating tool-issue reports (renovatebot/renovate#14551,
  changesets/action#174) all citing the identical 65536 ceiling, 2026-07-21.

## 4. OAuth Device Flow for a distributed desktop app

**Embedding `client_id` in a shipped binary is standard and safe** — because
`client_id` is not a secret. GitHub's own docs: "For the device flow, you must
pass your app's client ID... The `client_secret` is not needed for the device
flow." Device flow is explicitly one of the two scenarios (native/CLI/headless
apps) GitHub designed OAuth Apps' device flow for; best-practice doc frames
device flow as intended "unless you are using the app in a constrained
environment (CLIs, IoT devices, or headless systems)" — a desktop app qualifies.
Confirmed via two independent GitHub Docs pages (both accessed 2026-07-21):
- https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/best-practices-for-creating-an-oauth-app
- https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps

Caveat GitHub itself states: device flow has no redirect URI, so a malicious
actor could reuse a public client_id to run a phishing-style device-flow
prompt impersonating the app; this is an accepted tradeoff for headless/native
apps, not a reason to avoid it here.

**Scope needed to create an issue on a public repo:**
- Classic OAuth App scope: `public_repo` (read/write code, issues, commit
  statuses, projects, collaborators for PUBLIC repos only — no access to
  private repos). Confirmed current in 2026 docs.
- Modern alternative: **GitHub App with fine-grained `Issues: write`
  permission**, also supporting device flow as of the 2025-07-14 PKCE
  changelog and the "Generating a user access token for a GitHub App" docs
  page (device flow must be explicitly enabled in the App's settings). GitHub
  docs explicitly recommend GitHub Apps over OAuth Apps for new integrations
  ("Consider building a GitHub App instead of an OAuth app... fine-grained
  permissions instead of scopes").
  Source: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps (accessed 2026-07-21);
  https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app (accessed 2026-07-21);
  https://github.blog/changelog/2025-07-14-pkce-support-for-oauth-and-github-app-authentication/ (published 2025-07-14, accessed 2026-07-21).

**Works with zero backend/server component: confirmed.** All three device-flow
steps are plain HTTPS calls the desktop app itself makes directly to
`github.com/login/device/code` and polls
`github.com/login/oauth/access_token` — no redirect URI, no callback listener,
no app-owned server. The one point of confusion in generic docs ("your
application must be able to make HTTP POST requests") refers to the desktop
app process itself acting as the HTTP client, not a hosted server — this
matches how `gh` CLI and Git Credential Manager already do it with zero
server infrastructure.

## 5. Prior art: desktop apps reporting bugs to GitHub with attached logs, no server

No widely-documented case study found combining (a) OAuth/GitHub-App device
flow auth, (b) automated issue creation via REST API, and (c) log-file
attachment, all with zero backend. Two adjacent, well-established patterns
exist instead, and no counter-evidence surfaced after multiple search rounds
(rounds: prior-art phrased 3 ways, Sentry/Electron ecosystem, Octokit device-flow
libraries) — treat absence as genuine, not a search gap:

- **Manual pattern (most common today, zero engineering):** app opens a
  prefilled `issues/new?title=&body=` URL (what this app already does) and
  tells the user to drag the log file into the browser compose box themselves.
  This is what the current button already does minus the drag-in instruction —
  cheapest fix is adding a "your log is at `<path>`, please attach it" hint
  and shortening/removing the inlined body dump.
- **Automated pattern used by CLI/devtool ecosystems:** `gh` CLI and Git
  Credential Manager use OAuth device flow with zero server, proving the
  no-server constraint is achievable; but neither is a "report bug with log"
  feature — they authenticate for general git/gh operations. `octokit/
  auth-oauth-device.js` is the reusable library implementing exactly the
  device-flow client-side logic (device code request → user code display →
  poll) that a PySide6 app would need to port or shell out to (or reimplement
  in Python — the raw protocol is 2 HTTP calls, no SDK dependency required).
- **Crash-reporting SDKs (Sentry-Electron etc.)** solve "report bug with
  diagnostic data automatically" but route to Sentry's own hosted backend, not
  GitHub Issues — not directly reusable for a "file a GitHub issue" requirement
  without adding a Sentry-to-GitHub bridge (Sentry's GitHub integration exists
  but needs a Sentry account + org GitHub App install, i.e. a heavier stack than
  this app's constraint of "no server component I run").

## Recommendation ranking

1. **Best fit for a distributed OSS desktop tool with no server budget:**
   implement GitHub OAuth (App, not classic OAuth App — fine-grained
   `issues: write`) **device flow**, authenticated once, then call
   `POST /repos/{owner}/{repo}/issues` directly from the desktop app with a
   short body plus a **note that the log is attached** — but since the API has
   no attachment-upload endpoint outside the web UI's own JS, the practical
   attachment mechanics are either (a) inline the log's tail (fits under
   65536 chars, cheap, no upload plumbing) or (b) fall back to option 2 below
   for the raw file. A ~25-40KB log easily fits inline as a collapsible
   `<details>` block in the body — likely simplest overall for this app's size
   of logs; confirm typical session log size before committing to this path.
2. **Cheapest, zero-auth fallback (recommended default given effort/value):**
   keep the prefilled `issues/new?title=&body=` URL flow, drastically shorten
   the inlined body (short summary + version + OS, no full log dump — avoids
   the URL-length/truncation issue found in #22946), and have the app
   **copy the log file path to clipboard / reveal it in file manager** with an
   instruction to drag it into the opened issue's comment box. Zero auth flow,
   zero API calls, matches the "manual" prior-art pattern, and .log is
   confirmed accepted (Q2) at 25MB — comfortably above any plausible session
   log size.
3. **Full automation with device flow + inline log** (combining 1 above) is
   the only path that removes the manual drag-and-drop step entirely; worth
   the added device-flow implementation only if bug-report friction is a
   measured problem, since it adds a one-time GitHub App registration + OAuth
   flow the user must complete once per machine.
