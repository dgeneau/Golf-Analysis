-- Garmin Phase-0 pilot: raw swing segments uploaded straight from the watch.
-- Anon key may INSERT only — it can contribute data but never read it back,
-- so shipping the publishable key inside the watch app stays safe.
-- Idempotent; safe to re-run in the Supabase SQL editor.

create table if not exists public.garmin_pilot (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  device text,
  part text,
  rate_hz int,
  has_gyro boolean,
  cols int,              -- payload is a flat list; reshape by this many columns
  n int,                 -- sample count
  payload jsonb          -- flat [ax,ay,az,gx,gy,gz,...] accel mG, gyro deg/s
);

-- If the table already existed without `cols` (first migration), add it.
-- A POST naming a column the table lacks is what returns HTTP 400.
alter table public.garmin_pilot add column if not exists cols int;

alter table public.garmin_pilot enable row level security;

-- Anon may insert (contribute data) but has no select/update/delete policy,
-- so the publishable key can write one-way and never read back.
grant insert on public.garmin_pilot to anon;

drop policy if exists garmin_pilot_insert on public.garmin_pilot;
create policy garmin_pilot_insert on public.garmin_pilot
  for insert to anon with check (true);
