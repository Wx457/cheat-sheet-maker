import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from app.application.services.cheat_sheet_service import CheatSheetService
from app.schemas import GenerateSheetRequest


def run_stream(gemini_lines):
    """用给定的 Gemini 原始输出驱动流式解析，返回解析出的 SSE 事件（JSON 对象列表）。"""
    gemini = MagicMock()
    gemini.generate_text_stream = lambda prompt: iter(gemini_lines)
    rag = MagicMock()
    rag.search_context = AsyncMock(return_value=[])
    svc = CheatSheetService(gemini=gemini, rag_service=rag)

    async def collect():
        return [e async for e in svc.stream_cheat_sheet_sections(GenerateSheetRequest(), "u")]

    events = asyncio.run(collect())
    assert events[-1] == "data: [DONE]\n\n"
    return [json.loads(e[len("data: ") :]) for e in events[:-1]]


def test_parses_real_gemini_output_shapes():
    # 实际抓到的输出形态：开头 ```json 围栏、\( 单反斜杠、结尾 ``` 粘在最后一行
    events = run_stream(
        [
            "```json\n",
            '{"_type": "meta", "title": "Linear Algebra"}\n',
            r'{"title": "Eigen", "items": [{"type": "definition", "content": "an \(n \\times n\) matrix \(A\)"}]}'
            + "\n",
            r'{"title": "Diag", "items": [{"type": "equation", "content": "A = PDP^{-1}"}]}```',
        ]
    )

    assert events[0] == {"_type": "meta", "title": "Linear Algebra"}
    assert [e["title"] for e in events[1:]] == ["Eigen", "Diag"]
    assert events[1]["items"][0]["content"] == r"an \(n \times n\) matrix \(A\)"


def test_parses_concatenated_objects_and_preserves_latex_commands():
    events = run_stream(
        [
            '{"_type": "meta", "title": "T"}'
            + r'{"title": "S1", "items": [{"type": "text", "content": "\theta and \nabla f"}]}'
            + "\n",
        ]
    )

    assert [e.get("title") for e in events] == ["T", "S1"]
    assert events[1]["items"][0]["content"] == r"\theta and \nabla f"


def test_parses_pretty_printed_multiline_section():
    # 实际抓到的输出形态：一个 section 被缩进成多行，item 行末带逗号
    events = run_stream(
        [
            '{"_type": "meta", "title": "T"}\n',
            '{"title": "Eigen", "items": [\n',
            r'  {"type": "definition", "content": "\(Av = \lambda v\)"},' + "\n",
            '  {"type": "text", "content": "b"}\n',
            "]}\n",
        ]
    )

    assert events[1] == {
        "title": "Eigen",
        "items": [
            {"type": "definition", "content": r"\(Av = \lambda v\)"},
            {"type": "text", "content": "b"},
        ],
    }


def test_unwraps_sections_wrapper_object():
    events = run_stream(
        [
            '{"_type": "meta", "title": "T"}\n',
            '{"sections": [{"title": "S1", "items": []}, {"title": "S2", "items": []}]}\n',
        ]
    )

    assert [e.get("title") for e in events] == ["T", "S1", "S2"]


def test_truncated_trailing_object_is_dropped_but_stream_completes():
    events = run_stream(
        [
            '{"_type": "meta", "title": "T"}\n{"title": "S1", "items": []}\n{"title": "S2", "ite',
        ]
    )

    assert [e.get("title") for e in events] == ["T", "S1"]


def test_flat_format_items_are_grouped_under_section():
    # chunk 边界可以落在行中间
    events = run_stream(
        [
            '{"_type": "meta", "title": "T"}\n{"title": "S1"}\n{"type": "te',
            'xt", "content": "a"}\n{"type": "text", "content": "b"}\n{"title": "S2"}\n',
        ]
    )

    assert events[1] == {
        "title": "S1",
        "items": [{"type": "text", "content": "a"}, {"type": "text", "content": "b"}],
    }
    assert events[2] == {"title": "S2", "items": []}
