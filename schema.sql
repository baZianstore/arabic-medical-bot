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
