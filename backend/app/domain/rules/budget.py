from typing import Dict, List

from app.schemas import TopicInput


class BudgetRule:
    """根据页数限制与主题相关性分配条目预算的纯规则函数。"""

    @staticmethod
    def calculate(page_limit: str, topics: List[TopicInput]) -> Dict[str, int]:
        if page_limit == "1_side":
            total_items = 45
        elif page_limit == "1_page":
            total_items = 85
        elif page_limit == "2_pages":
            total_items = 120
        else:
            total_items = 200

        total_score = sum(t.relevance_score for t in topics) or 1

        budget_map: Dict[str, int] = {}
        current_allocated = 0
        sorted_topics = sorted(topics, key=lambda x: x.relevance_score, reverse=True)

        for topic in topics:
            raw_count = (topic.relevance_score / total_score) * total_items
            count = max(3, int(raw_count))
            budget_map[topic.title] = count
            current_allocated += count

        remainder = total_items - current_allocated
        if remainder > 0 and sorted_topics:
            for i in range(remainder):
                lucky_topic = sorted_topics[i % len(sorted_topics)]
                budget_map[lucky_topic.title] += 1

        return budget_map
