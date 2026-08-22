"""Interactive strategy Q&A over everything the agent has stored.

Retrieval is hybrid: Postgres full-text ranking (which is good at exact names,
model numbers and acronyms) fused with pgvector cosine similarity (which is good
at paraphrase), combined by reciprocal rank fusion. The answering model is told to
cite or refuse — an assertion with no [n] behind it is a bug, not a style choice.
"""

import json
import re

from .memory import get_pool
from .providers import LLMProvider, get_provider
from .scoring import EMBED_DIM

RRF_K = 60  # standard reciprocal-rank-fusion damping constant

SYSTEM = """You answer questions about a competitive-intelligence corpus.

You are given numbered findings. Every factual claim in your answer must cite the
findings it came from, as [1] or [2][5], placed at the end of the sentence it
supports.

Rules that matter more than being helpful:
- If the findings do not contain the answer, say so plainly and name what is
  missing. Do not fall back on general knowledge — the user is asking what THIS
  corpus knows, and an unsourced answer is worse than no answer.
- Never cite a number that is not in the list you were given.
- Do not describe the corpus or the retrieval; answer the question.
- Be concrete: names, dates, numbers from the findings. 2-6 sentences unless the
  question genuinely needs a list.
"""


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in values) + "]"


async def retrieve(
    question: str,
    limit: int = 8,
    run_id: str | None = None,
    provider: LLMProvider | None = None,
) -> list[dict]:
    """Hybrid retrieval. Returns items in fused-rank order, each carrying the ranks
    it earned from each retriever so the UI can show why something surfaced."""
    provider = provider or get_provider()
    pool = await get_pool()

    embedding = (await provider.embed([question], EMBED_DIM))[0]
    candidate_pool = max(limit * 5, 40)

    rows = await pool.fetch(
        """
        WITH scope AS (
            SELECT id, source, external_id, title, url, summary, relevance_reason,
                   organization, impact_score, published_at, first_seen_at, embedding
            FROM seen_items
            WHERE ($3::uuid IS NULL OR run_id = $3::uuid)
        ),
        semantic AS (
            SELECT id, row_number() OVER (ORDER BY embedding <=> $1::vector) AS rank
            FROM scope
            WHERE embedding IS NOT NULL
            LIMIT $4
        ),
        lexical AS (
            SELECT id,
                   row_number() OVER (
                       ORDER BY ts_rank(
                           to_tsvector('english',
                               coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' ||
                               coalesce(relevance_reason,'') || ' ' || coalesce(organization,'')),
                           plainto_tsquery('english', $2)
                       ) DESC
                   ) AS rank
            FROM scope
            WHERE plainto_tsquery('english', $2) @@ to_tsvector('english',
                      coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' ||
                      coalesce(relevance_reason,'') || ' ' || coalesce(organization,''))
            LIMIT $4
        )
        SELECT s.id, s.source, s.external_id, s.title, s.url, s.summary,
               s.relevance_reason, s.organization, s.impact_score,
               s.published_at, s.first_seen_at,
               sem.rank AS semantic_rank,
               lex.rank AS lexical_rank,
               (1.0 / ($5 + coalesce(sem.rank, 1000000))) +
               (1.0 / ($5 + coalesce(lex.rank, 1000000))) AS fused
        FROM scope s
        LEFT JOIN semantic sem ON sem.id = s.id
        LEFT JOIN lexical  lex ON lex.id = s.id
        WHERE sem.id IS NOT NULL OR lex.id IS NOT NULL
        ORDER BY fused DESC
        LIMIT $6
        """,
        _vector_literal(embedding),
        question,
        run_id,
        candidate_pool,
        RRF_K,
        limit,
    )

    return [
        {
            "id": str(r["id"]),
            "source": r["source"],
            "external_id": r["external_id"],
            "title": r["title"],
            "url": r["url"],
            "summary": r["summary"],
            "relevance_reason": r["relevance_reason"],
            "organization": r["organization"],
            "impact_1_10": r["impact_score"],
            "date": r["published_at"].isoformat() if r["published_at"] else None,
            "first_seen_at": r["first_seen_at"].isoformat() if r["first_seen_at"] else None,
            "semantic_rank": r["semantic_rank"],
            "lexical_rank": r["lexical_rank"],
            "matched_by": (
                "both"
                if r["semantic_rank"] and r["lexical_rank"]
                else "semantic"
                if r["semantic_rank"]
                else "keyword"
            ),
        }
        for r in rows
    ]


def _context_block(citations: list[dict]) -> str:
    return "\n\n".join(
        json.dumps(
            {
                "n": i + 1,
                "source": c["source"],
                "title": c["title"],
                "organization": c["organization"],
                "date": c["date"],
                "impact_1_10": c["impact_1_10"],
                "summary": c["summary"],
                "why_it_mattered": c["relevance_reason"],
                "url": c["url"],
            },
            default=str,
        )
        for i, c in enumerate(citations)
    )


def cited_indexes(answer: str, count: int) -> list[int]:
    """Which [n] markers the answer actually used, ignoring out-of-range ones."""
    used = {int(m) for m in re.findall(r"\[(\d{1,2})\]", answer)}
    return sorted(n for n in used if 1 <= n <= count)


async def ask(
    question: str,
    limit: int = 8,
    run_id: str | None = None,
    provider: LLMProvider | None = None,
) -> dict:
    provider = provider or get_provider()
    citations = await retrieve(question, limit, run_id, provider)

    if not citations:
        return {
            "question": question,
            "answer": (
                "Nothing in the corpus matches that question yet. Run the agent on a "
                "goal that covers it, then ask again."
            ),
            "citations": [],
            "cited": [],
            "provider": provider.name,
            "model": provider.model,
        }

    turn = await provider.complete(
        SYSTEM,
        f"Question: {question}\n\nFindings:\n{_context_block(citations)}",
    )
    answer = turn.text.strip()
    used = cited_indexes(answer, len(citations))

    return {
        "question": question,
        "answer": answer,
        # Everything retrieved is returned so the UI can show what was considered,
        # with `cited` marking which ones the answer actually leaned on.
        "citations": citations,
        "cited": used,
        "provider": provider.name,
        "model": provider.model,
        "input_tokens": turn.input_tokens,
        "output_tokens": turn.output_tokens,
    }


async def suggested_questions(limit: int = 5) -> list[str]:
    """Question starters grounded in what the corpus actually holds — the most
    frequent organizations and sources — so the first click is never a dead end."""
    pool = await get_pool()
    orgs = await pool.fetch(
        """SELECT organization, count(*) AS n
           FROM seen_items
           WHERE organization IS NOT NULL AND organization <> ''
           GROUP BY organization ORDER BY n DESC LIMIT 3"""
    )
    sources = await pool.fetch(
        "SELECT source, count(*) AS n FROM seen_items GROUP BY source ORDER BY n DESC LIMIT 2"
    )

    questions = [
        "What are the highest-impact findings so far, and why do they matter?",
        "Which competitors show up most often, and in what kind of source?",
    ]
    for row in orgs:
        questions.append(f"What has {row['organization']} been doing in this space?")
    for row in sources:
        questions.append(f"What do the {row['source']} findings say about where this is heading?")
    return questions[:limit]
