-- Round analytics migration — run once in Supabase: SQL Editor → New query → paste → Run.
-- Adds course identity to round sessions (so the analysis page can fetch
-- fairway/green geometry later) and par to the per-hole rows.

alter table public.sessions add column if not exists course_id text;
alter table public.sessions add column if not exists course_name text;
alter table public.sessions add column if not exists course_lat double precision;
alter table public.sessions add column if not exists course_lon double precision;

alter table public.holes add column if not exists par int;

-- 2026-09-05: mechanics × outcomes join + penalties
alter table public.shots add column if not exists swing_seq int;
alter table public.holes add column if not exists penalties int not null default 0;
