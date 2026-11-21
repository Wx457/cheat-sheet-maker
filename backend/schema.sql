-- ═══════════════════════════════════════════════════════════════════════════
-- Supabase schema（当前完整结构）。新建项目时在 SQL Editor 中执行一次。
--
-- 访问模型：所有表开启 RLS 且不写 policy —— anon / authenticated 一律拒绝，
-- 只有后端用 SUPABASE_SECRET_KEY（绕过 RLS）读写，因此后端每个查询都必须按 user_id 过滤。
-- 知识库 chunk 本体在 Qdrant（metadata.user_id + course_id），不在这里。
-- ═══════════════════════════════════════════════════════════════════════════

create extension if not exists moddatetime schema extensions;

-- ── users ────────────────────────────────────────────────────────────────────
-- clerk_id：Clerk 用户；anon_id：Phase 2 之前插件生成的匿名 id（link-anon 后并入 Clerk 用户）
create table public.users (
  id          uuid primary key default gen_random_uuid(),
  anon_id     text unique,
  clerk_id    text unique,
  email       text unique,
  created_at  timestamptz not null default now(),
  constraint users_has_identity check (anon_id is not null or clerk_id is not null)
);

-- ── courses ──────────────────────────────────────────────────────────────────
-- 每个用户一门默认课程「Uncategorized」（is_default），未指定课程时兜底
create table public.courses (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.users(id) on delete cascade,
  name            text not null check (char_length(name) between 1 and 100),
  archetype       text,                       -- 与后端 CourseArchetype 枚举一致；插件表单默认值
  academic_level  text,                       -- 与后端 AcademicLevel 枚举一致；插件表单默认值
  is_default      boolean not null default false,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()   -- 改名 / 新增小抄 / ingest 时刷新，列表按它排序
);
create unique index courses_user_name_uq on public.courses (user_id, lower(name));
create unique index courses_user_default_uq on public.courses (user_id) where is_default;
create index courses_user_updated_idx on public.courses (user_id, updated_at desc);
create trigger courses_set_updated_at
  before update on public.courses
  for each row execute procedure extensions.moddatetime(updated_at);

-- ── cheat_sheets ─────────────────────────────────────────────────────────────
-- 一行 = 课程内的一个版本：生成 / 重新生成 = 新行（version 递增），编辑 = 改当前行
create table public.cheat_sheets (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references public.users(id) on delete cascade,
  course_id          uuid not null references public.courses(id) on delete cascade,
  parent_sheet_id    uuid references public.cheat_sheets(id) on delete set null,   -- 重新生成的父版本
  version            integer not null default 1,
  origin             text not null default 'generate',   -- generate | regenerate
  generation_params  jsonb,                              -- 生成参数（主题、page_limit、level……；重新生成时含 regeneration）
  title              text not null default '',
  sections           jsonb not null default '[]'::jsonb, -- 只存 [{title, items}]，不含前端 id / isStreaming
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
create index cheat_sheets_user_created_idx on public.cheat_sheets (user_id, created_at desc);
create index cheat_sheets_course_created_idx on public.cheat_sheets (course_id, created_at desc);
create trigger cheat_sheets_set_updated_at
  before update on public.cheat_sheets
  for each row execute procedure extensions.moddatetime(updated_at);

-- ── ingest_batches ───────────────────────────────────────────────────────────
-- 一行 = 一次 ingest；chunk 本体在 Qdrant，用 ingest_batch_id 对应 payload metadata.ingest_batch_id
create table public.ingest_batches (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references public.users(id) on delete cascade,
  course_id        uuid not null references public.courses(id) on delete cascade,
  ingest_batch_id  text not null unique,
  source           text,                   -- URL / 文件名 / 粘贴文本的来源名
  chunk_count      integer not null check (chunk_count >= 0),
  truncated        boolean not null default false,
  created_at       timestamptz not null default now()
);
create index ingest_batches_user_created_idx on public.ingest_batches (user_id, created_at desc);
create index ingest_batches_course_idx on public.ingest_batches (course_id);

-- ── RLS：开启且不加 policy ───────────────────────────────────────────────────
alter table public.users          enable row level security;
alter table public.courses        enable row level security;
alter table public.cheat_sheets   enable row level security;
alter table public.ingest_batches enable row level security;
