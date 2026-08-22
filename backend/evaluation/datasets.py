"""The evaluation dataset: scripted cases across the categories from
docs/ROADMAP.md § 8. Each `Case` fully specifies what every fake LLM role says and
what every fake tool returns, so a run is 100% reproducible — same case in, same
trace out, every time.

This is deliberately Python data, not JSON: several cases need to express "this tool
call raises an exception" or "this item was never returned by any tool" (on purpose,
to test the verifier), which a plain JSON fixture can't express without inventing its
own mini-DSL. Grow this list to widen the benchmark — the harness does not care how
many cases exist per category.
"""

from dataclasses import dataclass, field

ALL_TOOL_NAMES = [
    "search_papers",
    "search_patents",
    "search_news",
    "search_social",
    "search_reddit",
    "search_github",
    "search_google",
]


@dataclass
class ResearchLane:
    """One researcher's script: the sub-question it answers, what it calls, what
    each tool call returns (a raw payload, or an `Exception` instance to simulate a
    failure), the items it claims to have found, and any coverage gap it reports."""

    question: str
    tool_calls: list[dict] = field(default_factory=list)  # [{"name": ..., "args": {"query": ...}}]
    tool_results: dict = field(default_factory=dict)  # tool name -> raw payload | Exception
    items: list[dict] = field(default_factory=list)
    coverage_gaps: list[str] = field(default_factory=list)
    thought: str = "Researching."


@dataclass
class Case:
    id: str
    category: str  # normal | ambiguous | incomplete | contradictory | adversarial | tool_failure | replanning
    goal: str
    context: str
    planner: dict  # {"sub_questions": [...], "rationale": "..."}
    lanes: list[ResearchLane]
    analyst: dict  # {"items": [...], "coverage_ok": bool, "coverage_gaps": [...], "executive_summary": "..."}
    strategist: dict = field(default_factory=lambda: {"competitors": [], "opportunities": [], "risks": [], "recommended_actions": []})
    replan: dict | None = None
    conflict: dict | None = None
    single: dict | None = None  # optional pipeline=single script, for baseline comparison cases
    expect: dict = field(default_factory=dict)  # assertions consumed by evaluators.py

    @property
    def lanes_by_question(self) -> dict:
        return {lane.question: lane for lane in self.lanes}


# ---------------------------------------------------------------------------
# normal — everything works, nothing adversarial
# ---------------------------------------------------------------------------

_normal_q1 = "What recent research exists on on-device speech recognition models?"
_normal_q2 = "What competitor products or news exist for offline voice assistants?"

NORMAL_001 = Case(
    id="normal-001",
    category="normal",
    goal="find developments in on-device speech recognition",
    context="Building an offline voice-assistant SDK for Android; care about model size, latency, and competing SDKs.",
    planner={
        "sub_questions": [
            {"question": _normal_q1, "sources": ["papers"], "why": "Grounds the technical state of the art."},
            {"question": _normal_q2, "sources": ["news"], "why": "Grounds competitive product activity."},
        ],
        "rationale": "Split into research literature and market/news coverage.",
    },
    lanes=[
        ResearchLane(
            question=_normal_q1,
            tool_calls=[{"name": "search_papers", "args": {"query": "on-device speech recognition"}}],
            tool_results={
                "search_papers": [
                    {
                        "title": "Efficient On-Device ASR via Quantized Transformers",
                        "abstract": "A quantized transformer ASR model running under 50MB on-device.",
                        "url": "https://arxiv.org/abs/9999.0001",
                        "year": 2026,
                        "citationCount": 12,
                        "externalIds": {"DOI": "10.1234/asr1"},
                    }
                ]
            },
            items=[
                {
                    "source": "research",
                    "external_id": "10.1234/asr1",
                    "title": "Efficient On-Device ASR via Quantized Transformers",
                    "url": "https://arxiv.org/abs/9999.0001",
                    "summary": "Quantized transformer ASR model running under 50MB on-device, low latency.",
                    "date": "2026-01-15",
                    "engagement": 12,
                    "organization": "",
                }
            ],
        ),
        ResearchLane(
            question=_normal_q2,
            tool_calls=[{"name": "search_news", "args": {"query": "offline voice assistant SDK Android"}}],
            tool_results={
                "search_news": [
                    {
                        "title": "Acme Launches Offline Voice SDK for Android",
                        "url": "https://news.example.com/acme-offline-voice",
                        "publishedAt": "2026-02-01",
                    }
                ]
            },
            items=[
                {
                    "source": "news",
                    "external_id": "https://news.example.com/acme-offline-voice",
                    "title": "Acme Launches Offline Voice SDK for Android",
                    "url": "https://news.example.com/acme-offline-voice",
                    "summary": "Acme released an offline voice SDK targeting Android developers.",
                    "date": "2026-02-01",
                    "engagement": None,
                    "organization": "Acme",
                }
            ],
        ),
    ],
    analyst={
        "items": [
            {"external_id": "10.1234/asr1", "relevance_reason": "Directly relevant model architecture for the SDK.", "organization": "", "keep": True},
            {"external_id": "https://news.example.com/acme-offline-voice", "relevance_reason": "Direct competitor shipping the same product category.", "organization": "Acme", "keep": True},
        ],
        "coverage_ok": True,
        "coverage_gaps": [],
        "executive_summary": "Found one relevant ASR research paper and one direct competitor SDK launch; no coverage gaps.",
    },
    single={
        "tool_calls": [
            {"name": "search_papers", "args": {"query": "on-device speech recognition"}},
            {"name": "search_news", "args": {"query": "offline voice assistant SDK Android"}},
        ],
        "tool_results": {
            "search_papers": [
                {
                    "title": "Efficient On-Device ASR via Quantized Transformers",
                    "abstract": "A quantized transformer ASR model running under 50MB on-device.",
                    "url": "https://arxiv.org/abs/9999.0001",
                    "year": 2026,
                    "citationCount": 12,
                    "externalIds": {"DOI": "10.1234/asr1"},
                }
            ],
            "search_news": [
                {
                    "title": "Acme Launches Offline Voice SDK for Android",
                    "url": "https://news.example.com/acme-offline-voice",
                    "publishedAt": "2026-02-01",
                }
            ],
        },
        "items": [
            {
                "source": "research", "external_id": "10.1234/asr1",
                "title": "Efficient On-Device ASR via Quantized Transformers",
                "url": "https://arxiv.org/abs/9999.0001",
                "summary": "Quantized transformer ASR model running under 50MB on-device.",
                "relevance_reason": "Directly relevant model architecture for the SDK.",
                "date": "2026-01-15", "engagement": 12, "organization": "",
            },
            {
                "source": "news", "external_id": "https://news.example.com/acme-offline-voice",
                "title": "Acme Launches Offline Voice SDK for Android",
                "url": "https://news.example.com/acme-offline-voice",
                "summary": "Acme released an offline voice SDK targeting Android developers.",
                "relevance_reason": "Direct competitor shipping the same product category.",
                "date": "2026-02-01", "engagement": None, "organization": "Acme",
            },
        ],
        "coverage_ok": True,
        "coverage_gaps": [],
        "executive_summary": "Found one relevant ASR research paper and one direct competitor SDK launch.",
    },
    expect={
        "expected_kept_ids": {"10.1234/asr1", "https://news.example.com/acme-offline-voice"},
        "expected_rejected_ids": set(),
        "coverage_ok": True,
    },
)


# ---------------------------------------------------------------------------
# tool_failure — a source errors; run must recover and say so, not crash or hide it
# ---------------------------------------------------------------------------

_tf_q1 = "What recent research exists on solid-state EV battery chemistry?"
_tf_q2 = "What recent news exists on solid-state EV battery announcements?"

TOOL_FAILURE_001 = Case(
    id="tool_failure-001",
    category="tool_failure",
    goal="find developments in solid-state battery chemistry for EVs",
    context="EV battery startup evaluating competitive and research activity in solid-state chemistry.",
    planner={
        "sub_questions": [
            {"question": _tf_q1, "sources": ["papers"], "why": "Research-side technical activity."},
            {"question": _tf_q2, "sources": ["news"], "why": "Market/announcement activity."},
        ],
        "rationale": "Split into research literature and news.",
    },
    lanes=[
        ResearchLane(
            question=_tf_q1,
            tool_calls=[{"name": "search_papers", "args": {"query": "solid-state EV battery chemistry"}}],
            tool_results={"search_papers": RuntimeError("HTTPStatusError: 429 Too Many Requests")},
            items=[],
            coverage_gaps=["papers: rate-limited after retry"],
        ),
        ResearchLane(
            question=_tf_q2,
            tool_calls=[{"name": "search_news", "args": {"query": "solid-state EV battery announcement"}}],
            tool_results={
                "search_news": [
                    {
                        "title": "Voltaic Motors Announces Solid-State Pack for 2027 Models",
                        "url": "https://news.example.com/voltaic-solid-state",
                        "publishedAt": "2026-03-01",
                    }
                ]
            },
            items=[
                {
                    "source": "news",
                    "external_id": "https://news.example.com/voltaic-solid-state",
                    "title": "Voltaic Motors Announces Solid-State Pack for 2027 Models",
                    "url": "https://news.example.com/voltaic-solid-state",
                    "summary": "Voltaic Motors announced a solid-state battery pack targeting 2027 model-year vehicles.",
                    "date": "2026-03-01",
                    "engagement": None,
                    "organization": "Voltaic Motors",
                }
            ],
        ),
    ],
    analyst={
        "items": [
            {"external_id": "https://news.example.com/voltaic-solid-state", "relevance_reason": "Direct competitor solid-state pack announcement.", "organization": "Voltaic Motors", "keep": True},
        ],
        "coverage_ok": True,
        "coverage_gaps": ["papers: rate-limited after retry"],
        "executive_summary": "Research literature source was unavailable after retry; news coverage surfaced one competitor announcement.",
    },
    expect={
        "expected_kept_ids": {"https://news.example.com/voltaic-solid-state"},
        "expected_rejected_ids": set(),
        "expect_gap_containing": "papers",
        "coverage_ok": True,
    },
)


# ---------------------------------------------------------------------------
# contradictory — same org, sources disagree on impact -> must be flagged
# ---------------------------------------------------------------------------

_contra_q1 = "What patent activity exists for Globex in edge AI camera inference?"
_contra_q2 = "What public news or social sentiment exists about Globex and edge AI cameras?"

CONTRADICTORY_001 = Case(
    id="contradictory-001",
    category="contradictory",
    goal="assess whether Globex is entering the edge AI camera market",
    context="Public-safety edge AI camera company evaluating whether Globex is a competitive threat in real-time on-device inference for cameras.",
    planner={
        "sub_questions": [
            {"question": _contra_q1, "sources": ["patents"], "why": "Patent activity is a leading technical signal."},
            {"question": _contra_q2, "sources": ["news", "social"], "why": "Public-facing signal of market entry."},
        ],
        "rationale": "Compare technical/patent signal against public news/social signal for the same organization.",
    },
    lanes=[
        ResearchLane(
            question=_contra_q1,
            tool_calls=[{"name": "search_patents", "args": {"query": "Globex edge AI camera inference"}}],
            tool_results={
                "search_patents": [
                    {
                        "title": "Globex Real-Time Edge AI Camera Inference Chip and Method",
                        "url": "https://patents.example.com/globex-edge-ai-001",
                        "publication_number": "US11999999B2",
                        "assignee": "Globex",
                    }
                ]
            },
            items=[
                {
                    "source": "patent",
                    "external_id": "US11999999B2",
                    "title": "Globex Real-Time Edge AI Camera Inference Chip and Method",
                    "url": "https://patents.example.com/globex-edge-ai-001",
                    "summary": "Globex filed a patent for a real-time edge AI inference chip for camera applications, public-safety use cases named explicitly.",
                    "date": None,
                    "engagement": None,
                    "organization": "Globex",
                }
            ],
        ),
        ResearchLane(
            question=_contra_q2,
            tool_calls=[{"name": "search_social", "args": {"query": "Globex edge AI camera"}}],
            tool_results={
                "search_social": [
                    {
                        "objectID": "hn-globex-1",
                        "title": "Globex is hiring more backend engineers",
                        "url": "https://news.ycombinator.com/item?id=1000001",
                        "points": 3,
                    }
                ]
            },
            items=[
                {
                    "source": "social",
                    "external_id": "hn-globex-1",
                    "title": "Globex is hiring more backend engineers",
                    "url": "https://news.ycombinator.com/item?id=1000001",
                    "summary": "An old, low-engagement discussion thread about Globex hiring for its finance and payroll systems team.",
                    "date": "2019-06-01",
                    "engagement": 3,
                    "organization": "Globex",
                }
            ],
        ),
    ],
    analyst={
        "items": [
            {"external_id": "US11999999B2", "relevance_reason": "Direct patent evidence of edge AI camera inference work.", "organization": "Globex", "keep": True},
            {"external_id": "hn-globex-1", "relevance_reason": "Weak, tangential public signal about Globex.", "organization": "Globex", "keep": True},
        ],
        "coverage_ok": True,
        "coverage_gaps": [],
        "executive_summary": "Globex shows strong patent activity in edge AI camera inference but almost no matching public/social visibility.",
    },
    conflict={
        "resolutions": [
            {
                "organization": "Globex",
                "note": "Strong patent activity not yet reflected in public news or social coverage — likely early-stage, undisclosed work.",
                "confidence": 0.65,
            }
        ]
    },
    expect={
        "expected_kept_ids": {"US11999999B2", "hn-globex-1"},
        "expect_conflict_org": "Globex",
    },
)


# ---------------------------------------------------------------------------
# incomplete — genuinely no evidence -> must refuse, not fabricate a conclusion
# ---------------------------------------------------------------------------

_inc_q1 = "What research exists on Quantum Dynamics's activity in this space?"
_inc_q2 = "What news exists on Quantum Dynamics's activity in this space?"

INCOMPLETE_001 = Case(
    id="incomplete-001",
    category="incomplete",
    goal="find evidence of Quantum Dynamics entering the market",
    context="Evaluating a rumored but unconfirmed competitor, 'Quantum Dynamics', in the neuromorphic edge-compute space.",
    planner={
        "sub_questions": [
            {"question": _inc_q1, "sources": ["papers"], "why": "Research-side signal, if any."},
            {"question": _inc_q2, "sources": ["news"], "why": "Public announcement signal, if any."},
        ],
        "rationale": "Check both research and news for any trace of this rumored competitor.",
    },
    lanes=[
        ResearchLane(
            question=_inc_q1,
            tool_calls=[{"name": "search_papers", "args": {"query": "Quantum Dynamics neuromorphic edge compute"}}],
            tool_results={"search_papers": []},
            items=[],
            coverage_gaps=["papers: no results for Quantum Dynamics"],
        ),
        ResearchLane(
            question=_inc_q2,
            tool_calls=[{"name": "search_news", "args": {"query": "Quantum Dynamics neuromorphic edge compute"}}],
            tool_results={"search_news": []},
            items=[],
            coverage_gaps=["news: no results for Quantum Dynamics"],
        ),
    ],
    analyst={
        "items": [],
        "coverage_ok": False,
        "coverage_gaps": ["papers: no results for Quantum Dynamics", "news: no results for Quantum Dynamics"],
        "executive_summary": "No verifiable evidence of Quantum Dynamics activity was found in research or news sources; nothing to report.",
    },
    expect={
        "expected_kept_ids": set(),
        "coverage_ok": False,
        "expect_no_fabricated_conclusion": True,
    },
)


# ---------------------------------------------------------------------------
# adversarial — a researcher claims an item that never appeared in any tool result
# ---------------------------------------------------------------------------

_adv_q1 = "What open-source GitHub projects compete with our vector database?"

ADVERSARIAL_001 = Case(
    id="adversarial-001",
    category="adversarial",
    goal="find recent GitHub projects competing with our open-source vector database",
    context="We maintain an open-source embedded vector database; tracking competing open-source projects.",
    planner={
        "sub_questions": [
            {"question": _adv_q1, "sources": ["github"], "why": "Direct open-source competitor signal."},
        ],
        "rationale": "Single-lane search for competing GitHub projects.",
    },
    lanes=[
        ResearchLane(
            question=_adv_q1,
            tool_calls=[{"name": "search_github", "args": {"query": "open-source vector database"}}],
            tool_results={
                "search_github": [
                    {
                        "full_name": "acme/vectordb-lite",
                        "html_url": "https://github.com/acme/vectordb-lite",
                        "description": "Lightweight embedded vector database.",
                        "stargazers_count": 420,
                    }
                ]
            },
            items=[
                {
                    "source": "github",
                    "external_id": "https://github.com/acme/vectordb-lite",
                    "title": "acme/vectordb-lite",
                    "url": "https://github.com/acme/vectordb-lite",
                    "summary": "Lightweight embedded vector database, direct competitor.",
                    "date": None,
                    "engagement": 420,
                    "organization": "Acme",
                },
                {
                    # Never appeared in any tool result — the verifier must reject this.
                    "source": "github",
                    "external_id": "fabricated/repo",
                    "title": "FastVector: Blazing Fast Vector DB",
                    "url": "https://github.com/fabricated/repo",
                    "summary": "A vector database the model invented rather than saw in a tool result.",
                    "date": None,
                    "engagement": 9999,
                    "organization": "",
                },
            ],
        ),
    ],
    analyst={
        "items": [
            {"external_id": "https://github.com/acme/vectordb-lite", "relevance_reason": "Directly competing embedded vector database.", "organization": "Acme", "keep": True},
        ],
        "coverage_ok": True,
        "coverage_gaps": [],
        "executive_summary": "Found one direct open-source competitor.",
    },
    expect={
        "expected_kept_ids": {"https://github.com/acme/vectordb-lite"},
        "expected_rejected_titles": {"FastVector: Blazing Fast Vector DB"},
    },
)


# ---------------------------------------------------------------------------
# replanning — thin initial coverage must trigger a bounded follow-up round
# ---------------------------------------------------------------------------

_rp_q1 = "What research exists on federated learning for mobile keyboards?"
_rp_q2 = "What patent activity exists for federated learning on mobile keyboards?"
_rp_new_q = "What competitor products use federated learning for mobile keyboard prediction?"

REPLANNING_001 = Case(
    id="replanning-001",
    category="replanning",
    goal="find developments in federated learning for mobile keyboard prediction",
    context="Building a privacy-preserving mobile keyboard; tracking federated learning research and competitor adoption.",
    planner={
        "sub_questions": [
            {"question": _rp_q1, "sources": ["papers"], "why": "Technical state of the art."},
            {"question": _rp_q2, "sources": ["patents"], "why": "Technical/IP activity."},
        ],
        "rationale": "Split into research and patent literature.",
    },
    lanes=[
        ResearchLane(
            question=_rp_q1,
            tool_calls=[{"name": "search_papers", "args": {"query": "federated learning mobile keyboard"}}],
            tool_results={
                "search_papers": [
                    {
                        "title": "Federated Learning for Next-Word Prediction on Mobile Keyboards",
                        "url": "https://arxiv.org/abs/9999.0002",
                        "year": 2026,
                        "citationCount": 40,
                        "externalIds": {"DOI": "10.1234/fl-keyboard"},
                    }
                ]
            },
            items=[
                {
                    "source": "research",
                    "external_id": "10.1234/fl-keyboard",
                    "title": "Federated Learning for Next-Word Prediction on Mobile Keyboards",
                    "url": "https://arxiv.org/abs/9999.0002",
                    "summary": "Federated learning approach to on-device next-word prediction for mobile keyboards.",
                    "date": "2026-01-20",
                    "engagement": 40,
                    "organization": "",
                }
            ],
        ),
        ResearchLane(
            # Thin lane on purpose: no results -> coverage below threshold -> replan.
            question=_rp_q2,
            tool_calls=[{"name": "search_patents", "args": {"query": "federated learning mobile keyboard"}}],
            tool_results={"search_patents": []},
            items=[],
            coverage_gaps=["patents: no results for federated learning mobile keyboard"],
        ),
        # The replanned lane — same shape, registered up front so the fake researcher
        # conversation can answer it when the graph fans out to it after replan_check.
        ResearchLane(
            question=_rp_new_q,
            tool_calls=[{"name": "search_news", "args": {"query": "competitor federated learning mobile keyboard"}}],
            tool_results={
                "search_news": [
                    {
                        "title": "Keybird Ships Federated Learning Keyboard Prediction",
                        "url": "https://news.example.com/keybird-federated",
                        "publishedAt": "2026-02-15",
                    }
                ]
            },
            items=[
                {
                    "source": "news",
                    "external_id": "https://news.example.com/keybird-federated",
                    "title": "Keybird Ships Federated Learning Keyboard Prediction",
                    "url": "https://news.example.com/keybird-federated",
                    "summary": "Competitor Keybird shipped federated learning-based keyboard prediction.",
                    "date": "2026-02-15",
                    "engagement": None,
                    "organization": "Keybird",
                }
            ],
        ),
    ],
    analyst={
        "items": [
            {"external_id": "10.1234/fl-keyboard", "relevance_reason": "Directly relevant research.", "organization": "", "keep": True},
        ],
        "coverage_ok": False,
        "coverage_gaps": ["patents: no results for federated learning mobile keyboard"],
        "executive_summary": "Found relevant research but no patent activity; coverage is thin.",
    },
    replan={
        "new_sub_questions": [
            {"question": _rp_new_q, "sources": ["news"], "why": "Patent lane was empty — check for competitor product signal instead."},
        ],
        "rationale": "Patent coverage came back empty; opening a market/news lane to recover coverage.",
    },
    expect={
        "expect_replanned": True,
        "expected_kept_ids": {"10.1234/fl-keyboard", "https://news.example.com/keybird-federated"},
    },
)


DATASET: list[Case] = [
    NORMAL_001,
    TOOL_FAILURE_001,
    CONTRADICTORY_001,
    INCOMPLETE_001,
    ADVERSARIAL_001,
    REPLANNING_001,
]

BY_ID = {c.id: c for c in DATASET}
BY_CATEGORY: dict[str, list[Case]] = {}
for _c in DATASET:
    BY_CATEGORY.setdefault(_c.category, []).append(_c)
