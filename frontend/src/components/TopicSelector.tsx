import { useState, useEffect } from 'react'
import type { TopicNode, TopicInput } from '../types'

interface TopicSelectorProps {
  topics: TopicNode[]
  onGenerate: (selectedTopics: TopicInput[]) => void
  loading?: boolean
}

interface ExtendedTopic extends TopicNode {
  isCustom?: boolean
}

const TopicSelector = ({ topics, onGenerate, loading = false }: TopicSelectorProps) => {
  const [selectedTopics, setSelectedTopics] = useState<Set<string>>(new Set())
  const [customTopicInput, setCustomTopicInput] = useState('')
  const [extendedTopics, setExtendedTopics] = useState<ExtendedTopic[]>([])

  // 初始化：默认选中所有 AI 检测到的主题
  useEffect(() => {
    const initial = new Set(topics.map((t) => t.title))
    setSelectedTopics(initial)
    setExtendedTopics(topics.map((t) => ({ ...t, isCustom: false })))
  }, [topics])

  const handleToggleTopic = (title: string) => {
    const newSelected = new Set(selectedTopics)
    if (newSelected.has(title)) {
      newSelected.delete(title)
    } else {
      newSelected.add(title)
    }
    setSelectedTopics(newSelected)
  }

  const handleAddCustomTopic = () => {
    const trimmed = customTopicInput.trim()
    if (!trimmed || extendedTopics.some((t) => t.title === trimmed)) {
      return
    }

    // 计算当前 AI 检测到的所有主题的 relevance_score 平均值
    const avgScore = topics.length > 0
      ? topics.reduce((sum, t) => sum + t.relevance_score, 0) / topics.length
      : 0.5  // 如果 topics 为空，默认使用 0.5

    const newTopic: ExtendedTopic = {
      title: trimmed,
      relevance_score: avgScore,  // 使用平均权重而不是 1.0
      isCustom: true,
    }

    setExtendedTopics([...extendedTopics, newTopic])
    setSelectedTopics(new Set([...selectedTopics, trimmed]))
    setCustomTopicInput('')
  }

  const handleGenerate = () => {
    if (selectedTopics.size === 0) {
      alert('请至少选择一个主题')
      return
    }
    
    // 遍历 extendedTopics，筛选出被选中的项，构建 TopicInput 数组
    const selectedTopicInputs: TopicInput[] = extendedTopics
      .filter((topic) => selectedTopics.has(topic.title))
      .map((topic) => ({
        title: topic.title,
        relevance_score: topic.relevance_score,
      }))
    
    onGenerate(selectedTopicInputs)
  }

  return (
    <div className="input-card no-print">
      <div className="input-header">
        <h2>步骤 2: 选择主题</h2>
      </div>

      <div className="topic-hint">
        AI 检测到 {topics.length} 个主题。请选择您需要包含在小抄中的主题。
      </div>

      <div className="topic-list">
        {extendedTopics.map((topic, idx) => (
          <label key={`${topic.title}-${idx}`} className="topic-item">
            <input
              type="checkbox"
              checked={selectedTopics.has(topic.title)}
              onChange={() => handleToggleTopic(topic.title)}
              className="topic-checkbox"
            />
            <span className="topic-title">{topic.title}</span>
            {!topic.isCustom && (
              <span className="topic-score">
                相关性: {(topic.relevance_score * 100).toFixed(0)}%
              </span>
            )}
            {topic.isCustom && <span className="topic-custom">自定义</span>}
          </label>
        ))}
      </div>

      <div className="custom-topic-input">
        <input
          type="text"
          className="form-input"
          placeholder="添加自定义主题..."
          value={customTopicInput}
          onChange={(e) => setCustomTopicInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              handleAddCustomTopic()
            }
          }}
        />
        <button
          className="add-topic-btn"
          onClick={handleAddCustomTopic}
          disabled={!customTopicInput.trim()}
        >
          +
        </button>
      </div>

      <button
        className="primary-btn"
        onClick={handleGenerate}
        disabled={loading || selectedTopics.size === 0}
      >
        {loading ? '生成中...' : `生成小抄 (${selectedTopics.size} 个主题)`}
      </button>
    </div>
  )
}

export default TopicSelector

