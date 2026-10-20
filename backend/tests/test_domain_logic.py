import json

from app.domain.rules.budget import BudgetRule
from app.domain.utils.cleaner import (
    clean_raw_text,
    densify_item_content,
    escape_latex_backslashes,
    extract_json_objects,
)
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


def test_escape_latex_backslashes_repairs_single_backslash_latex():
    # 复现 Gemini 实际输出：\( 单写（非法转义），\\times 已正确双写
    line = r'{"content": "an \(n \\times n\) matrix \(A\)"}'
    assert json.loads(escape_latex_backslashes(line))["content"] == r"an \(n \times n\) matrix \(A\)"


def test_escape_latex_backslashes_keeps_latex_that_looks_like_json_escapes():
    # \t \f \n \b \r 后接字母是 LaTeX 命令，不能被吞成制表符/换页/换行
    line = r'{"content": "\theta \frac{a}{b} \nabla f \beta \rho"}'
    assert json.loads(escape_latex_backslashes(line))["content"] == r"\theta \frac{a}{b} \nabla f \beta \rho"


def test_extract_json_objects_ignores_braces_and_quotes_inside_strings():
    buffer = r'```json' + "\n" + r'{"c": "\frac{a}{b} and \"}\""}, {"d": 1}' + "\n" + r'{"e": "unfin'
    objects, rest = extract_json_objects(buffer)

    assert objects == [r'{"c": "\frac{a}{b} and \"}\""}', '{"d": 1}']
    assert rest == r'{"e": "unfin'


def test_extract_json_objects_returns_empty_rest_when_nothing_pending():
    objects, rest = extract_json_objects('{"a": {"b": 1}}\n```')

    assert objects == ['{"a": {"b": 1}}']
    assert rest == ""


def test_escape_latex_backslashes_preserves_valid_json_escapes():
    line = r'{"content": "say \"hi\"\n next \\alpha é a/b"}'
    assert escape_latex_backslashes(line) == line
    assert json.loads(line)["content"] == 'say "hi"\n next \\alpha é a/b'
