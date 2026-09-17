-- مخطط قاعدة بيانات بوت التعليم الطبي
-- المحتوى تعليمي عام فقط؛ لا تُخزَّن بيانات مرضى أو PHI.

create extension if not exists pgcrypto;

-- أي كائن جديد يبقى مغلقًا حتى منحه صراحة لدور خادمي محدد.
alter default privileges for role postgres in schema public
    revoke select, insert, update, delete on tables from anon, authenticated, service_role;
alter default privileges for role postgres in schema public
    revoke usage, select on sequences from anon, authenticated, service_role;
alter default privileges for role postgres in schema public
    revoke execute on functions from public;

create table if not exists public.diseases (
    id uuid primary key default gen_random_uuid(),
    name_ar text not null check (char_length(name_ar) between 2 and 200),
    name_en text not null check (char_length(name_en) between 2 and 200),
    system text not null check (char_length(system) between 2 and 120),
    definition text not null check (char_length(definition) between 10 and 5000),
    etiology text not null check (char_length(etiology) between 10 and 5000),
    symptoms text not null check (char_length(symptoms) between 10 and 5000),
    diagnosis text not null check (char_length(diagnosis) between 10 and 5000),
    treatment text not null check (char_length(treatment) between 10 and 7000),
    importance smallint not null default 1 check (importance between 1 and 3),
    week_number smallint not null default 1 check (week_number between 1 and 53),
    image_url text check (image_url is null or char_length(image_url) <= 1000),
    created_at timestamptz not null default now(),
    unique (name_ar),
    unique (name_en)
);

create table if not exists public.questions (
    id uuid primary key default gen_random_uuid(),
    disease_id uuid not null references public.diseases(id) on delete cascade,
    question text not null check (char_length(question) between 5 and 2000),
    option_a text not null check (char_length(option_a) between 1 and 1000),
    option_b text not null check (char_length(option_b) between 1 and 1000),
    option_c text not null check (char_length(option_c) between 1 and 1000),
    option_d text not null check (char_length(option_d) between 1 and 1000),
    correct_answer text not null check (correct_answer in ('A', 'B', 'C', 'D')),
    explanation text not null check (char_length(explanation) between 5 and 3000),
    difficulty smallint not null default 1 check (difficulty between 1 and 5),
    created_at timestamptz not null default now()
);

create table if not exists public.subscribers (
    id uuid primary key default gen_random_uuid(),
    user_id bigint not null unique,
    username text check (username is null or char_length(username) <= 64),
    subscribed_at timestamptz not null default now(),
    is_active boolean not null default true
);

-- هذا الجدول الصغير يجعل النشر اليومي idempotent حتى عند وجود أكثر من مجدول.
create table if not exists public.daily_publications (
    publication_date date primary key,
    disease_id uuid references public.diseases(id) on delete set null,
    created_at timestamptz not null default now()
);

create index if not exists diseases_week_number_idx on public.diseases(week_number);
create index if not exists diseases_system_idx on public.diseases(system);
create index if not exists questions_disease_id_idx on public.questions(disease_id);
create index if not exists subscribers_active_idx on public.subscribers(is_active) where is_active = true;

-- منع الوصول الافتراضي من المفاتيح العامة والمستخدمين النهائيين.
alter table public.diseases enable row level security;
alter table public.questions enable row level security;
alter table public.subscribers enable row level security;
alter table public.daily_publications enable row level security;

revoke all on table public.diseases from anon, authenticated;
revoke all on table public.questions from anon, authenticated;
revoke all on table public.subscribers from anon, authenticated;
revoke all on table public.daily_publications from anon, authenticated;

grant select, insert, update, delete on table public.diseases to service_role;
grant select, insert, update, delete on table public.questions to service_role;
grant select, insert, update, delete on table public.subscribers to service_role;
grant select, insert, update, delete on table public.daily_publications to service_role;

-- لا تُنشأ سياسات لـ anon أو authenticated؛ عدم وجود سياسة يعني DENY.
comment on table public.diseases is 'محتوى طبي تعليمي عام فقط، بلا بيانات مرضى.';
comment on table public.questions is 'أسئلة تعليمية عامة مرتبطة بالأمراض.';
comment on table public.subscribers is 'الحد الأدنى من بيانات توصيل Telegram؛ لا بيانات سريرية.';

-- عدادات يومية مجمعة؛ لا معرفات مستخدمين ولا نصوص رسائل أو كلمات بحث.
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

-- صف واحد فقط لإعداد مستلم التقرير؛ منفصل بالكامل عن عدادات الاستخدام.
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
