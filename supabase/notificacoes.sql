-- Radar do Café: inscrições das notificações no celular.
-- Rodar uma vez no SQL Editor do Supabase.

create table if not exists public.radar_inscricoes (
  id uuid primary key default gen_random_uuid(),
  endpoint text not null unique,
  p256dh text not null,
  auth text not null,
  prefs jsonb not null default '{}'::jsonb,
  falhas int not null default 0,
  criado timestamptz not null default now(),
  atualizado timestamptz not null default now()
);

-- O app (chave pública) não lê nem altera a tabela diretamente: só pelas duas funções abaixo,
-- que mexem apenas na inscrição do próprio celular. O robô usa a chave service_role.
alter table public.radar_inscricoes enable row level security;
revoke all on public.radar_inscricoes from anon, authenticated;

create or replace function public.radar_salvar_inscricao(p_endpoint text, p_p256dh text, p_auth text, p_prefs jsonb)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_endpoint is null or p_endpoint !~ '^https://' or length(p_endpoint) > 1000 then
    raise exception 'endereço de inscrição inválido';
  end if;
  if length(coalesce(p_p256dh, '')) > 200 or length(coalesce(p_auth, '')) > 100 or pg_column_size(p_prefs) > 4000 then
    raise exception 'dados grandes demais';
  end if;
  insert into public.radar_inscricoes (endpoint, p256dh, auth, prefs)
  values (p_endpoint, p_p256dh, p_auth, coalesce(p_prefs, '{}'::jsonb))
  on conflict (endpoint) do update
    set p256dh = excluded.p256dh, auth = excluded.auth, prefs = excluded.prefs, atualizado = now(), falhas = 0;
end;
$$;

create or replace function public.radar_remover_inscricao(p_endpoint text)
returns void
language sql
security definer
set search_path = public
as $$
  delete from public.radar_inscricoes where endpoint = p_endpoint;
$$;

revoke all on function public.radar_salvar_inscricao(text, text, text, jsonb) from public;
revoke all on function public.radar_remover_inscricao(text) from public;
grant execute on function public.radar_salvar_inscricao(text, text, text, jsonb) to anon;
grant execute on function public.radar_remover_inscricao(text) to anon;
