export type ContentType = 'text' | 'equation' | 'definition'

export type PageLimit = '1_side' | '1_page' | '2_pages' | 'unlimited'

export type AcademicLevel = 'high_school' | 'undergraduate' | 'graduate'

export type ExamType = 'quiz' | 'midterm' | 'final'

export interface ContentItem {
  type: ContentType
  content: string
}

export interface Section {
  title: string
  items: ContentItem[]
}

export interface CheatSheet {
  title: string
  sections: Section[]
}

export interface TopicNode {
  title: string
  relevance_score: number
}

export interface TopicInput {
  title: string
  relevance_score: number
}

export interface OutlineResponse {
  topics: TopicNode[]
}

