-- ═══════════════════════════════════════════════════════════════════════════
-- UPGRADE_PLAN 第 8 点 · 8-1：课程与版本
-- 在 Supabase SQL Editor 中分两步执行：
--   第 1 步（本节）→ 部署新后端 → 运行 `python scripts/migrate_courses.py`
--   → 第 2 步（文件末尾，确认迁移脚本报告 0 条遗留后再执行）
-- 全部语句可重复执行。
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 第 1 步：建表 / 加列 ─────────────────────────────────────────────────────

create table if not exists public.courses (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.users(id) on delete cascade,
  name            text not null check (char_length(name) between 1 and 100),
  archetype       text,                       -- 与后端 CourseArchetype 枚举一致；插件表单默认值
  academic_level  text,                       -- 与后端 AcademicLevel 枚举一致；插件表单默认值
  is_default      boolean not null default false,   -- 每个用户一门「Uncategorized」：兜底课程 + 旧数据归属
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()  -- 改名 / 新增小抄 / ingest 时刷新，列表按它排序
);
create unique index if not exists courses_user_name_uq on public.courses (user_id, lower(name));
create unique index if not exists courses_user_default_uq on public.courses (user_id) where is_default;
create index if not exists courses_user_updated_idx on public.courses (user_id, updated_at desc);
drop trigger if exists courses_set_updated_at on public.courses;
create trigger courses_set_updated_at
  before update on public.courses
  for each row execute procedure extensions.moddatetime(updated_at);
alter table public.courses enable row level security;   -- 同其他表：不写 policy，仅后端 secret key 访问

alter table public.cheat_sheets
  add column if not exists course_id         uuid references public.courses(id) on delete cascade,
  add column if not exists parent_sheet_id   uuid references public.cheat_sheets(id) on delete set null,
  add column if not exists version           integer not null default 1,
  add column if not exists generation_params jsonb,           -- 生成参数（主题、page_limit、level……），8-2 重新生成复用
  add column if not exists origin            text not null default 'generate';   -- generate | regenerate
create index if not exists cheat_sheets_course_created_idx on public.cheat_sheets (course_id, created_at desc);

alter table public.ingest_batches
  add column if not exists course_id uuid references public.courses(id) on delete cascade;
create index if not exists ingest_batches_course_idx on public.ingest_batches (course_id);


-- ── 第 2 步：迁移脚本跑完后再执行 ────────────────────────────────────────────
-- 先确认没有遗留（两条都应返回 0）：
--   select count(*) from public.cheat_sheets   where course_id is null;
--   select count(*) from public.ingest_batches where course_id is null;
--
-- alter table public.cheat_sheets   alter column course_id set not null;
-- alter table public.ingest_batches alter column course_id set not null;
