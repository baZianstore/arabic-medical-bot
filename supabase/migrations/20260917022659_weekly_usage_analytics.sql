-- عدادات استخدام يومية مجمعة فقط؛ لا معرفات مستخدمين أو نصوص رسائل.

create table if not exists public.usage_daily_metrics (
    metric_date date not null,
    event_type text not null check (
        event_type in (
            'start', 'menu_open', 'help_view', 'today_view', 'topic_view',
            'topic_detail_view', 'sources_view', 'quiz_en_started',
            'quiz_en_answered', 'quiz_en_correct', 'quiz_ar_started',
            'quiz_ar_answered', 'quiz_ar_correct', 'search_success',
            'search_empty', 'systems_view', 'stats_view'
        )
    ),
    topic_id text not null default '' check (
        topic_id in ('', 'diabetes', 'asthma', 'hypertension', 'gastritis', 'hypothyroidism')
    ),
    event_count bigint not null default 0 check (event_count >= 0),
    updated_at timestamptz not null default now(),
    primary key (metric_date, event_type, topic_id)
);

create table if not exists public.report_delivery_config (
    id smallint primary key default 1 check (id = 1),
    telegram_chat_id bigint,
    linked_at timestamptz,
    link_token_hash text check (link_token_hash is null or link_token_hash ~ '^[0-9a-f]{64}$'),
    link_token_expires_at timestamptz,
    updated_at timestamptz not null default now(),
    check (
        (link_token_hash is null and link_token_expires_at is null)
        or (link_token_hash is not null and link_token_expires_at is not null)
    )
);

create table if not exists public.weekly_report_deliveries (
    week_start date primary key,
    status text not null check (status in ('pending', 'sent')),
    claimed_at timestamptz not null default now(),
    sent_at timestamptz,
    total_interactions bigint check (total_interactions is null or total_interactions >= 0)
);

create index if not exists usage_daily_metrics_date_idx
    on public.usage_daily_metrics(metric_date desc);
create index if not exists usage_daily_metrics_event_idx
    on public.usage_daily_metrics(event_type, metric_date desc);

alter table public.usage_daily_metrics enable row level security;
alter table public.report_delivery_config enable row level security;
alter table public.weekly_report_deliveries enable row level security;

revoke all on table public.usage_daily_metrics from public, anon, authenticated;
revoke all on table public.report_delivery_config from public, anon, authenticated;
revoke all on table public.weekly_report_deliveries from public, anon, authenticated;

grant select, insert, update, delete on table public.usage_daily_metrics to service_role;
grant select, insert, update, delete on table public.report_delivery_config to service_role;
grant select, insert, update, delete on table public.weekly_report_deliveries to service_role;

create or replace function public.increment_usage_metric(
    p_metric_date date,
    p_event_type text,
    p_topic_id text default ''
)
returns void
language sql
security invoker
set search_path = ''
as $$
    insert into public.usage_daily_metrics (
        metric_date,
        event_type,
        topic_id,
        event_count,
        updated_at
    )
    values (
        p_metric_date,
        p_event_type,
        coalesce(p_topic_id, ''),
        1,
        now()
    )
    on conflict (metric_date, event_type, topic_id)
    do update set
        event_count = public.usage_daily_metrics.event_count + 1,
        updated_at = now();
$$;

revoke all on function public.increment_usage_metric(date, text, text) from public, anon, authenticated;
grant execute on function public.increment_usage_metric(date, text, text) to service_role;

create or replace function public.consume_report_link_token(
    p_token_hash text,
    p_chat_id bigint
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
    updated_rows integer;
begin
    update public.report_delivery_config
    set telegram_chat_id = p_chat_id,
        linked_at = now(),
        link_token_hash = null,
        link_token_expires_at = null,
        updated_at = now()
    where id = 1
      and link_token_hash = p_token_hash
      and link_token_expires_at > now();
    get diagnostics updated_rows = row_count;
    return updated_rows = 1;
end;
$$;

revoke all on function public.consume_report_link_token(text, bigint) from public, anon, authenticated;
grant execute on function public.consume_report_link_token(text, bigint) to service_role;

comment on table public.usage_daily_metrics is
    'عدادات يومية مجمعة لتفاعل البوت، بلا معرفات مستخدمين أو نصوص رسائل.';
comment on table public.report_delivery_config is
    'إعداد توصيل إداري منفصل؛ لا يرتبط بأحداث التعلم.';
comment on table public.weekly_report_deliveries is
    'سجل تشغيلي لمنع إرسال التقرير الأسبوعي أكثر من مرة.';
