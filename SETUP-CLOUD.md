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

## 5. Use it
- Open the site → **Sign in** → enter your email → open the emailed link
  **on the same device**. You stay signed in on that device.
- From then on every swing and round syncs automatically (offline-first:
  data queues on the device and uploads when there's signal).
- The **Progress** tab shows tempo and club-speed trends across sessions.

## Costs & limits
Free tier: 500 MB database (thousands of sessions of metrics), 50k monthly
auth users, 1 GB file storage. No card required. Upgrade only if a whole
team adopts it.

## Later (already planned)
- Google sign-in: Authentication → Providers → Google (needs a Google Cloud
  OAuth client; nicer on shared tablets).
- Coach role + team views; raw-CSV upload to Storage for the ML corpus.
