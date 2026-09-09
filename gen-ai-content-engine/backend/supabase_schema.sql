-- OmniFormat AI Engine — Supabase schema
-- Run once in the Supabase project's SQL editor.

create table if not exists public.transformations (
  run_id      text primary key,
  user_id     text not null default 'anonymous',
  created_at  timestamptz not null default now(),
  payload     jsonb not null
);

create index if not exists transformations_user_created_idx
  on public.transformations (user_id, created_at desc);

-- The backend connects with the service-role key and bypasses RLS.
-- RLS is still enabled so the anon/public key cannot read rows directly.
alter table public.transformations enable row level security;
