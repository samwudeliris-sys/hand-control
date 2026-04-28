create extension if not exists pgcrypto;

create table if not exists public.devices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  role text not null check (role in ('mac', 'phone')),
  public_device_id text not null unique,
  last_seen_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.pairings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  mac_device_id uuid references public.devices(id) on delete cascade,
  phone_device_id uuid references public.devices(id) on delete cascade,
  status text not null default 'active' check (status in ('active', 'revoked')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.relay_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  pairing_id uuid references public.pairings(id) on delete cascade,
  device_id uuid references public.devices(id) on delete cascade,
  role text not null check (role in ('mac', 'phone')),
  token_hash text not null,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

alter table public.devices enable row level security;
alter table public.pairings enable row level security;
alter table public.relay_sessions enable row level security;

drop policy if exists devices_select_own on public.devices;
create policy devices_select_own
  on public.devices for select
  using (auth.uid() = user_id);

drop policy if exists devices_insert_own on public.devices;
create policy devices_insert_own
  on public.devices for insert
  with check (auth.uid() = user_id);

drop policy if exists devices_update_own on public.devices;
create policy devices_update_own
  on public.devices for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists pairings_select_own on public.pairings;
create policy pairings_select_own
  on public.pairings for select
  using (auth.uid() = user_id);

drop policy if exists pairings_insert_own on public.pairings;
create policy pairings_insert_own
  on public.pairings for insert
  with check (auth.uid() = user_id);

drop policy if exists pairings_update_own on public.pairings;
create policy pairings_update_own
  on public.pairings for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists relay_sessions_select_own on public.relay_sessions;
create policy relay_sessions_select_own
  on public.relay_sessions for select
  using (auth.uid() = user_id);

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists devices_touch_updated_at on public.devices;
create trigger devices_touch_updated_at
  before update on public.devices
  for each row execute function public.touch_updated_at();

drop trigger if exists pairings_touch_updated_at on public.pairings;
create trigger pairings_touch_updated_at
  before update on public.pairings
  for each row execute function public.touch_updated_at();
