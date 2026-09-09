# erganiOS Card Scanner PWA

Entry point: `/scanner/`. Runs in the existing Flask application, with a separate
scanner session and no office/admin login. No App Store / Google Play package.

## Implemented flow

- Authenticate configured `web_username` through Ergani API (usertype 02 and
  EX_BASE_01 employer verification), or configured portal `username` through the
  existing portal login flow, including EFKA users. Only stores mapped to the
  verified account are offered. Submissions still use the store's web/API account.
  No arbitrary employer/branch ids from the browser.
- Right-side hamburger menu shows store details without a store selector.
  The first configured matching store is used for a new login.
  The menu displays the official `karta_employer.eponimia`, AFM, branch description
  and the configured **portal `username`**, not the web/API account.
  “Τελ. συγχρ.” shows the latest card event time for this branch, considering both
  synchronized work-log punches and successful local card declarations. It is not
  the background job execution time. Details refresh whenever the menu opens.
- Choose arrival/departure, camera scan (vendored jsQR 1.4.0), branch roster check,
  confirmation, submission through existing `_submit_work_card`, preserving the
  store's listener/direct routing and existing card guards.
- Αποστολές: latest punches from **karta_work_log**, including other sources,
  20 per page, previous/next arrows without page counts. The scanner's former
  date-filtered history and manual sync endpoints have been removed. Existing
  erganiOS background synchronization remains the source of updates.
- Εκκρεμείς: separate tab and count of local unconfirmed submissions, with retry,
  late reason selection and explicit unknown-result handling.
- Local IndexedDB outbox records intent before sending. Replays reuse request id.
  Server SQLite commits intent before the upstream call and stores the response.
  Unknown upstream outcomes are not automatically submitted again.
- Late events require an explicit reason. The existing
  erganiOS card validation still applies; the scanner does not bypass it.
- PIN protects only the Αποστολές view for the current scanner login (12 hours), with
  short server unlock and rate limiting. New login requires setting PIN again.
- App shell only is cached. No history, passwords, tokens or API responses in the
  service worker cache. Local outbox contains scanned data; protect shared devices.

## Connectivity and manual synchronization

- A fresh `/scanner/api/connectivity` request runs every 30 seconds while visible,
  at startup, on network restoration and on return to the application. Timeout is
  5 seconds; nonce validation and `no-store` prevent cached success responses.
- Online means that the **erganiOS server is reachable**, not that Ergani or the
  database is available. On localhost it does not prove internet access.
- Automatic pending submission runs every 60 seconds while the page is running,
  and after connectivity is restored. The original request id is reused.
- The menu “Συγχρονισμός” submits eligible pending
  events. Empty queue: “Δεν βρέθηκαν δηλώσεις προς υποβολή.” A result dialog includes
  date/time and OK. Offline, late, failed and uncertain outcomes stay visible in
  Εκκρεμείς; reasons and reconciliation are not bypassed.

## Appearance

- Shared official erganiOS logo on login, main header and drawer; primary blue
  `#1062fe`, white Online/Offline badge with blue text.
- Header contains the Online/Offline indicator next to the hamburger menu;
  synchronization is available only inside the drawer.
- Returning from another app resets the view, title and selected menu item to
  Αρχική together and closes the drawer/camera.
- Installation icons use the existing erganiOS symbol on white: 192/512px regular
  icons, 180px Apple touch icon and a separate 512px maskable Android icon with
  safe padding. Existing installations may need re-adding to update their icon.
- CardScanner heading and bilingual Clock-in / Clock-out labels.
- Ministry logo on login and scanner home uses the supplied remote image with
  CSS multiply blending to visually remove its white background. The JPEG itself
  is not an alpha-transparent asset and requires network access to load.
- Service worker v4 replaces old shell caches and refreshes successful cached
  shell responses. Business data and API responses are excluded.
- Πλαϊνό μενού σε κινητό: στενότερο (~78vw / max 300px) και μικρότερα γράμματα
  (επωνυμία ~15px, στοιχεία ~12px, στοιχεία μενού ~14px).

## Verification

Final regression run (2026-09-09): **76 passed** across scanner, access control,
audit logging, card delay reasons and card guards. JavaScript syntax checks passed.

`python -m pytest tests/test_scanner.py -q` covers authentication, branch isolation,
portal login display, PIN, paging, connectivity, idempotency and late submissions.
`tests/scanner_browser_smoke.cjs` uses Playwright against localhost:5051 with mocked
business endpoints and submissions; it exercises offline/reconnect, pending count,
manual sync, navigation, PIN scope and responsive layouts. Set `NODE_PATH` to the
installed Playwright package directory before running it with Node.

Read-only live checks verified existing portal-account login, company details and
two pages of database punches. No real card submission was made by these checks.

## Deployment

Local preview using the existing `.env` configuration, without the debugger:

```powershell
python -c "from run import app; app.run(host='127.0.0.1',port=5051,debug=False,threaded=True)"
```

Open `http://localhost:5051/scanner/`. A local preview still uses the configured
store's Ergani environment; it is not a demo mode. Camera testing from a phone
requires an HTTPS origin accessible to that phone.

Serve over HTTPS through the existing site. Icons and manifest are under
`app/static/scanner/`; SW scope is `/scanner/`. Η ενότητα «Εγκατάσταση στη συσκευή»
δεν εμφανίζεται πλέον στις Ρυθμίσεις του UI.

Grant the application identity write access to Flask's `instance/` directory.
`SCANNER_DB_PATH` may be supplied in Flask config to override `instance/scanner.sqlite3`.
This SQLite file holds scanner sessions, rate limits and submission deduplication,
not the business history. Back it up and keep it on persistent local storage.
Multiple processes on the same host share it; multiple hosts require a shared
transactional store implementation before deployment. Never expose the file via IIS.

Use one stable HTTPS origin (`PUBLIC_BASE_URL`, π.χ. `https://erganios.gr`).
POST requests require `X-Scanner-Request: 1` and, when `Origin` is present, it must
match either that public base URL or the Flask `host_url` (loopback behind IIS is
accepted via `PUBLIC_BASE_URL`). No automated production submissions were
performed during implementation.

## Device acceptance checks still required

1. Real Ergani login for a configured web user; verify permitted branches.
2. Actual issued employee QR: the current decoder expects an unambiguous nine-digit
   AFM matching the active branch roster. An opaque/encoded QR format must be
   handled explicitly if encountered; unknown/ambiguous values are rejected.
3. iPhone Safari standalone and Android Chrome camera, front/back camera and torch
   where supported. jsQR is bundled, with no runtime CDN dependency.
4. Scan online, network loss after confirmation, app restart and same-id replay;
   reconcile unknown results against Ergani before a fresh scan.
5. Offline scanning works while an authenticated page/store remains open; an
   offline cold start does not restore authenticated access or roster data.
6. Shared devices: PIN, backgrounding, logout, session expiry, outbox visibility.
7. Compare history dates, multiple shifts and overnight exits with the existing UI.

The application must be open for retry execution. Mobile background execution is
not assumed. Its local record is never presented as a confirmed Ergani submission.
