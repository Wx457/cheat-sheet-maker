from app.domain.rules.budget import BudgetRule
from app.domain.utils.cleaner import clean_raw_text, densify_item_content
from app.domain.utils.math_formatter import normalize_equation
from app.schemas import TopicInput


def test_clean_raw_text_removes_html_and_normalizes_whitespace():
    raw = "  <div>Hello</div>\n\n\nWorld\t\t  "

    cleaned = clean_raw_text(raw)

    assert cleaned == "Hello\n\nWorld"


def test_densify_item_content_merges_markdown_bullets():
    text = "Line one\n- item A\n- item B"

    densified = densify_item_content(text)

    assert densified == "Line one  • item A  • item B"


def test_densify_item_content_preserves_code_blocks():
    text = "Intro\n```python\nprint('hi')\n```"

    densified = densify_item_content(text)

    assert densified == text


def test_normalize_equation_strips_wrappers_and_newlines():
    content = "\\[\na = b + c\n\\]"

    normalized = normalize_equation(content)

    assert normalized == "$$a = b + c$$"


def test_budget_rule_allocates_expected_total_and_prioritizes_high_score_topic():
    topics = [
        TopicInput(title="Topic A", relevance_score=0.9),
        TopicInput(title="Topic B", relevance_score=0.1),
    ]

    budget = BudgetRule.calculate("1_side", topics)

    assert sum(budget.values()) == 45
    assert budget["Topic A"] > budget["Topic B"]
    assert budget["Topic B"] >= 3
