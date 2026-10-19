'use client'

/**
 * CardList — 可拖拽 section 卡片列表
 *
 * DnD Kit 三层结构：
 *   DndContext            → 拖拽事件的全局容器
 *     SortableContext     → 管理 items 顺序，提供排序算法
 *       useSortable()     → 每张卡片的 hook，注入 ref / attrs / listeners / style
 *     DragOverlay         → 拖拽时跟随光标的「幽灵」预览
 *
 * 流程：
 *   用户按住手柄 → onDragStart 记录 activeId
 *   拖动过程中  → (SortableContext 内部计算虚拟顺序)
 *   松开        → onDragEnd → arrayMove → store.reorderSections
 */

import { useState } from 'react'
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  DragOverlay,
  closestCenter,
  type DragStartEvent,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  arrayMove,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

import { useCheatSheetStore } from '@/stores/cheatSheetStore'
import CheatSheetCard from '@/components/CheatSheetCard'
import type { UISection } from '@/types'

// ─────────────────────────────────────────────────────────────────────────────
// SortableCard — wraps CheatSheetCard with useSortable()
// ─────────────────────────────────────────────────────────────────────────────

function SortableCard({ section }: { section: UISection }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: section.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <CheatSheetCard
      section={section}
      setNodeRef={setNodeRef}
      attributes={attributes}
      listeners={listeners}
      style={style}
      isDragging={isDragging}
    />
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CardList — public component
// ─────────────────────────────────────────────────────────────────────────────

export default function CardList() {
  const sections = useCheatSheetStore((s) => s.sections)
  const reorderSections = useCheatSheetStore((s) => s.reorderSections)

  // ID of the section currently being dragged (for DragOverlay)
  const [activeId, setActiveId] = useState<string | null>(null)
  const activeSection = sections.find((s) => s.id === activeId) ?? null

  // ── Sensors ─────────────────────────────────────────────────────────────
  // PointerSensor:  handles mouse and touch
  // KeyboardSensor: handles keyboard-based drag (a11y)
  const sensors = useSensors(
    useSensor(PointerSensor, {
      // Require 8px of movement before activating drag
      // (prevents accidental drags when clicking buttons inside the card)
      activationConstraint: { distance: 8 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  )

  // ── Handlers ─────────────────────────────────────────────────────────────
  function handleDragStart(event: DragStartEvent) {
    setActiveId(event.active.id as string)
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    setActiveId(null)

    if (!over || active.id === over.id) return

    const oldIndex = sections.findIndex((s) => s.id === active.id)
    const newIndex = sections.findIndex((s) => s.id === over.id)

    if (oldIndex !== -1 && newIndex !== -1) {
      // arrayMove is used to validate the new order, then we sync to Zustand
      // (arrayMove itself doesn't mutate state — reorderSections does)
      reorderSections(oldIndex, newIndex)
    }
  }

  // ── Empty state ──────────────────────────────────────────────────────────
  if (sections.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-24 text-zinc-400 dark:text-zinc-600 select-none">
        <svg
          width="40"
          height="40"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="opacity-40"
        >
          <path d="M9 12h6M9 16h6M4 6h16M4 10h16M4 14h2M4 18h2" />
        </svg>
        <p className="text-sm">No sections yet. Generate a cheat sheet to get started.</p>
      </div>
    )
  }

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <SortableContext
        items={sections.map((s) => s.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="flex flex-col gap-4">
          {sections.map((section) => (
            <SortableCard key={section.id} section={section} />
          ))}
        </div>
      </SortableContext>

      {/*
        DragOverlay renders a floating clone of the dragged card.
        It lives outside the SortableContext so it doesn't affect layout.
        pointerEvents="none" prevents it from capturing hover/click events.
      */}
      <DragOverlay>
        {activeSection && (
          <div className="pointer-events-none rotate-1 scale-[1.02] opacity-90">
            <CheatSheetCard section={activeSection} isDragging />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  )
}
