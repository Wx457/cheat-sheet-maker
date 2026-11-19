"""
课程 API（UPGRADE_PLAN 第 8 点 · 8-1）

- GET    /api/courses         当前用户的课程（按最近使用倒序；默认课程「Uncategorized」总是存在）
- POST   /api/courses         新建课程（同名 → 409，不区分大小写）
- GET    /api/courses/{id}    课程 + 该课程所有小抄版本（不含 sections）
- PATCH  /api/courses/{id}    改名 / 改默认参数（archetype / academic_level）
- DELETE /api/courses/{id}    删除课程：连同小抄、ingest 记录、Qdrant 中该课程的 chunk

不属于当前用户的课程一律 404。需要 Supabase；未配置时 503。
"""

import traceback
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException

from app.application.services.course_service import CourseNotFoundError, CourseService
from app.core.auth import CurrentUserId
from app.infrastructure.cache.redis_cache import get_cheat_sheet_cache
from app.infrastructure.db.supabase_store import DuplicateCourseNameError
from app.schemas import (
    CourseCreateRequest,
    CourseDeleteResponse,
    CourseDetail,
    CourseRecord,
    CourseUpdateRequest,
)

router = APIRouter()


def _require_service() -> CourseService:
    service = CourseService.default()
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="课程功能未配置（缺少 SUPABASE_URL / SUPABASE_SECRET_KEY）",
        )
    return service


def _not_found(course_id: UUID) -> HTTPException:
    return HTTPException(status_code=404, detail=f"课程不存在: {course_id}")


def _duplicate(name: str) -> HTTPException:
    return HTTPException(status_code=409, detail=f"A course named '{name}' already exists.")


@router.get("/api/courses", response_model=list[CourseRecord])
async def list_courses(user_id: CurrentUserId) -> list[CourseRecord]:
    service = _require_service()
    try:
        rows = await service.list_courses(user_id)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"读取课程时发生错误: {str(e)}")
    return [CourseRecord(**row) for row in rows]


@router.post("/api/courses", response_model=CourseRecord, status_code=201)
async def create_course(
    user_id: CurrentUserId,
    payload: CourseCreateRequest = Body(...),
) -> CourseRecord:
    service = _require_service()
    try:
        row = await service.create_course(
            user_id,
            payload.name,
            payload.archetype.value if payload.archetype else None,
            payload.academic_level.value if payload.academic_level else None,
        )
    except DuplicateCourseNameError:
        raise _duplicate(payload.name)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"创建课程时发生错误: {str(e)}")
    return CourseRecord(**row)


@router.get("/api/courses/{course_id}", response_model=CourseDetail)
async def get_course(user_id: CurrentUserId, course_id: UUID) -> CourseDetail:
    service = _require_service()
    try:
        detail = await service.get_course_detail(user_id, str(course_id))
    except CourseNotFoundError:
        raise _not_found(course_id)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"读取课程时发生错误: {str(e)}")
    return CourseDetail(**detail)


@router.patch("/api/courses/{course_id}", response_model=CourseRecord)
async def update_course(
    user_id: CurrentUserId,
    course_id: UUID,
    payload: CourseUpdateRequest = Body(...),
) -> CourseRecord:
    service = _require_service()
    fields = payload.model_dump(mode="json", exclude_unset=True)
    if "name" in fields and fields["name"] is None:
        raise HTTPException(status_code=422, detail="course name must not be null")
    try:
        row = await service.update_course(user_id, str(course_id), fields)
    except CourseNotFoundError:
        raise _not_found(course_id)
    except DuplicateCourseNameError:
        raise _duplicate(fields.get("name", ""))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"更新课程时发生错误: {str(e)}")
    return CourseRecord(**row)


@router.delete("/api/courses/{course_id}", response_model=CourseDeleteResponse)
async def delete_course(user_id: CurrentUserId, course_id: UUID) -> CourseDeleteResponse:
    service = _require_service()
    try:
        result = await service.delete_course(user_id, str(course_id))
    except CourseNotFoundError:
        raise _not_found(course_id)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"删除课程时发生错误: {str(e)}")
    finally:
        # 知识库可能已变化（含部分删除后失败）→ 该用户的生成结果缓存作废（Phase 5）
        await get_cheat_sheet_cache().invalidate_user(user_id)
    return CourseDeleteResponse(**result)
