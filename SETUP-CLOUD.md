# Cloud setup (Supabase free tier) — one-time, ~10 minutes

Accounts + history for SwingCoach: sign-in, automatic session sync, and the
Progress view. The app works fine without this; until it's configured, the
cloud features simply stay hidden.

## 1. Create the project
1. Go to **supabase.com** → Sign up (GitHub login is easiest) → **New project**.
2. Organization: personal is fine. Name: `swingcoach`.
3. **Region: Canada (Central)** — keeps athlete data in Canada.
4. Database password: generate one and store it in a password manager
   (you rarely need it — it's for direct DB access, not the app).
5. Wait ~1 minute for the project to provision.

## 2. Create the tables
1. Left sidebar → **SQL Editor** → **New query**.
2. Paste the entire contents of `supabase/schema.sql` from this repo → **Run**.
   You should see "Success. No rows returned."

## 3. Point auth at the app
1. Left sidebar → **Authentication → URL Configuration**.
2. Set **Site URL** to your GitHub Pages URL
   (e.g. `https://dgeneau.github.io/Golf-Analysis/`) — sign-in links redirect here.

## 4. Wire the app to the project
1. Left sidebar → **Settings (gear) → API**. Copy two values:
   - **Project URL** (like `https://abcd1234.supabase.co`)
   - **anon / public key** (long string starting `eyJ…`)
   The anon key is *publishable* — safe to ship in the page; row-level
   security in the database is what protects each golfer's data.
2. Put them into `swingcoach/dashboard.html` in the `CLOUD` object near
   the top of the script, then rebuild and deploy:

   ```bash
   python scripts/build_web.py
   git add -A && git commit -m "Enable cloud sync" && git push
   ```

## 5. Put the 6-digit code in the sign-in email (needed for the iPhone app)
Magic links tapped in Mail open Safari, not the app, so the iPhone app signs
in with a **6-digit code** from the same email instead.

Supabase now requires **custom SMTP** before email templates can be edited
(the Source tab is read-only on the built-in sender). Setting up SMTP also
removes the built-in sender's ~2 emails/hour limit.

1. **Get SMTP credentials.** Easiest is Gmail: in a Google account turn on
   2-Step Verification, then Security → **App passwords** → generate one.
   (Alternative: Brevo free tier, 300/day, verified sender only —
   host `smtp-relay.brevo.com`, port 587.)
2. In Supabase: **Authentication → Emails** → banner → **Set up SMTP**.
   Gmail values: host `smtp.gmail.com`, port `465`, username = your Gmail
   address, password = the app password, sender = same address,
   sender name `SwingCoach`. Save.
3. Still in **Authentication → Emails**, open the magic-link template
   ("Send a one-time sign-in link or one-time password") and switch the
   Body box from **Preview** to **Source** (top right). Set the body to:

   ```html
   <h2>Sign in to SwingCoach</h2>
   <p>Your sign-in code: <strong style="font-size:24px">{{ .Token }}</strong></p>
   <p>Or open this link on the same device: <a href="{{ .ConfirmationURL }}">Sign in</a></p>
   ```

   (`{{ .Token }}` is the one-time code; keeping `{{ .ConfirmationURL }}` too
   means the same email still works as a click-through link in the browser.)
4. Save the template.

## 6. Use it
- **Browser:** open the site → **Sign in** → enter your email → open the
  emailed link **on the same device**. You stay signed in on that device.
- **iPhone app:** Session summary → **Account** → enter your email →
  **Email code** → type the 6-digit code from the email. You stay signed in.
- From then on every swing and round syncs automatically (offline-first:
  data queues on the device and uploads when there's signal).
- The **Progress** tab shows tempo and club-speed trends across sessions.

## Migrations (existing projects)
If your project was created before a schema change, run the migration files in
`supabase/` the same way as step 2 (SQL Editor → paste → Run). Currently:
- `migration-round-analytics.sql` — adds course identity to round sessions and
  par to holes, powering the Progress tab's Round analytics (fairways, GIR,
  distances over time, strokes gained). Safe to run more than once.

## Costs & limits
Free tier: 500 MB database (thousands of sessions of metrics), 50k monthly
auth users, 1 GB file storage. No card required. Upgrade only if a whole
team adopts it.

## Later (already planned)
- Google sign-in: Authentication → Providers → Google (needs a Google Cloud
  OAuth client; nicer on shared tablets).
- Coach role + team views; raw-CSV upload to Storage for the ML corpus.
