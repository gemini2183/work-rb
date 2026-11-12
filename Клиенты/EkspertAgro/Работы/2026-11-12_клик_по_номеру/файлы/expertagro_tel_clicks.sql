create table public.expertagro_tel_clicks (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  ts_ms bigint not null,
  rngst_client_id text not null default '',
  click_key text not null default '', gclid text not null default '', gbraid text not null default '', wbraid text not null default '',
  utm_source text not null default '', utm_medium text not null default '', utm_campaign text not null default '', utm_content text not null default '',
  page_url text not null default '', phone_href text not null default '', consent text not null default '', mark_source text not null default ''
);
create unique index expertagro_tel_clicks_uq on public.expertagro_tel_clicks (rngst_client_id, ts_ms);
alter table public.expertagro_tel_clicks enable row level security;
create policy "anon insert" on public.expertagro_tel_clicks for insert to anon with check (true);
-- чтение для anon НЕ открываем; читает скрипт с секретным ключом
