#!/usr/bin/env python3
"""LLM-as-a-Judge evaluation for RAG retrieval groundedness.

This script runs against the **live** MongoDB Atlas vector store and uses
Gemini 2.5 Flash as an impartial judge to score how well retrieved chunks
cover the expected knowledge anchors for each synthetic query.

Usage (from backend/):
    python -m scripts.eval_retrieval_groundedness                  # all queries
    python -m scripts.eval_retrieval_groundedness --user-id <uid>  # specific user

Requires: MONGODB_URI, GOOGLE_API_KEY, OPENAI_API_KEY in .env
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.rag.vector_store import VectorStore  # noqa: E402
from app.infrastructure.llm.gemini_client import GeminiClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Golden dataset — synthetic queries with expected anchor knowledge
# ---------------------------------------------------------------------------

@dataclass
class GoldenQuery:
    query: str
    anchor_knowledge: str
    topic: str


GOLDEN_DATASET: list[GoldenQuery] = [
    GoldenQuery(
        query="What are the key concepts of eigenvalue decomposition?",
        anchor_knowledge=(
            "Eigenvalue decomposition factors a square matrix into eigenvalues "
            "and eigenvectors. The matrix A can be expressed as PDP^{-1} where "
            "D is a diagonal matrix of eigenvalues and P contains eigenvectors."
        ),
        topic="Linear Algebra",
    ),
    GoldenQuery(
        query="Explain the fundamental theorem of calculus and its significance",
        anchor_knowledge=(
            "The fundamental theorem of calculus connects differentiation and "
            "integration, stating that the integral of a derivative recovers "
            "the original function (up to a constant)."
        ),
        topic="Calculus",
    ),
    GoldenQuery(
        query="How does Bayes' theorem work in probability?",
        anchor_knowledge=(
            "Bayes' theorem computes the posterior probability of a hypothesis "
            "given observed evidence, using the prior probability and the "
            "likelihood function: P(H|E) = P(E|H)P(H) / P(E)."
        ),
        topic="Statistics / Probability",
    ),
    GoldenQuery(
        query="What is gradient descent and how is it used in machine learning?",
        anchor_knowledge=(
            "Gradient descent is an iterative optimisation algorithm that "
            "minimises a loss function by computing gradients and updating "
            "model parameters in the direction of steepest descent."
        ),
        topic="Machine Learning",
    ),
    GoldenQuery(
        query="Describe common sorting algorithms and their time complexity",
        anchor_knowledge=(
            "Common sorting algorithms include merge sort (O(n log n)), "
            "quicksort (average O(n log n)), and insertion sort (O(n^2)). "
            "Merge sort is stable and uses divide-and-conquer."
        ),
        topic="Algorithms",
    ),
]

# ---------------------------------------------------------------------------
# LLM-as-a-Judge prompt
# ---------------------------------------------------------------------------

JUDGE_PROMPT_TEMPLATE = textwrap.dedent("""\
    You are an impartial evaluation judge.  Your task is to assess how well
    the RETRIEVED CHUNKS cover the EXPECTED ANCHOR KNOWLEDGE for a given
    USER QUERY.

    Scoring rubric (output a single float between 0.0 and 1.0):
      1.0 — Retrieved chunks fully cover the anchor knowledge with accurate,
             relevant detail.  No important information is missing.
      0.7 — Most of the anchor knowledge is covered; minor gaps or tangential
             content present.
      0.4 — Partial coverage; significant portions of the anchor knowledge
             are missing or only loosely related content was retrieved.
      0.1 — Very little relevant content; mostly irrelevant or off-topic.
      0.0 — No relevant content at all; complete miss.

    USER QUERY:
    {query}

    EXPECTED ANCHOR KNOWLEDGE:
    {anchor}

    RETRIEVED CHUNKS:
    {chunks}

    Respond with ONLY a JSON object in this exact format:
    {{"score": <float>, "reasoning": "<one-sentence explanation>"}}
""")


# ---------------------------------------------------------------------------
# Core evaluation logic
# ---------------------------------------------------------------------------

async def retrieve_chunks(
    vs: VectorStore, query: str, user_id: str, k: int = 5,
) -> list[dict]:
    return await vs.search_context(query, user_id=user_id, k=k)


def judge_groundedness(
    gemini: GeminiClient, query: str, anchor: str, chunks: list[dict],
) -> tuple[float, str]:
    """Ask Gemini to score how well chunks cover the anchor knowledge."""
    chunks_text = "\n---\n".join(
        f"[Source: {c.get('source', '?')}]  {c.get('content', '')}" for c in chunks
    ) or "(no chunks retrieved)"

    prompt = JUDGE_PROMPT_TEMPLATE.format(
        query=query, anchor=anchor, chunks=chunks_text,
    )
    result = gemini.generate_json(prompt)
    score = float(result.get("score", 0.0))
    reasoning = result.get("reasoning", "")
    return score, reasoning


@dataclass
class EvalRow:
    topic: str
    query: str
    chunks_retrieved: int
    score: float
    reasoning: str
    latency_ms: float


async def run_evaluation(
    user_id: str,
    k: int = 5,
    dataset: list[GoldenQuery] | None = None,
) -> list[EvalRow]:
    dataset = dataset or GOLDEN_DATASET
    vs = VectorStore()
    gemini = GeminiClient()
    rows: list[EvalRow] = []

    for gq in dataset:
        t0 = time.perf_counter()
        chunks = await retrieve_chunks(vs, gq.query, user_id, k=k)
        retrieval_ms = (time.perf_counter() - t0) * 1000

        score, reasoning = judge_groundedness(gemini, gq.query, gq.anchor_knowledge, chunks)

        rows.append(EvalRow(
            topic=gq.topic,
            query=gq.query,
            chunks_retrieved=len(chunks),
            score=score,
            reasoning=reasoning,
            latency_ms=round(retrieval_ms, 1),
        ))
        logger.info(
            "  [%s]  score=%.2f  chunks=%d  latency=%.0fms",
            gq.topic, score, len(chunks), retrieval_ms,
        )

    vs.close()
    return rows


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(rows: list[EvalRow]) -> None:
    scores = np.array([r.score for r in rows])
    latencies = np.array([r.latency_ms for r in rows])

    print("\n" + "=" * 72)
    print("  RAG Retrieval Groundedness — Evaluation Report")
    print("=" * 72)

    print(f"\n{'Topic':<25} {'Score':>6} {'Chunks':>7} {'Latency':>10}  Reasoning")
    print("-" * 72)
    for r in rows:
        print(
            f"{r.topic:<25} {r.score:>6.2f} {r.chunks_retrieved:>7} "
            f"{r.latency_ms:>8.0f}ms  {r.reasoning[:50]}"
        )

    print("-" * 72)
    print(f"{'MEAN':<25} {scores.mean():>6.2f} "
          f"{np.mean([r.chunks_retrieved for r in rows]):>7.1f} "
          f"{latencies.mean():>8.0f}ms")
    print(f"{'STD':<25} {scores.std():>6.2f} "
          f"{'':>7} "
          f"{latencies.std():>8.0f}ms")
    print(f"{'MIN':<25} {scores.min():>6.2f}")
    print(f"{'MAX':<25} {scores.max():>6.2f}")
    print("=" * 72)

    if scores.mean() >= 0.7:
        print("\n✅ PASS — Average groundedness ≥ 0.70")
    elif scores.mean() >= 0.4:
        print("\n⚠️  MARGINAL — Average groundedness between 0.40 and 0.70")
    else:
        print("\n❌ FAIL — Average groundedness < 0.40")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate RAG retrieval groundedness using LLM-as-a-Judge",
    )
    parser.add_argument(
        "--user-id", required=True,
        help="user_id whose knowledge base to query against",
    )
    parser.add_argument(
        "--k", type=int, default=5,
        help="number of chunks to retrieve per query (default: 5)",
    )
    args = parser.parse_args()

    logger.info("Starting evaluation for user_id=%s, k=%d", args.user_id, args.k)
    rows = asyncio.run(run_evaluation(user_id=args.user_id, k=args.k))
    print_report(rows)


if __name__ == "__main__":
    main()
