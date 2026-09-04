-- SwingCoach data platform — run this once in Supabase: SQL Editor → New query → paste → Run.
-- Postgres schema with row-level security: each golfer sees only their own rows.

-- ---------- profiles ----------
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  name text,
  org text,
  role text not null default 'golfer' check (role in ('golfer', 'coach')),
  created_at timestamptz not null default now()
);
alter table public.profiles enable row level security;
create policy "own profile" on public.profiles
  for all using (auth.uid() = id) with check (auth.uid() = id);

-- auto-create a profile row on signup
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id) values (new.id) on conflict do nothing;
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------- sessions (a range session or a round) ----------
create table if not exists public.sessions (
  id uuid primary key,                                  -- client-generated (offline-first)
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  type text not null check (type in ('range', 'round')),
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  notes text,
  course_id text,
  course_name text,
  course_lat double precision,
  course_lon double precision
);
alter table public.sessions enable row level security;
create policy "own sessions" on public.sessions
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create index if not exists sessions_user_started on public.sessions (user_id, started_at desc);

-- ---------- swings ----------
-- Hot trend metrics are real columns (fast time-series queries);
-- the complete metrics object rides along as JSONB so the schema
-- never blocks a new metric.
create table if not exists public.swings (
  id bigint generated always as identity primary key,
  session_id uuid not null references public.sessions (id) on delete cascade,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  seq int not null,
  ts timestamptz not null default now(),
  club_id text,
  club_inches numeric,
  tempo numeric,
  hand_mph numeric,
  club_mph numeric,
  plane_deg numeric,
  release_fraction numeric,
  clipped boolean not null default false,
  metrics jsonb,
  unique (session_id, seq)
);
alter table public.swings enable row level security;
create policy "own swings" on public.swings
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create index if not exists swings_user_ts on public.swings (user_id, ts);
create index if not exists swings_session on public.swings (session_id);

-- ---------- shots (round mode) ----------
create table if not exists public.shots (
  id bigint generated always as identity primary key,
  session_id uuid not null references public.sessions (id) on delete cascade,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  seq int not null,
  hole int not null,
  hit_at timestamptz not null default now(),
  club_id text,
  club_inches numeric,
  lat double precision,
  lon double precision,
  acc_m numeric,
  dist_m numeric,
  club_mph numeric,
  unique (session_id, seq)
);
alter table public.shots enable row level security;
create policy "own shots" on public.shots
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create index if not exists shots_session on public.shots (session_id);

-- ---------- holes (putts per hole, round mode) ----------
create table if not exists public.holes (
  session_id uuid not null references public.sessions (id) on delete cascade,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  hole int not null,
  putts int not null default 0,
  par int,
  primary key (session_id, hole)
);
alter table public.holes enable row level security;
create policy "own holes" on public.holes
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
