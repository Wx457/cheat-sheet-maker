"""测试用内存版 SupabaseStore（只实现 API / 服务层用到的方法，语义与真实实现一致）。"""

from datetime import datetime, timedelta, timezone
from itertools import count

from app.infrastructure.db.supabase_store import DEFAULT_COURSE_NAME, DuplicateCourseNameError

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


class FakeSupabase:
    def __init__(self):
        self._ids = count(1)
        self._clock = count(1)
        self.users = {}  # clerk_id -> db user id
        self.courses = {}  # id -> row（含 user_id）
        self.sheets = {}  # id -> row（含 user_id）

    def _now(self):
        return (_BASE + timedelta(seconds=next(self._clock))).isoformat()

    # ── users ────────────────────────────────────────────────────────────────

    def get_or_create_user_id(self, clerk_id):
        return self.users.setdefault(clerk_id, f"db-{clerk_id}")

    # ── courses ──────────────────────────────────────────────────────────────

    def _public_course(self, row):
        return {k: v for k, v in row.items() if k != "user_id"}

    def _insert_course(self, user_id, name, archetype=None, academic_level=None, is_default=False):
        if any(
            c["user_id"] == user_id and c["name"].lower() == name.lower()
            for c in self.courses.values()
        ):
            raise DuplicateCourseNameError(name)
        now = self._now()
        row = {
            "id": _uuid(next(self._ids)),
            "user_id": user_id,
            "name": name,
            "archetype": archetype,
            "academic_level": academic_level,
            "is_default": is_default,
            "created_at": now,
            "updated_at": now,
        }
        self.courses[row["id"]] = row
        return self._public_course(row)

    def get_or_create_default_course(self, user_id):
        for c in self.courses.values():
            if c["user_id"] == user_id and c["is_default"]:
                return self._public_course(c)
        return self._insert_course(user_id, DEFAULT_COURSE_NAME, is_default=True)

    def list_courses(self, user_id):
        rows = [
            {**self._public_course(c), "sheet_count": self._sheet_count(c["id"])}
            for c in self.courses.values()
            if c["user_id"] == user_id
        ]
        return sorted(rows, key=lambda r: r["updated_at"], reverse=True)

    def _sheet_count(self, course_id):
        return sum(1 for s in self.sheets.values() if s["course_id"] == course_id)

    def get_course(self, user_id, course_id):
        c = self.courses.get(course_id)
        return self._public_course(c) if c and c["user_id"] == user_id else None

    def create_course(self, user_id, name, archetype=None, academic_level=None):
        return self._insert_course(user_id, name, archetype, academic_level)

    def update_course(self, user_id, course_id, fields):
        c = self.courses.get(course_id)
        if not c or c["user_id"] != user_id:
            return None
        name = fields.get("name")
        if name and any(
            o["id"] != course_id and o["user_id"] == user_id and o["name"].lower() == name.lower()
            for o in self.courses.values()
        ):
            raise DuplicateCourseNameError(name)
        c.update(fields, updated_at=self._now())
        return self._public_course(c)

    def touch_course(self, user_id, course_id):
        c = self.courses.get(course_id)
        if c and c["user_id"] == user_id:
            c["updated_at"] = self._now()

    def delete_course(self, user_id, course_id):
        c = self.courses.get(course_id)
        if not c or c["user_id"] != user_id:
            return False
        del self.courses[course_id]
        for sid in [s for s, row in self.sheets.items() if row["course_id"] == course_id]:
            del self.sheets[sid]
        return True

    def list_course_sheets(self, user_id, course_id):
        rows = [
            {
                k: s[k]
                for k in (
                    "id",
                    "title",
                    "version",
                    "origin",
                    "parent_sheet_id",
                    "created_at",
                    "updated_at",
                )
            }
            for s in self.sheets.values()
            if s["user_id"] == user_id and s["course_id"] == course_id
        ]
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)

    # ── cheat_sheets ─────────────────────────────────────────────────────────

    def create_cheat_sheet(
        self,
        user_id,
        course_id,
        title,
        sections,
        generation_params=None,
        origin="generate",
        parent_sheet_id=None,
    ):
        in_course = [
            s
            for s in self.sheets.values()
            if s["user_id"] == user_id and s["course_id"] == course_id
        ]
        latest = max(in_course, key=lambda s: s["version"], default=None)
        if (
            latest
            and generation_params is not None
            and latest["generation_params"] == generation_params
            and latest["sections"] == sections
            and latest["title"] == title
        ):
            return latest
        now = self._now()
        row = {
            "id": _uuid(next(self._ids)),
            "user_id": user_id,
            "course_id": course_id,
            "title": title,
            "sections": sections,
            "version": (latest["version"] + 1) if latest else 1,
            "origin": origin,
            "parent_sheet_id": parent_sheet_id,
            "generation_params": generation_params,
            "created_at": now,
            "updated_at": now,
        }
        self.sheets[row["id"]] = row
        self.touch_course(user_id, course_id)
        return row

    def update_cheat_sheet(self, user_id, sheet_id, title, sections):
        row = self.sheets.get(sheet_id)
        if row is None or row["user_id"] != user_id:
            return None
        row.update(title=title, sections=sections, updated_at=self._now())
        return row

    def get_cheat_sheet(self, user_id, sheet_id):
        row = self.sheets.get(sheet_id)
        if row is None or row["user_id"] != user_id:
            return None
        return row
