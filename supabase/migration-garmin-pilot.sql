-- Garmin Phase-0 pilot: raw swing segments uploaded straight from the watch.
-- Anon key may INSERT only — it can contribute data but never read it back,
-- so shipping the publishable key inside the watch app stays safe.
-- Idempotent; run in the Supabase SQL editor.

create table if not exists public.garmin_pilot (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  device text,
  part text,
  rate_hz int,
  has_gyro boolean,
  n int,
  payload jsonb          -- [[ax,ay,az,gx,gy,gz], ...] accel mG, gyro deg/s
);

alter table public.garmin_pilot enable row level security;

drop policy if exists garmin_pilot_insert on public.garmin_pilot;
create policy garmin_pilot_insert on public.garmin_pilot
  for insert to anon with check (true);
-- no select/update/delete policies: anon writes are one-way
