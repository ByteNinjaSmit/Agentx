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
    single={
        "tool_calls": [
            {"name": "search_papers", "args": {"query": "solid-state EV battery chemistry"}},
            {"name": "search_news", "args": {"query": "solid-state EV battery announcement"}},
        ],
        "tool_results": {
            "search_papers": RuntimeError("HTTPStatusError: 429 Too Many Requests"),
            "search_news": [
                {
                    "title": "Voltaic Motors Announces Solid-State Pack for 2027 Models",
                    "url": "https://news.example.com/voltaic-solid-state",
                    "publishedAt": "2026-03-01",
                }
            ],
        },
        "items": [
            {
                "source": "news",
                "external_id": "https://news.example.com/voltaic-solid-state",
                "title": "Voltaic Motors Announces Solid-State Pack for 2027 Models",
                "url": "https://news.example.com/voltaic-solid-state",
                "summary": "Voltaic Motors announced a solid-state battery pack targeting 2027 model-year vehicles.",
                "relevance_reason": "Direct competitor solid-state pack announcement.",
                "date": "2026-03-01",
                "engagement": None,
                "organization": "Voltaic Motors",
            }
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
    single={
        "tool_calls": [
            {"name": "search_patents", "args": {"query": "Globex edge AI camera inference"}},
            {"name": "search_social", "args": {"query": "Globex edge AI camera"}},
        ],
        "tool_results": {
            "search_patents": [
                {
                    "title": "Globex Real-Time Edge AI Camera Inference Chip and Method",
                    "url": "https://patents.example.com/globex-edge-ai-001",
                    "publication_number": "US11999999B2",
                    "assignee": "Globex",
                }
            ],
            "search_social": [
                {
                    "objectID": "hn-globex-1",
                    "title": "Globex is hiring more backend engineers",
                    "url": "https://news.ycombinator.com/item?id=1000001",
                    "points": 3,
                }
            ],
        },
        "items": [
            {
                "source": "patent",
                "external_id": "US11999999B2",
                "title": "Globex Real-Time Edge AI Camera Inference Chip and Method",
                "url": "https://patents.example.com/globex-edge-ai-001",
                "summary": "Globex filed a patent for a real-time edge AI inference chip for camera applications.",
                "relevance_reason": "Direct patent evidence of edge AI camera inference work.",
                "date": None, "engagement": None, "organization": "Globex",
            },
            {
                "source": "social",
                "external_id": "hn-globex-1",
                "title": "Globex is hiring more backend engineers",
                "url": "https://news.ycombinator.com/item?id=1000001",
                "summary": "An old, low-engagement discussion thread about Globex hiring.",
                "relevance_reason": "Weak, tangential public signal about Globex.",
                "date": "2019-06-01", "engagement": 3, "organization": "Globex",
            },
        ],
        "coverage_ok": True,
        "coverage_gaps": [],
        # single-loop has no conflict-resolution step, so its summary can't flag the disagreement.
        "executive_summary": "Found signals for Globex across patent and social sources.",
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
    single={
        "tool_calls": [
            {"name": "search_papers", "args": {"query": "Quantum Dynamics neuromorphic edge compute"}},
            {"name": "search_news", "args": {"query": "Quantum Dynamics neuromorphic edge compute"}},
        ],
        "tool_results": {"search_papers": [], "search_news": []},
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
    # single-loop has no independent verifier, so its script represents the honest
    # best case (only the real item) — it is not exercised against the hallucination
    # attempt the fleet lane above is.
    single={
        "tool_calls": [{"name": "search_github", "args": {"query": "open-source vector database"}}],
        "tool_results": {
            "search_github": [
                {
                    "full_name": "acme/vectordb-lite",
                    "html_url": "https://github.com/acme/vectordb-lite",
                    "description": "Lightweight embedded vector database.",
                    "stargazers_count": 420,
                }
            ]
        },
        "items": [
            {
                "source": "github",
                "external_id": "https://github.com/acme/vectordb-lite",
                "title": "acme/vectordb-lite",
                "url": "https://github.com/acme/vectordb-lite",
                "summary": "Lightweight embedded vector database, direct competitor.",
                "relevance_reason": "Directly competing embedded vector database.",
                "date": None, "engagement": 420, "organization": "Acme",
            },
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
    # single-loop has no replanning mechanism, so its script is deliberately built
    # from the first two lanes only — it never opens the news lane that recovers
    # coverage. That gap (fleet recovers, single stays thin) IS the comparison.
    single={
        "tool_calls": [
            {"name": "search_papers", "args": {"query": "federated learning mobile keyboard"}},
            {"name": "search_patents", "args": {"query": "federated learning mobile keyboard"}},
        ],
        "tool_results": {
            "search_papers": [
                {
                    "title": "Federated Learning for Next-Word Prediction on Mobile Keyboards",
                    "url": "https://arxiv.org/abs/9999.0002",
                    "year": 2026,
                    "citationCount": 40,
                    "externalIds": {"DOI": "10.1234/fl-keyboard"},
                }
            ],
            "search_patents": [],
        },
        "items": [
            {
                "source": "research",
                "external_id": "10.1234/fl-keyboard",
                "title": "Federated Learning for Next-Word Prediction on Mobile Keyboards",
                "url": "https://arxiv.org/abs/9999.0002",
                "summary": "Federated learning approach to on-device next-word prediction for mobile keyboards.",
                "relevance_reason": "Directly relevant research.",
                "date": "2026-01-20", "engagement": 40, "organization": "",
            },
        ],
        "coverage_ok": False,
        "coverage_gaps": ["patents: no results for federated learning mobile keyboard"],
        "executive_summary": "Found relevant research but no patent activity; coverage stayed thin (the single-agent loop has no replanning mechanism to recover it).",
    },
    expect={
        "expect_replanned": True,
        "expected_kept_ids": {"10.1234/fl-keyboard", "https://news.example.com/keybird-federated"},
        "expected_kept_ids_single": {"10.1234/fl-keyboard"},
    },
)


# ---------------------------------------------------------------------------
# The cases above were hand-written to prove the harness shape. Everything below
# uses the builders in case_builders.py (imported here, after Case/ResearchLane are
# defined, to avoid a circular import) so the dataset can grow to a real benchmark
# size without every case re-deriving the planner/analyst/verifier script wiring.
# ---------------------------------------------------------------------------

from .case_builders import (  # noqa: E402
    adversarial_case,
    ambiguous_case,
    contradictory_case,
    incomplete_case,
    normal_case,
    replanning_case,
    tool_failure_case,
)

# --- normal: 7 more, across varied domains -----------------------------------

NORMAL_002 = normal_case(
    "normal-002",
    "find developments in autonomous drone delivery",
    "Last-mile logistics company evaluating autonomous drone delivery for suburban routes.",
    [
        {
            "question": "What recent research exists on autonomous drone delivery routing and safety?",
            "source": "research", "query": "autonomous drone delivery routing safety",
            "raw": {"title": "Safe Multi-Drone Routing for Suburban Last-Mile Delivery", "url": "https://arxiv.org/abs/9999.0101", "year": 2026, "citationCount": 8, "externalIds": {"DOI": "10.1234/drone-route"}},
            "item": {"source": "research", "external_id": "10.1234/drone-route", "title": "Safe Multi-Drone Routing for Suburban Last-Mile Delivery", "url": "https://arxiv.org/abs/9999.0101", "summary": "Routing and collision-avoidance approach for multi-drone suburban delivery fleets.", "date": "2026-01-05", "engagement": 8, "organization": ""},
            "why": "Directly relevant to suburban delivery routing safety.",
        },
        {
            "question": "What competitor news exists on drone delivery service launches?",
            "source": "news", "query": "drone delivery service launch suburban",
            "raw": {"title": "SkyParcel Expands Drone Delivery to Suburban Markets", "url": "https://news.example.com/skyparcel-suburban", "publishedAt": "2026-02-10"},
            "item": {"source": "news", "external_id": "https://news.example.com/skyparcel-suburban", "title": "SkyParcel Expands Drone Delivery to Suburban Markets", "url": "https://news.example.com/skyparcel-suburban", "summary": "SkyParcel announced expansion of its drone delivery service into suburban markets.", "date": "2026-02-10", "engagement": None, "organization": "SkyParcel"},
            "why": "Direct competitor expanding into the same market segment.",
        },
    ],
)

NORMAL_003 = normal_case(
    "normal-003",
    "find developments in CRISPR delivery systems",
    "Biotech startup developing non-viral CRISPR delivery vectors for in-vivo gene editing.",
    [
        {
            "question": "What recent research exists on non-viral CRISPR delivery vectors?",
            "source": "research", "query": "non-viral CRISPR delivery vector",
            "raw": {"title": "Lipid Nanoparticle Delivery of CRISPR-Cas9 for In-Vivo Editing", "url": "https://arxiv.org/abs/9999.0102", "year": 2026, "citationCount": 25, "externalIds": {"DOI": "10.1234/crispr-lnp"}},
            "item": {"source": "research", "external_id": "10.1234/crispr-lnp", "title": "Lipid Nanoparticle Delivery of CRISPR-Cas9 for In-Vivo Editing", "url": "https://arxiv.org/abs/9999.0102", "summary": "Lipid nanoparticle formulation improves in-vivo delivery efficiency of CRISPR-Cas9 editing components.", "date": "2026-01-18", "engagement": 25, "organization": ""},
            "why": "Directly relevant non-viral delivery mechanism.",
        },
        {
            "question": "What patent activity exists on non-viral CRISPR delivery vectors?",
            "source": "patent", "query": "non-viral CRISPR delivery vector",
            "raw": {"title": "Lipid Nanoparticle Formulation for Gene-Editing Cargo Delivery", "url": "https://patents.example.com/lnp-crispr-001", "publication_number": "US12000111B2", "assignee": "GeneVector Inc"},
            "item": {"source": "patent", "external_id": "US12000111B2", "title": "Lipid Nanoparticle Formulation for Gene-Editing Cargo Delivery", "url": "https://patents.example.com/lnp-crispr-001", "summary": "GeneVector filed a patent on a lipid nanoparticle formulation for gene-editing cargo delivery.", "date": "2026-01-22", "engagement": None, "organization": "GeneVector Inc"},
            "why": "Competitor IP directly in the same delivery mechanism.",
        },
    ],
)

NORMAL_004 = normal_case(
    "normal-004",
    "find developments in serverless edge compute platforms",
    "Cloud infrastructure startup building a serverless edge compute platform for latency-sensitive apps.",
    [
        {
            "question": "What open-source projects compete in serverless edge compute?",
            "source": "github", "query": "serverless edge compute platform",
            "raw": {"full_name": "edgehub/edge-runtime", "html_url": "https://github.com/edgehub/edge-runtime", "description": "Open-source serverless runtime for edge compute.", "stargazers_count": 1800},
            "item": {"source": "github", "external_id": "https://github.com/edgehub/edge-runtime", "title": "edgehub/edge-runtime", "url": "https://github.com/edgehub/edge-runtime", "summary": "Open-source serverless runtime targeting edge compute deployments, direct overlap.", "date": None, "engagement": 1800, "organization": "EdgeHub"},
            "why": "Direct open-source competitor in the same runtime category.",
        },
        {
            "question": "What news exists on serverless edge compute product launches?",
            "source": "news", "query": "serverless edge compute platform launch",
            "raw": {"title": "Latchkey Cloud Launches Serverless Edge Platform", "url": "https://news.example.com/latchkey-edge", "publishedAt": "2026-01-30"},
            "item": {"source": "news", "external_id": "https://news.example.com/latchkey-edge", "title": "Latchkey Cloud Launches Serverless Edge Platform", "url": "https://news.example.com/latchkey-edge", "summary": "Latchkey Cloud launched a commercial serverless edge compute platform for latency-sensitive workloads.", "date": "2026-01-30", "engagement": None, "organization": "Latchkey Cloud"},
            "why": "Direct commercial competitor launch in the same category.",
        },
    ],
)

NORMAL_005 = normal_case(
    "normal-005",
    "find developments in AR/VR haptic gloves",
    "Consumer hardware startup building haptic feedback gloves for AR/VR training simulations.",
    [
        {
            "question": "What recent research exists on haptic feedback gloves for VR?",
            "source": "research", "query": "haptic feedback glove VR training",
            "raw": {"title": "Force-Feedback Glove Design for VR Skills Training", "url": "https://arxiv.org/abs/9999.0103", "year": 2025, "citationCount": 14, "externalIds": {"DOI": "10.1234/haptic-glove"}},
            "item": {"source": "research", "external_id": "10.1234/haptic-glove", "title": "Force-Feedback Glove Design for VR Skills Training", "url": "https://arxiv.org/abs/9999.0103", "summary": "Force-feedback actuator layout for a VR training glove, evaluated on manual-skills tasks.", "date": "2025-11-12", "engagement": 14, "organization": ""},
            "why": "Directly relevant actuator design for VR training gloves.",
        },
        {
            "question": "What discussion exists on Hacker News about haptic VR hardware?",
            "source": "social", "query": "haptic VR glove hardware",
            "raw": {"objectID": "hn-hapt-1", "title": "Show HN: We built an open-source haptic VR glove", "url": "https://news.ycombinator.com/item?id=1000101", "points": 210},
            "item": {"source": "social", "external_id": "hn-hapt-1", "title": "Show HN: We built an open-source haptic VR glove", "url": "https://news.ycombinator.com/item?id=1000101", "summary": "Community project sharing an open-source haptic VR glove design with strong engagement.", "date": "2026-02-05", "engagement": 210, "organization": ""},
            "why": "Strong community engagement signal on directly competing hardware.",
        },
    ],
)

NORMAL_006 = normal_case(
    "normal-006",
    "find developments in zero-trust network access",
    "Enterprise security startup building a zero-trust network access (ZTNA) product for remote workforces.",
    [
        {
            "question": "What patent activity exists on zero-trust network access?",
            "source": "patent", "query": "zero-trust network access",
            "raw": {"title": "Continuous Device Posture Verification for Zero-Trust Access", "url": "https://patents.example.com/ztna-001", "publication_number": "US12000222B2", "assignee": "Perimeterless Inc"},
            "item": {"source": "patent", "external_id": "US12000222B2", "title": "Continuous Device Posture Verification for Zero-Trust Access", "url": "https://patents.example.com/ztna-001", "summary": "Perimeterless filed a patent for continuous device posture verification in ZTNA systems.", "date": "2026-01-08", "engagement": None, "organization": "Perimeterless Inc"},
            "why": "Direct competitor IP in the same ZTNA mechanism.",
        },
        {
            "question": "What news exists on zero-trust network access product announcements?",
            "source": "news", "query": "zero-trust network access product launch",
            "raw": {"title": "Perimeterless Raises Series B for Zero-Trust Platform", "url": "https://news.example.com/perimeterless-series-b", "publishedAt": "2026-02-12"},
            "item": {"source": "news", "external_id": "https://news.example.com/perimeterless-series-b", "title": "Perimeterless Raises Series B for Zero-Trust Platform", "url": "https://news.example.com/perimeterless-series-b", "summary": "Perimeterless raised a Series B round to expand its zero-trust access platform.", "date": "2026-02-12", "engagement": None, "organization": "Perimeterless Inc"},
            "why": "Funding signal reinforcing the same competitor's momentum.",
        },
    ],
)

NORMAL_007 = normal_case(
    "normal-007",
    "find developments in agri-tech soil sensors",
    "Precision agriculture startup building low-cost networked soil-moisture and nutrient sensors.",
    [
        {
            "question": "What recent research exists on low-cost networked soil sensors?",
            "source": "research", "query": "low-cost networked soil moisture sensor",
            "raw": {"title": "Low-Power LoRa Soil Sensor Network for Smallholder Farms", "url": "https://arxiv.org/abs/9999.0104", "year": 2026, "citationCount": 6, "externalIds": {"DOI": "10.1234/soil-lora"}},
            "item": {"source": "research", "external_id": "10.1234/soil-lora", "title": "Low-Power LoRa Soil Sensor Network for Smallholder Farms", "url": "https://arxiv.org/abs/9999.0104", "summary": "Low-power LoRa-based soil moisture and nutrient sensor network designed for smallholder farms.", "date": "2026-01-25", "engagement": 6, "organization": ""},
            "why": "Directly relevant low-cost sensor network design.",
        },
        {
            "question": "What GitHub projects compete in open-source soil sensor firmware?",
            "source": "github", "query": "open source soil sensor firmware LoRa",
            "raw": {"full_name": "greenfield/soil-node", "html_url": "https://github.com/greenfield/soil-node", "description": "Open-source firmware for LoRa soil sensor nodes.", "stargazers_count": 340},
            "item": {"source": "github", "external_id": "https://github.com/greenfield/soil-node", "title": "greenfield/soil-node", "url": "https://github.com/greenfield/soil-node", "summary": "Open-source LoRa soil sensor firmware project, direct overlap with the product category.", "date": None, "engagement": 340, "organization": "Greenfield"},
            "why": "Open-source alternative in the same product category.",
        },
    ],
)

NORMAL_008 = normal_case(
    "normal-008",
    "find developments in LLM inference chips",
    "Semiconductor startup designing an ASIC for low-power LLM inference at the edge.",
    [
        {
            "question": "What recent research exists on low-power LLM inference ASICs?",
            "source": "research", "query": "low-power LLM inference ASIC",
            "raw": {"title": "A 4-bit Weight-Stationary ASIC for Edge LLM Inference", "url": "https://arxiv.org/abs/9999.0105", "year": 2026, "citationCount": 33, "externalIds": {"DOI": "10.1234/llm-asic"}},
            "item": {"source": "research", "external_id": "10.1234/llm-asic", "title": "A 4-bit Weight-Stationary ASIC for Edge LLM Inference", "url": "https://arxiv.org/abs/9999.0105", "summary": "4-bit weight-stationary ASIC architecture achieving low-power edge LLM inference.", "date": "2026-02-01", "engagement": 33, "organization": ""},
            "why": "Directly relevant chip architecture for the same use case.",
        },
        {
            "question": "What patent activity exists on low-power LLM inference chips?",
            "source": "patent", "query": "low-power LLM inference chip",
            "raw": {"title": "Weight-Stationary Dataflow for Low-Power Transformer Inference", "url": "https://patents.example.com/llm-asic-001", "publication_number": "US12000333B2", "assignee": "Tensilith"},
            "item": {"source": "patent", "external_id": "US12000333B2", "title": "Weight-Stationary Dataflow for Low-Power Transformer Inference", "url": "https://patents.example.com/llm-asic-001", "summary": "Tensilith filed a patent on a weight-stationary dataflow for low-power transformer inference chips.", "date": "2026-01-14", "engagement": None, "organization": "Tensilith"},
            "why": "Direct competitor IP in the same chip architecture space.",
        },
    ],
)


# --- tool_failure: 7 more --------------------------------------------------

TOOL_FAILURE_002 = tool_failure_case(
    "tool_failure-002", "find developments in quantum error correction chips",
    "Quantum computing startup tracking error-correction hardware progress.",
    failing={"question": "What patent activity exists on quantum error correction hardware?", "source": "patent", "query": "quantum error correction chip", "error": RuntimeError("HTTPStatusError: 503 Service Unavailable"), "gap": "patents: source unavailable after retry"},
    working={"question": "What recent research exists on quantum error correction hardware?", "source": "research", "query": "quantum error correction hardware", "raw": {"title": "Surface-Code Error Correction on a 100-Qubit Chip", "url": "https://arxiv.org/abs/9999.0106", "year": 2026, "citationCount": 51, "externalIds": {"DOI": "10.1234/qec-100"}}, "item": {"source": "research", "external_id": "10.1234/qec-100", "title": "Surface-Code Error Correction on a 100-Qubit Chip", "url": "https://arxiv.org/abs/9999.0106", "summary": "Demonstrates surface-code error correction on a 100-qubit superconducting chip.", "date": "2026-01-30", "engagement": 51, "organization": ""}, "why": "Directly relevant hardware milestone."},
)

TOOL_FAILURE_003 = tool_failure_case(
    "tool_failure-003", "find developments in humanoid robotics actuators",
    "Robotics startup tracking actuator technology for humanoid robots.",
    failing={"question": "What GitHub projects exist for open-source humanoid actuator control?", "source": "github", "query": "open source humanoid actuator control", "error": ConnectionError("connection reset by peer"), "gap": "github: connection failed after retry"},
    working={"question": "What news exists on humanoid robot actuator announcements?", "source": "news", "query": "humanoid robot actuator announcement", "raw": {"title": "Ferrum Robotics Unveils New High-Torque Actuator", "url": "https://news.example.com/ferrum-actuator", "publishedAt": "2026-02-08"}, "item": {"source": "news", "external_id": "https://news.example.com/ferrum-actuator", "title": "Ferrum Robotics Unveils New High-Torque Actuator", "url": "https://news.example.com/ferrum-actuator", "summary": "Ferrum Robotics unveiled a new high-torque actuator for humanoid robot legs.", "date": "2026-02-08", "engagement": None, "organization": "Ferrum Robotics"}, "why": "Direct competitor hardware announcement."},
)

TOOL_FAILURE_004 = tool_failure_case(
    "tool_failure-004", "find developments in carbon capture materials",
    "Climate-tech startup tracking novel sorbent materials for direct air capture.",
    failing={"question": "What news exists on carbon capture material announcements?", "source": "news", "query": "carbon capture sorbent material announcement", "error": TimeoutError("request timed out after 10s"), "gap": "news: timed out after retry"},
    working={"question": "What recent research exists on novel direct air capture sorbents?", "source": "research", "query": "direct air capture sorbent material", "raw": {"title": "MOF-Based Sorbent with Improved CO2 Capture Kinetics", "url": "https://arxiv.org/abs/9999.0107", "year": 2026, "citationCount": 19, "externalIds": {"DOI": "10.1234/dac-mof"}}, "item": {"source": "research", "external_id": "10.1234/dac-mof", "title": "MOF-Based Sorbent with Improved CO2 Capture Kinetics", "url": "https://arxiv.org/abs/9999.0107", "summary": "A metal-organic-framework sorbent showing improved CO2 capture kinetics for direct air capture.", "date": "2026-01-19", "engagement": 19, "organization": ""}, "why": "Directly relevant sorbent material advance."},
)

TOOL_FAILURE_005 = tool_failure_case(
    "tool_failure-005", "find developments in synthetic biology enzymes",
    "Industrial biotech startup engineering enzymes for plastic degradation.",
    failing={"question": "What patent activity exists on engineered plastic-degrading enzymes?", "source": "patent", "query": "engineered plastic degrading enzyme", "error": RuntimeError("HTTPStatusError: 429 Too Many Requests"), "gap": "patents: rate-limited after retry"},
    working={"question": "What recent research exists on engineered plastic-degrading enzymes?", "source": "research", "query": "engineered plastic degrading enzyme", "raw": {"title": "Directed Evolution of a Fast PET-Degrading Enzyme", "url": "https://arxiv.org/abs/9999.0108", "year": 2026, "citationCount": 44, "externalIds": {"DOI": "10.1234/pet-enzyme"}}, "item": {"source": "research", "external_id": "10.1234/pet-enzyme", "title": "Directed Evolution of a Fast PET-Degrading Enzyme", "url": "https://arxiv.org/abs/9999.0108", "summary": "Directed-evolution approach producing a substantially faster PET-degrading enzyme variant.", "date": "2026-02-02", "engagement": 44, "organization": ""}, "why": "Directly relevant enzyme engineering advance."},
)

TOOL_FAILURE_006 = tool_failure_case(
    "tool_failure-006", "find developments in satellite IoT connectivity",
    "IoT hardware startup evaluating direct-to-satellite connectivity modules.",
    failing={"question": "What social/HN discussion exists about satellite IoT connectivity?", "source": "social", "query": "satellite IoT connectivity module", "error": RuntimeError("HTTPStatusError: 502 Bad Gateway"), "gap": "social: gateway error after retry"},
    working={"question": "What news exists on satellite IoT connectivity product launches?", "source": "news", "query": "satellite IoT connectivity module launch", "raw": {"title": "OrbitLink Ships Direct-to-Satellite IoT Module", "url": "https://news.example.com/orbitlink-module", "publishedAt": "2026-01-27"}, "item": {"source": "news", "external_id": "https://news.example.com/orbitlink-module", "title": "OrbitLink Ships Direct-to-Satellite IoT Module", "url": "https://news.example.com/orbitlink-module", "summary": "OrbitLink began shipping a direct-to-satellite IoT connectivity module.", "date": "2026-01-27", "engagement": None, "organization": "OrbitLink"}, "why": "Direct competitor product shipment."},
)

TOOL_FAILURE_007 = tool_failure_case(
    "tool_failure-007", "find developments in battery recycling chemistry",
    "Battery recycling startup tracking hydrometallurgical recovery process research.",
    failing={"question": "What GitHub projects exist for battery recycling process simulation?", "source": "github", "query": "battery recycling process simulation", "error": RuntimeError("HTTPStatusError: 403 Forbidden"), "gap": "github: forbidden after retry"},
    working={"question": "What recent research exists on hydrometallurgical battery recovery?", "source": "research", "query": "hydrometallurgical lithium battery recovery", "raw": {"title": "Selective Lithium Recovery via Low-pH Hydrometallurgy", "url": "https://arxiv.org/abs/9999.0109", "year": 2025, "citationCount": 22, "externalIds": {"DOI": "10.1234/li-recovery"}}, "item": {"source": "research", "external_id": "10.1234/li-recovery", "title": "Selective Lithium Recovery via Low-pH Hydrometallurgy", "url": "https://arxiv.org/abs/9999.0109", "summary": "A low-pH hydrometallurgical process improving selective lithium recovery from spent batteries.", "date": "2025-12-10", "engagement": 22, "organization": ""}, "why": "Directly relevant recovery process advance."},
)

TOOL_FAILURE_008 = tool_failure_case(
    "tool_failure-008", "find developments in digital twin manufacturing software",
    "Industrial software startup building digital-twin simulation for factory lines.",
    failing={"question": "What news exists on digital twin manufacturing product launches?", "source": "news", "query": "digital twin manufacturing software launch", "error": TimeoutError("request timed out after 10s"), "gap": "news: timed out after retry"},
    working={"question": "What patent activity exists on digital-twin factory simulation?", "source": "patent", "query": "digital twin factory line simulation", "raw": {"title": "Real-Time Synchronization Method for Factory Digital Twins", "url": "https://patents.example.com/dtwin-001", "publication_number": "US12000444B2", "assignee": "Mirrorworks"}, "item": {"source": "patent", "external_id": "US12000444B2", "title": "Real-Time Synchronization Method for Factory Digital Twins", "url": "https://patents.example.com/dtwin-001", "summary": "Mirrorworks filed a patent on real-time synchronization between factory lines and their digital twins.", "date": "2026-01-16", "engagement": None, "organization": "Mirrorworks"}, "why": "Direct competitor IP in the same product category."},
)


# --- contradictory: 7 more, source pairs varied across the authority table -

CONTRADICTORY_002 = contradictory_case(
    "contradictory-002", "assess whether Ignis Fusion is nearing commercial fusion confinement",
    "Fusion energy startup evaluating whether competitor Ignis Fusion has a credible path to commercial confinement.",
    org="Ignis Fusion",
    hot={"question": "What patent activity exists for Ignis Fusion in plasma confinement?", "source": "patent", "query": "Ignis Fusion plasma confinement", "raw": {"title": "Ignis Fusion High-Field Magnetic Confinement Coil Design", "url": "https://patents.example.com/ignis-001", "publication_number": "US12000555B2", "assignee": "Ignis Fusion"}, "item": {"source": "patent", "external_id": "US12000555B2", "title": "Ignis Fusion High-Field Magnetic Confinement Coil Design", "url": "https://patents.example.com/ignis-001", "summary": "Ignis Fusion filed a patent on a high-field magnetic confinement coil design for compact fusion reactors.", "date": None, "engagement": None, "organization": "Ignis Fusion"}, "why": "Direct patent evidence of confinement hardware progress."},
    cold={"question": "What social sentiment exists about Ignis Fusion?", "source": "social", "query": "Ignis Fusion", "raw": {"objectID": "hn-ignis-1", "title": "Ignis Fusion is hiring an office manager", "url": "https://news.ycombinator.com/item?id=1000201", "points": 2}, "item": {"source": "social", "external_id": "hn-ignis-1", "title": "Ignis Fusion is hiring an office manager", "url": "https://news.ycombinator.com/item?id=1000201", "summary": "A low-engagement hiring post about an administrative office role at Ignis Fusion.", "date": "2015-03-01", "engagement": 2, "organization": "Ignis Fusion"}, "why": "Weak, tangential public signal about the same organization."},
    note="Strong patent activity in confinement hardware is not yet reflected in any public or social visibility — likely early-stage, undisclosed work.",
)

CONTRADICTORY_003 = contradictory_case(
    "contradictory-003", "assess whether Triton Marine is entering autonomous underwater vehicles",
    "Marine robotics company evaluating whether Triton Marine is a credible AUV competitor.",
    org="Triton Marine",
    hot={"question": "What research exists on Triton Marine's autonomous underwater vehicle work?", "source": "research", "query": "Triton Marine autonomous underwater vehicle", "raw": {"title": "Triton Marine Deep-Sea Autonomous Underwater Vehicle Navigation", "url": "https://arxiv.org/abs/9999.0201", "year": 2026, "citationCount": 17, "externalIds": {"DOI": "10.1234/triton-auv"}}, "item": {"source": "research", "external_id": "10.1234/triton-auv", "title": "Triton Marine Deep-Sea Autonomous Underwater Vehicle Navigation", "url": "https://arxiv.org/abs/9999.0201", "summary": "Triton Marine researchers published a deep-sea autonomous underwater vehicle navigation method.", "date": None, "engagement": 17, "organization": "Triton Marine"}, "why": "Direct research evidence of AUV navigation work."},
    cold={"question": "What web coverage exists about Triton Marine?", "source": "web", "query": "Triton Marine company", "raw": {"title": "Triton Marine's Office Move Covered in Local Business Blog", "url": "https://blog.example.com/triton-marine-office-move", "snippet": "A local business blog post about Triton Marine relocating its headquarters office."}, "item": {"source": "web", "external_id": "https://blog.example.com/triton-marine-office-move", "title": "Triton Marine's Office Move Covered in Local Business Blog", "url": "https://blog.example.com/triton-marine-office-move", "summary": "A local business blog post about an office relocation, unrelated to technical product activity.", "date": "2015-06-15", "engagement": None, "organization": "Triton Marine"}, "why": "Weak, tangential public web signal about the same organization."},
    note="Research-side navigation work is not yet reflected in public web coverage — likely pre-announcement technical progress.",
)

CONTRADICTORY_004 = contradictory_case(
    "contradictory-004", "assess whether Retina Systems is a threat in neuromorphic vision sensors",
    "Computer vision hardware company evaluating whether Retina Systems is a credible neuromorphic sensor competitor.",
    org="Retina Systems",
    hot={"question": "What patent activity exists for Retina Systems in neuromorphic vision sensors?", "source": "patent", "query": "Retina Systems neuromorphic vision sensor", "raw": {"title": "Retina Systems Event-Based Neuromorphic Image Sensor Array", "url": "https://patents.example.com/retina-001", "publication_number": "US12000666B2", "assignee": "Retina Systems"}, "item": {"source": "patent", "external_id": "US12000666B2", "title": "Retina Systems Event-Based Neuromorphic Image Sensor Array", "url": "https://patents.example.com/retina-001", "summary": "Retina Systems filed a patent on an event-based neuromorphic image sensor array for low-power vision.", "date": None, "engagement": 45, "organization": "Retina Systems"}, "why": "Direct patent evidence of neuromorphic sensor hardware."},
    cold={"question": "What news coverage exists about Retina Systems?", "source": "news", "query": "Retina Systems company news", "raw": {"title": "Retina Systems Sponsors Local Youth Sports League", "url": "https://news.example.com/retina-sponsorship", "publishedAt": "2016-04-01"}, "item": {"source": "news", "external_id": "https://news.example.com/retina-sponsorship", "title": "Retina Systems Sponsors Local Youth Sports League", "url": "https://news.example.com/retina-sponsorship", "summary": "A community sponsorship announcement about a youth sports league, unrelated to any product or engineering activity.", "date": "2016-04-01", "engagement": None, "organization": "Retina Systems"}, "why": "Weak, tangential public news signal about the same organization."},
    note="Patent activity in neuromorphic sensor hardware has no matching public news footprint — likely stealth-mode technical work.",
)

CONTRADICTORY_005 = contradictory_case(
    "contradictory-005", "assess whether Ferment Labs is entering precision fermentation food tech",
    "Alt-protein company evaluating whether Ferment Labs is a credible precision-fermentation competitor.",
    org="Ferment Labs",
    hot={"question": "What research exists on Ferment Labs's precision fermentation work?", "source": "research", "query": "Ferment Labs precision fermentation protein", "raw": {"title": "Ferment Labs High-Yield Precision Fermentation Strain Engineering", "url": "https://arxiv.org/abs/9999.0202", "year": 2026, "citationCount": 29, "externalIds": {"DOI": "10.1234/ferment-strain"}}, "item": {"source": "research", "external_id": "10.1234/ferment-strain", "title": "Ferment Labs High-Yield Precision Fermentation Strain Engineering", "url": "https://arxiv.org/abs/9999.0202", "summary": "Ferment Labs researchers published a high-yield precision fermentation strain-engineering method.", "date": None, "engagement": 29, "organization": "Ferment Labs"}, "why": "Direct research evidence of fermentation strain improvements."},
    cold={"question": "What social sentiment exists about Ferment Labs?", "source": "social", "query": "Ferment Labs", "raw": {"objectID": "hn-ferment-1", "title": "Ferment Labs is hiring a receptionist", "url": "https://news.ycombinator.com/item?id=1000301", "points": 1}, "item": {"source": "social", "external_id": "hn-ferment-1", "title": "Ferment Labs is hiring a receptionist", "url": "https://news.ycombinator.com/item?id=1000301", "summary": "A minimal-engagement administrative hiring post about Ferment Labs.", "date": "2015-08-01", "engagement": 1, "organization": "Ferment Labs"}, "why": "Weak, tangential public signal about the same organization."},
    note="Strain-engineering research progress is not yet reflected in public visibility — likely pre-launch technical work.",
)

CONTRADICTORY_006 = contradictory_case(
    "contradictory-006", "assess whether Orbital Sweep is a credible threat in space debris removal",
    "Space robotics company evaluating whether Orbital Sweep has real technical traction in debris removal.",
    org="Orbital Sweep",
    hot={"question": "What patent activity exists for Orbital Sweep in debris capture mechanisms?", "source": "patent", "query": "Orbital Sweep debris capture mechanism", "raw": {"title": "Orbital Sweep Net-Capture Mechanism for Space Debris Removal", "url": "https://patents.example.com/orbital-001", "publication_number": "US12000777B2", "assignee": "Orbital Sweep"}, "item": {"source": "patent", "external_id": "US12000777B2", "title": "Orbital Sweep Net-Capture Mechanism for Space Debris Removal", "url": "https://patents.example.com/orbital-001", "summary": "Orbital Sweep filed a patent on a net-capture mechanism for removing small space debris.", "date": None, "engagement": None, "organization": "Orbital Sweep"}, "why": "Direct patent evidence of debris-capture hardware."},
    cold={"question": "What web coverage exists about Orbital Sweep?", "source": "web", "query": "Orbital Sweep company", "raw": {"title": "Orbital Sweep Featured in Company Culture Roundup", "url": "https://blog.example.com/orbital-sweep-culture", "snippet": "A general company-culture blog post about Orbital Sweep's remote work policy."}, "item": {"source": "web", "external_id": "https://blog.example.com/orbital-sweep-culture", "title": "Orbital Sweep Featured in Company Culture Roundup", "url": "https://blog.example.com/orbital-sweep-culture", "summary": "A general workplace-culture blog post, unrelated to technical product activity.", "date": "2015-09-20", "engagement": None, "organization": "Orbital Sweep"}, "why": "Weak, tangential public web signal about the same organization."},
    note="Debris-capture patent activity has no matching public web footprint — likely undisclosed technical development.",
)

CONTRADICTORY_007 = contradictory_case(
    "contradictory-007", "assess whether Cargo Motion is a credible threat in warehouse autonomous mobile robots",
    "Warehouse automation company evaluating whether Cargo Motion is a credible AMR competitor.",
    org="Cargo Motion",
    hot={"question": "What research exists on Cargo Motion's warehouse AMR fleet coordination?", "source": "research", "query": "Cargo Motion warehouse autonomous mobile robot fleet", "raw": {"title": "Cargo Motion Decentralized Fleet Coordination for Warehouse AMRs", "url": "https://arxiv.org/abs/9999.0203", "year": 2026, "citationCount": 21, "externalIds": {"DOI": "10.1234/cargo-amr"}}, "item": {"source": "research", "external_id": "10.1234/cargo-amr", "title": "Cargo Motion Decentralized Fleet Coordination for Warehouse AMRs", "url": "https://arxiv.org/abs/9999.0203", "summary": "Cargo Motion researchers published a decentralized fleet-coordination method for warehouse autonomous mobile robots.", "date": None, "engagement": 21, "organization": "Cargo Motion"}, "why": "Direct research evidence of AMR fleet coordination work."},
    cold={"question": "What news coverage exists about Cargo Motion?", "source": "news", "query": "Cargo Motion company news", "raw": {"title": "Cargo Motion Wins Regional Small Business Award", "url": "https://news.example.com/cargo-motion-award", "publishedAt": "2016-02-14"}, "item": {"source": "news", "external_id": "https://news.example.com/cargo-motion-award", "title": "Cargo Motion Wins Regional Small Business Award", "url": "https://news.example.com/cargo-motion-award", "summary": "A regional small-business award announcement, unrelated to robotics product activity.", "date": "2016-02-14", "engagement": None, "organization": "Cargo Motion"}, "why": "Weak, tangential public news signal about the same organization."},
    note="Fleet-coordination research progress has no matching public news footprint — likely pre-launch technical work.",
)

CONTRADICTORY_008 = contradictory_case(
    "contradictory-008", "assess whether EchoForge is a credible threat in synthetic media detection",
    "Trust-and-safety company evaluating whether EchoForge has real technical traction in voice-clone detection.",
    org="EchoForge",
    hot={"question": "What patent activity exists for EchoForge in synthetic voice detection?", "source": "patent", "query": "EchoForge synthetic voice detection", "raw": {"title": "EchoForge Spectral Artifact Detector for Synthetic Speech", "url": "https://patents.example.com/echoforge-001", "publication_number": "US12000888B2", "assignee": "EchoForge"}, "item": {"source": "patent", "external_id": "US12000888B2", "title": "EchoForge Spectral Artifact Detector for Synthetic Speech", "url": "https://patents.example.com/echoforge-001", "summary": "EchoForge filed a patent on a spectral-artifact detector for identifying synthetic/cloned speech.", "date": None, "engagement": None, "organization": "EchoForge"}, "why": "Direct patent evidence of voice-clone detection hardware/software."},
    cold={"question": "What social sentiment exists about EchoForge?", "source": "social", "query": "EchoForge", "raw": {"objectID": "hn-echo-1", "title": "EchoForge is hiring a facilities coordinator", "url": "https://news.ycombinator.com/item?id=1000401", "points": 2}, "item": {"source": "social", "external_id": "hn-echo-1", "title": "EchoForge is hiring a facilities coordinator", "url": "https://news.ycombinator.com/item?id=1000401", "summary": "A minimal-engagement administrative hiring post about EchoForge.", "date": "2015-11-05", "engagement": 2, "organization": "EchoForge"}, "why": "Weak, tangential public signal about the same organization."},
    note="Detection-technology patent activity is not yet reflected in public visibility — likely undisclosed technical work.",
)


# --- incomplete: 7 more, rumored competitors with genuinely no evidence ----

INCOMPLETE_002 = incomplete_case(
    "incomplete-002", "find evidence of NanoCortex entering the brain-computer interface market",
    "Evaluating a rumored but unconfirmed competitor, 'NanoCortex', in implantable brain-computer interfaces.",
    probes=[
        {"question": "What research exists on NanoCortex's activity?", "source": "research", "query": "NanoCortex brain-computer interface", "gap": "papers: no results for NanoCortex"},
        {"question": "What patent activity exists for NanoCortex?", "source": "patent", "query": "NanoCortex brain-computer interface", "gap": "patents: no results for NanoCortex"},
    ],
)

INCOMPLETE_003 = incomplete_case(
    "incomplete-003", "find evidence of Helios Grid entering the grid-scale storage market",
    "Evaluating a rumored but unconfirmed competitor, 'Helios Grid', in grid-scale energy storage.",
    probes=[
        {"question": "What news exists on Helios Grid's activity?", "source": "news", "query": "Helios Grid grid-scale energy storage", "gap": "news: no results for Helios Grid"},
        {"question": "What patent activity exists for Helios Grid?", "source": "patent", "query": "Helios Grid energy storage", "gap": "patents: no results for Helios Grid"},
    ],
)

INCOMPLETE_004 = incomplete_case(
    "incomplete-004", "find evidence of Verdant Bio entering the lab-grown leather market",
    "Evaluating a rumored but unconfirmed competitor, 'Verdant Bio', in lab-grown/cultivated leather.",
    probes=[
        {"question": "What research exists on Verdant Bio's activity?", "source": "research", "query": "Verdant Bio lab-grown leather", "gap": "papers: no results for Verdant Bio"},
        {"question": "What social discussion exists about Verdant Bio?", "source": "social", "query": "Verdant Bio lab-grown leather", "gap": "social: no results for Verdant Bio"},
    ],
)

INCOMPLETE_005 = incomplete_case(
    "incomplete-005", "find evidence of Pulsewave entering the medical imaging AI market",
    "Evaluating a rumored but unconfirmed competitor, 'Pulsewave', in AI-assisted medical imaging diagnostics.",
    probes=[
        {"question": "What research exists on Pulsewave's activity?", "source": "research", "query": "Pulsewave medical imaging AI", "gap": "papers: no results for Pulsewave"},
        {"question": "What news exists on Pulsewave's activity?", "source": "news", "query": "Pulsewave medical imaging AI", "gap": "news: no results for Pulsewave"},
    ],
)

INCOMPLETE_006 = incomplete_case(
    "incomplete-006", "find evidence of DeepReef entering ocean carbon sequestration",
    "Evaluating a rumored but unconfirmed competitor, 'DeepReef', in ocean-based carbon sequestration.",
    probes=[
        {"question": "What research exists on DeepReef's activity?", "source": "research", "query": "DeepReef ocean carbon sequestration", "gap": "papers: no results for DeepReef"},
        {"question": "What patent activity exists for DeepReef?", "source": "patent", "query": "DeepReef carbon sequestration", "gap": "patents: no results for DeepReef"},
    ],
)

INCOMPLETE_007 = incomplete_case(
    "incomplete-007", "find evidence of Ionix entering the solid electrolyte market",
    "Evaluating a rumored but unconfirmed competitor, 'Ionix', in solid-state battery electrolytes.",
    probes=[
        {"question": "What research exists on Ionix's activity?", "source": "research", "query": "Ionix solid electrolyte battery", "gap": "papers: no results for Ionix"},
        {"question": "What GitHub projects exist related to Ionix?", "source": "github", "query": "Ionix solid electrolyte", "gap": "github: no results for Ionix"},
    ],
)

INCOMPLETE_008 = incomplete_case(
    "incomplete-008", "find evidence of Cortex Robotics entering the surgical robotics market",
    "Evaluating a rumored but unconfirmed competitor, 'Cortex Robotics', in autonomous surgical robotics.",
    probes=[
        {"question": "What research exists on Cortex Robotics's activity?", "source": "research", "query": "Cortex Robotics surgical robot", "gap": "papers: no results for Cortex Robotics"},
        {"question": "What news exists on Cortex Robotics's activity?", "source": "news", "query": "Cortex Robotics surgical robot", "gap": "news: no results for Cortex Robotics"},
    ],
)


# --- adversarial: 7 more, one fabricated item per lane, across sources -----

ADVERSARIAL_002 = adversarial_case(
    "adversarial-002", "find recent research on protein folding prediction models",
    "Computational biology startup tracking competing protein-structure prediction models.",
    question="What recent research exists on protein folding prediction models?", source="research", query="protein folding prediction model",
    raw={"title": "FoldNet: A Lightweight Protein Structure Predictor", "url": "https://arxiv.org/abs/9999.0301", "year": 2026, "citationCount": 60, "externalIds": {"DOI": "10.1234/foldnet"}},
    real_item={"source": "research", "external_id": "10.1234/foldnet", "title": "FoldNet: A Lightweight Protein Structure Predictor", "url": "https://arxiv.org/abs/9999.0301", "summary": "A lightweight protein structure prediction model with competitive accuracy.", "date": "2026-01-11", "engagement": 60, "organization": ""},
    fake_item={"source": "research", "external_id": "10.9999/fabricated-fold", "title": "OmniFold: Perfect Protein Structure Prediction at Zero Cost", "url": "https://arxiv.org/abs/9999.9999", "summary": "A paper the model invented rather than saw in a tool result.", "date": None, "engagement": 5000, "organization": ""},
    why="Directly relevant, grounded protein-folding model.",
)

ADVERSARIAL_003 = adversarial_case(
    "adversarial-003", "find recent patent activity on EV fast-charging connectors",
    "EV infrastructure company tracking competing fast-charging connector patents.",
    question="What patent activity exists on EV fast-charging connectors?", source="patent", query="EV fast charging connector",
    raw={"title": "High-Current Liquid-Cooled EV Charging Connector", "url": "https://patents.example.com/ev-connector-001", "publication_number": "US12000999B2", "assignee": "VoltJack"},
    real_item={"source": "patent", "external_id": "US12000999B2", "title": "High-Current Liquid-Cooled EV Charging Connector", "url": "https://patents.example.com/ev-connector-001", "summary": "VoltJack filed a patent for a liquid-cooled high-current EV charging connector.", "date": "2026-01-09", "engagement": None, "organization": "VoltJack"},
    fake_item={"source": "patent", "external_id": "US99999999B2", "title": "Instant-Charge EV Connector With No Thermal Limits", "url": "https://patents.example.com/fabricated-connector", "summary": "A patent the model invented rather than saw in a tool result.", "date": None, "engagement": None, "organization": ""},
    why="Directly relevant, grounded connector patent.",
)

ADVERSARIAL_004 = adversarial_case(
    "adversarial-004", "find recent news on vertical farming funding rounds",
    "Vertical farming startup tracking competitor funding activity.",
    question="What news exists on vertical farming funding rounds?", source="news", query="vertical farming funding round",
    raw={"title": "GreenStack Raises $40M Series C for Vertical Farming", "url": "https://news.example.com/greenstack-series-c", "publishedAt": "2026-02-03"},
    real_item={"source": "news", "external_id": "https://news.example.com/greenstack-series-c", "title": "GreenStack Raises $40M Series C for Vertical Farming", "url": "https://news.example.com/greenstack-series-c", "summary": "GreenStack raised a $40M Series C round to expand its vertical farming operations.", "date": "2026-02-03", "engagement": None, "organization": "GreenStack"},
    fake_item={"source": "news", "external_id": "https://news.example.com/fabricated-round", "title": "AgriMax Raises $500M Series F for Vertical Farming", "url": "https://news.example.com/fabricated-agrimax", "summary": "A funding article the model invented rather than saw in a tool result.", "date": None, "engagement": None, "organization": "AgriMax"},
    why="Directly relevant, grounded funding announcement.",
)

ADVERSARIAL_005 = adversarial_case(
    "adversarial-005", "find recent Hacker News discussion about home robotics kits",
    "Consumer robotics startup tracking community sentiment on home robotics kits.",
    question="What discussion exists on Hacker News about home robotics kits?", source="social", query="home robotics kit",
    raw={"objectID": "hn-homerobo-1", "title": "Show HN: An open-source home robotics kit for $200", "url": "https://news.ycombinator.com/item?id=1000501", "points": 340},
    real_item={"source": "social", "external_id": "hn-homerobo-1", "title": "Show HN: An open-source home robotics kit for $200", "url": "https://news.ycombinator.com/item?id=1000501", "summary": "A well-engaged community post about an open-source $200 home robotics kit.", "date": "2026-01-29", "engagement": 340, "organization": ""},
    fake_item={"source": "social", "external_id": "hn-fabricated-1", "title": "Show HN: A $10 home robot that beats every competitor", "url": "https://news.ycombinator.com/item?id=9999999", "summary": "A forum post the model invented rather than saw in a tool result.", "date": None, "engagement": 9999, "organization": ""},
    why="Directly relevant, grounded community post.",
)

ADVERSARIAL_006 = adversarial_case(
    "adversarial-006", "find recent Reddit discussion about e-bike battery swap networks",
    "Micromobility startup tracking practitioner sentiment on battery-swap networks.",
    question="What Reddit discussion exists about e-bike battery swap networks?", source="reddit", query="e-bike battery swap network",
    raw={"id": "swapnet1", "title": "SwapNet stations are finally in my city", "url": "https://www.reddit.com/r/ebikes/comments/swapnet1", "subreddit": "r/ebikes", "score": 512, "num_comments": 88, "selftext": "SwapNet's battery swap stations rolled out in my city this week."},
    real_item={"source": "reddit", "external_id": "swapnet1", "title": "SwapNet stations are finally in my city", "url": "https://www.reddit.com/r/ebikes/comments/swapnet1", "summary": "A high-engagement thread about SwapNet's battery-swap station rollout.", "date": "2026-02-06", "engagement": 512, "organization": "SwapNet"},
    fake_item={"source": "reddit", "external_id": "fabricated1", "title": "InstaSwap batteries last 10 years, zero degradation", "url": "https://www.reddit.com/r/ebikes/comments/fabricated1", "summary": "A thread the model invented rather than saw in a tool result.", "date": None, "engagement": 9999, "organization": "InstaSwap"},
    why="Directly relevant, grounded practitioner thread.",
)

ADVERSARIAL_007 = adversarial_case(
    "adversarial-007", "find recent web coverage of AI coding assistant benchmarks",
    "Developer tools startup tracking competitor AI coding assistant benchmark claims.",
    question="What web coverage exists on AI coding assistant benchmarks?", source="web", query="AI coding assistant benchmark",
    raw={"title": "Independent Benchmark: CodeMate Tops Completion Accuracy", "url": "https://blog.example.com/codemate-benchmark", "snippet": "An independent benchmark comparing AI coding assistants on completion accuracy."},
    real_item={"source": "web", "external_id": "https://blog.example.com/codemate-benchmark", "title": "Independent Benchmark: CodeMate Tops Completion Accuracy", "url": "https://blog.example.com/codemate-benchmark", "summary": "An independent benchmark showing CodeMate leading on completion accuracy.", "date": "2026-01-21", "engagement": None, "organization": "CodeMate"},
    fake_item={"source": "web", "external_id": "https://blog.example.com/fabricated-benchmark", "title": "PerfectCode Achieves 100% Benchmark Accuracy", "url": "https://blog.example.com/fabricated-perfectcode", "summary": "A benchmark article the model invented rather than saw in a tool result.", "date": None, "engagement": None, "organization": "PerfectCode"},
    why="Directly relevant, grounded independent benchmark.",
)

ADVERSARIAL_008 = adversarial_case(
    "adversarial-008", "find recent GitHub projects competing with our LLM serving framework",
    "Infra startup tracking competing open-source LLM inference-serving frameworks.",
    question="What open-source projects compete in LLM serving frameworks?", source="github", query="open source LLM serving framework",
    raw={"full_name": "servewell/llm-serve", "html_url": "https://github.com/servewell/llm-serve", "description": "Open-source high-throughput LLM serving framework.", "stargazers_count": 2600},
    real_item={"source": "github", "external_id": "https://github.com/servewell/llm-serve", "title": "servewell/llm-serve", "url": "https://github.com/servewell/llm-serve", "summary": "A high-throughput open-source LLM serving framework, direct overlap.", "date": None, "engagement": 2600, "organization": "ServeWell"},
    fake_item={"source": "github", "external_id": "fabricated/infinite-serve", "title": "infinite-serve: Zero-Latency LLM Serving", "url": "https://github.com/fabricated/infinite-serve", "summary": "A repo the model invented rather than saw in a tool result.", "date": None, "engagement": 50000, "organization": ""},
    why="Directly relevant, grounded serving framework.",
)


# --- replanning: 6 more -----------------------------------------------------

REPLANNING_002 = replanning_case(
    "replanning-002", "find developments in autonomous forklift systems",
    "Warehouse automation company tracking autonomous forklift research and IP.",
    strong={"question": "What research exists on autonomous forklift navigation?", "source": "research", "query": "autonomous forklift navigation", "raw": {"title": "Warehouse-Aware Path Planning for Autonomous Forklifts", "url": "https://arxiv.org/abs/9999.0401", "year": 2026, "citationCount": 15, "externalIds": {"DOI": "10.1234/forklift-nav"}}, "item": {"source": "research", "external_id": "10.1234/forklift-nav", "title": "Warehouse-Aware Path Planning for Autonomous Forklifts", "url": "https://arxiv.org/abs/9999.0401", "summary": "A warehouse-aware path planning method for autonomous forklift navigation.", "date": "2026-01-13", "engagement": 15, "organization": ""}, "why": "Directly relevant navigation research."},
    thin={"question": "What patent activity exists on autonomous forklift systems?", "source": "patent", "query": "autonomous forklift system", "gap": "patents: no results for autonomous forklift systems"},
    new={"question": "What competitor products use autonomous forklift systems?", "source": "news", "query": "competitor autonomous forklift product", "raw": {"title": "LiftWise Ships Autonomous Forklift Fleet", "url": "https://news.example.com/liftwise-fleet", "publishedAt": "2026-02-11"}, "item": {"source": "news", "external_id": "https://news.example.com/liftwise-fleet", "title": "LiftWise Ships Autonomous Forklift Fleet", "url": "https://news.example.com/liftwise-fleet", "summary": "LiftWise shipped its first autonomous forklift fleet to a logistics customer.", "date": "2026-02-11", "engagement": None, "organization": "LiftWise"}},
)

REPLANNING_003 = replanning_case(
    "replanning-003", "find developments in smart contact lens displays",
    "Wearables startup tracking smart contact lens research and competitor products.",
    strong={"question": "What research exists on smart contact lens micro-displays?", "source": "research", "query": "smart contact lens micro display", "raw": {"title": "Micro-LED Array for Smart Contact Lens Displays", "url": "https://arxiv.org/abs/9999.0402", "year": 2026, "citationCount": 27, "externalIds": {"DOI": "10.1234/lens-display"}}, "item": {"source": "research", "external_id": "10.1234/lens-display", "title": "Micro-LED Array for Smart Contact Lens Displays", "url": "https://arxiv.org/abs/9999.0402", "summary": "A micro-LED array design suitable for smart contact lens displays.", "date": "2026-01-24", "engagement": 27, "organization": ""}, "why": "Directly relevant display hardware research."},
    thin={"question": "What news exists on smart contact lens product announcements?", "source": "news", "query": "smart contact lens display announcement", "gap": "news: no results for smart contact lens displays"},
    new={"question": "What open-source projects relate to smart contact lens firmware?", "source": "github", "query": "smart contact lens firmware", "raw": {"full_name": "opticore/lens-firmware", "html_url": "https://github.com/opticore/lens-firmware", "description": "Open-source firmware experiments for micro-display contact lenses.", "stargazers_count": 90}, "item": {"source": "github", "external_id": "https://github.com/opticore/lens-firmware", "title": "opticore/lens-firmware", "url": "https://github.com/opticore/lens-firmware", "summary": "An open-source firmware project for micro-display contact lenses.", "date": None, "engagement": 90, "organization": "OptiCore"}},
)

REPLANNING_004 = replanning_case(
    "replanning-004", "find developments in bioprinted organ scaffolds",
    "Regenerative medicine startup tracking bioprinting research and competitor activity.",
    strong={"question": "What research exists on bioprinted organ scaffolds?", "source": "research", "query": "bioprinted organ scaffold", "raw": {"title": "Vascularized Scaffold Bioprinting for Kidney Tissue", "url": "https://arxiv.org/abs/9999.0403", "year": 2026, "citationCount": 38, "externalIds": {"DOI": "10.1234/bioprint-kidney"}}, "item": {"source": "research", "external_id": "10.1234/bioprint-kidney", "title": "Vascularized Scaffold Bioprinting for Kidney Tissue", "url": "https://arxiv.org/abs/9999.0403", "summary": "A vascularized scaffold bioprinting method demonstrated on kidney tissue constructs.", "date": "2026-02-04", "engagement": 38, "organization": ""}, "why": "Directly relevant scaffold bioprinting research."},
    thin={"question": "What patent activity exists on bioprinted organ scaffolds?", "source": "patent", "query": "bioprinted organ scaffold", "gap": "patents: no results for bioprinted organ scaffolds"},
    new={"question": "What news exists on bioprinting competitor announcements?", "source": "news", "query": "bioprinting organ competitor announcement", "raw": {"title": "OrganForge Announces Bioprinted Kidney Trial", "url": "https://news.example.com/organforge-trial", "publishedAt": "2026-02-14"}, "item": {"source": "news", "external_id": "https://news.example.com/organforge-trial", "title": "OrganForge Announces Bioprinted Kidney Trial", "url": "https://news.example.com/organforge-trial", "summary": "OrganForge announced the start of a bioprinted kidney scaffold trial.", "date": "2026-02-14", "engagement": None, "organization": "OrganForge"}},
)

REPLANNING_005 = replanning_case(
    "replanning-005", "find developments in desalination membrane technology",
    "Water-tech startup tracking desalination membrane research and IP.",
    strong={"question": "What research exists on next-generation desalination membranes?", "source": "research", "query": "next generation desalination membrane", "raw": {"title": "Graphene-Oxide Membrane for Low-Fouling Desalination", "url": "https://arxiv.org/abs/9999.0404", "year": 2026, "citationCount": 31, "externalIds": {"DOI": "10.1234/desal-membrane"}}, "item": {"source": "research", "external_id": "10.1234/desal-membrane", "title": "Graphene-Oxide Membrane for Low-Fouling Desalination", "url": "https://arxiv.org/abs/9999.0404", "summary": "A graphene-oxide membrane design showing reduced fouling in desalination.", "date": "2026-01-17", "engagement": 31, "organization": ""}, "why": "Directly relevant membrane material research."},
    thin={"question": "What social discussion exists about desalination membrane technology?", "source": "social", "query": "desalination membrane technology", "gap": "social: no results for desalination membrane technology"},
    new={"question": "What patent activity exists on low-fouling desalination membranes?", "source": "patent", "query": "low fouling desalination membrane", "raw": {"title": "Anti-Fouling Coating for Reverse Osmosis Membranes", "url": "https://patents.example.com/desal-001", "publication_number": "US12001111B2", "assignee": "AquaPure Membranes"}, "item": {"source": "patent", "external_id": "US12001111B2", "title": "Anti-Fouling Coating for Reverse Osmosis Membranes", "url": "https://patents.example.com/desal-001", "summary": "AquaPure Membranes filed a patent on an anti-fouling coating for reverse-osmosis membranes.", "date": "2026-01-26", "engagement": None, "organization": "AquaPure Membranes"}},
)

REPLANNING_006 = replanning_case(
    "replanning-006", "find developments in wearable ECG patch monitors",
    "Digital health startup tracking wearable cardiac monitoring research and products.",
    strong={"question": "What research exists on wearable ECG patch monitors?", "source": "research", "query": "wearable ECG patch monitor", "raw": {"title": "Low-Power Adhesive ECG Patch for Continuous Arrhythmia Detection", "url": "https://arxiv.org/abs/9999.0405", "year": 2026, "citationCount": 24, "externalIds": {"DOI": "10.1234/ecg-patch"}}, "item": {"source": "research", "external_id": "10.1234/ecg-patch", "title": "Low-Power Adhesive ECG Patch for Continuous Arrhythmia Detection", "url": "https://arxiv.org/abs/9999.0405", "summary": "A low-power adhesive ECG patch design for continuous arrhythmia detection.", "date": "2026-02-07", "engagement": 24, "organization": ""}, "why": "Directly relevant wearable cardiac monitoring research."},
    thin={"question": "What patent activity exists on wearable ECG patch monitors?", "source": "patent", "query": "wearable ECG patch monitor", "gap": "patents: no results for wearable ECG patch monitors"},
    new={"question": "What news exists on wearable ECG patch product launches?", "source": "news", "query": "wearable ECG patch product launch", "raw": {"title": "CardioTag Launches Continuous ECG Patch", "url": "https://news.example.com/cardiotag-launch", "publishedAt": "2026-02-16"}, "item": {"source": "news", "external_id": "https://news.example.com/cardiotag-launch", "title": "CardioTag Launches Continuous ECG Patch", "url": "https://news.example.com/cardiotag-launch", "summary": "CardioTag launched a continuous wearable ECG patch for arrhythmia monitoring.", "date": "2026-02-16", "engagement": None, "organization": "CardioTag"}},
)


# --- ambiguous: 7 new, underspecified goals requiring a stated assumption --

AMBIGUOUS_001 = ambiguous_case(
    "ambiguous-001", "find threats around AI",
    "A general-purpose robotics and automation company, no specific AI sub-domain named in the goal.",
    finding={"question": "What recent research exists at the intersection of AI and robotics automation?", "source": "research", "query": "AI robotics automation", "raw": {"title": "Foundation Models for General-Purpose Robot Manipulation", "url": "https://arxiv.org/abs/9999.0501", "year": 2026, "citationCount": 55, "externalIds": {"DOI": "10.1234/ai-robot-fm"}}, "item": {"source": "research", "external_id": "10.1234/ai-robot-fm", "title": "Foundation Models for General-Purpose Robot Manipulation", "url": "https://arxiv.org/abs/9999.0501", "summary": "A foundation-model approach to general-purpose robot manipulation tasks.", "date": "2026-01-15", "engagement": 55, "organization": ""}, "why": "Relevant under the robotics/automation interpretation of the goal."},
    assumption="The goal 'find threats around AI' does not name a sub-domain, so this run assumed the robotics/automation intersection of AI given the project context.",
)

AMBIGUOUS_002 = ambiguous_case(
    "ambiguous-002", "find opportunities in health",
    "A digital therapeutics company building app-based chronic-condition management, no specific health area named.",
    finding={"question": "What recent research exists on app-based chronic-condition management?", "source": "research", "query": "app-based chronic condition management digital therapeutics", "raw": {"title": "Digital Therapeutic App Improves Diabetes Self-Management Adherence", "url": "https://arxiv.org/abs/9999.0502", "year": 2026, "citationCount": 18, "externalIds": {"DOI": "10.1234/dtx-diabetes"}}, "item": {"source": "research", "external_id": "10.1234/dtx-diabetes", "title": "Digital Therapeutic App Improves Diabetes Self-Management Adherence", "url": "https://arxiv.org/abs/9999.0502", "summary": "A digital therapeutic app shown to improve adherence in diabetes self-management.", "date": "2026-01-28", "engagement": 18, "organization": ""}, "why": "Relevant under the chronic-condition digital therapeutics interpretation of the goal."},
    assumption="The goal 'find opportunities in health' does not name a condition or product area, so this run assumed app-based chronic-condition management given the project context.",
)

AMBIGUOUS_003 = ambiguous_case(
    "ambiguous-003", "find developments in energy",
    "A grid-scale battery storage startup, no specific energy sub-domain named in the goal.",
    finding={"question": "What recent research exists on grid-scale battery storage?", "source": "research", "query": "grid-scale battery storage", "raw": {"title": "Long-Duration Flow Battery for Grid-Scale Storage", "url": "https://arxiv.org/abs/9999.0503", "year": 2026, "citationCount": 34, "externalIds": {"DOI": "10.1234/flow-battery"}}, "item": {"source": "research", "external_id": "10.1234/flow-battery", "title": "Long-Duration Flow Battery for Grid-Scale Storage", "url": "https://arxiv.org/abs/9999.0503", "summary": "A long-duration flow battery design targeting grid-scale storage applications.", "date": "2026-02-01", "engagement": 34, "organization": ""}, "why": "Relevant under the grid-scale storage interpretation of the goal."},
    assumption="The goal 'find developments in energy' does not name a sub-domain, so this run assumed grid-scale storage given the project context.",
)

AMBIGUOUS_004 = ambiguous_case(
    "ambiguous-004", "find risks in supply chain",
    "An electronics contract manufacturer, no specific supply-chain risk category named in the goal.",
    finding={"question": "What news exists on electronics component supply-chain disruptions?", "source": "news", "query": "electronics component supply chain disruption", "raw": {"title": "Semiconductor Substrate Shortage Hits Contract Manufacturers", "url": "https://news.example.com/substrate-shortage", "publishedAt": "2026-02-09"}, "item": {"source": "news", "external_id": "https://news.example.com/substrate-shortage", "title": "Semiconductor Substrate Shortage Hits Contract Manufacturers", "url": "https://news.example.com/substrate-shortage", "summary": "A semiconductor substrate shortage is affecting electronics contract manufacturers.", "date": "2026-02-09", "engagement": None, "organization": ""}, "why": "Relevant under the component-shortage interpretation of the goal."},
    assumption="The goal 'find risks in supply chain' does not name a risk category, so this run assumed component-shortage risk given the project context.",
)

AMBIGUOUS_005 = ambiguous_case(
    "ambiguous-005", "find what's happening in space",
    "A small-satellite IoT connectivity startup, no specific space sub-domain named in the goal.",
    finding={"question": "What recent news exists on small-satellite connectivity constellations?", "source": "news", "query": "small satellite IoT constellation news", "raw": {"title": "New Small-Sat Constellation Targets Rural IoT Coverage", "url": "https://news.example.com/smallsat-constellation", "publishedAt": "2026-01-31"}, "item": {"source": "news", "external_id": "https://news.example.com/smallsat-constellation", "title": "New Small-Sat Constellation Targets Rural IoT Coverage", "url": "https://news.example.com/smallsat-constellation", "summary": "A new small-satellite constellation aims to provide rural IoT connectivity coverage.", "date": "2026-01-31", "engagement": None, "organization": ""}, "why": "Relevant under the small-sat IoT connectivity interpretation of the goal."},
    assumption="The goal 'find what's happening in space' does not name a sub-domain, so this run assumed small-satellite IoT connectivity given the project context.",
)

AMBIGUOUS_006 = ambiguous_case(
    "ambiguous-006", "find news about batteries",
    "An EV battery startup focused on solid-state chemistry, no specific battery angle named in the goal.",
    finding={"question": "What recent news exists on solid-state EV battery developments?", "source": "news", "query": "solid-state EV battery news", "raw": {"title": "Solid-State Battery Pilot Line Breaks Ground", "url": "https://news.example.com/solid-state-pilot-line", "publishedAt": "2026-02-13"}, "item": {"source": "news", "external_id": "https://news.example.com/solid-state-pilot-line", "title": "Solid-State Battery Pilot Line Breaks Ground", "url": "https://news.example.com/solid-state-pilot-line", "summary": "Construction began on a new solid-state battery pilot production line.", "date": "2026-02-13", "engagement": None, "organization": ""}, "why": "Relevant under the solid-state chemistry interpretation of the goal."},
    assumption="The goal 'find news about batteries' does not name a chemistry, so this run assumed solid-state chemistry given the project context.",
)

AMBIGUOUS_007 = ambiguous_case(
    "ambiguous-007", "find competitors in fintech",
    "A B2B embedded-payments startup, no specific fintech vertical named in the goal.",
    finding={"question": "What news exists on embedded B2B payments competitor activity?", "source": "news", "query": "embedded B2B payments competitor", "raw": {"title": "PayRail Launches Embedded B2B Payments API", "url": "https://news.example.com/payrail-api", "publishedAt": "2026-02-05"}, "item": {"source": "news", "external_id": "https://news.example.com/payrail-api", "title": "PayRail Launches Embedded B2B Payments API", "url": "https://news.example.com/payrail-api", "summary": "PayRail launched a new embedded B2B payments API targeting the same market segment.", "date": "2026-02-05", "engagement": None, "organization": "PayRail"}, "why": "Relevant under the embedded B2B payments interpretation of the goal."},
    assumption="The goal 'find competitors in fintech' does not name a vertical, so this run assumed embedded B2B payments given the project context.",
)


DATASET: list[Case] = [
    NORMAL_001, NORMAL_002, NORMAL_003, NORMAL_004, NORMAL_005, NORMAL_006, NORMAL_007, NORMAL_008,
    TOOL_FAILURE_001, TOOL_FAILURE_002, TOOL_FAILURE_003, TOOL_FAILURE_004, TOOL_FAILURE_005, TOOL_FAILURE_006, TOOL_FAILURE_007, TOOL_FAILURE_008,
    CONTRADICTORY_001, CONTRADICTORY_002, CONTRADICTORY_003, CONTRADICTORY_004, CONTRADICTORY_005, CONTRADICTORY_006, CONTRADICTORY_007, CONTRADICTORY_008,
    INCOMPLETE_001, INCOMPLETE_002, INCOMPLETE_003, INCOMPLETE_004, INCOMPLETE_005, INCOMPLETE_006, INCOMPLETE_007, INCOMPLETE_008,
    ADVERSARIAL_001, ADVERSARIAL_002, ADVERSARIAL_003, ADVERSARIAL_004, ADVERSARIAL_005, ADVERSARIAL_006, ADVERSARIAL_007, ADVERSARIAL_008,
    REPLANNING_001, REPLANNING_002, REPLANNING_003, REPLANNING_004, REPLANNING_005, REPLANNING_006,
    AMBIGUOUS_001, AMBIGUOUS_002, AMBIGUOUS_003, AMBIGUOUS_004, AMBIGUOUS_005, AMBIGUOUS_006, AMBIGUOUS_007,
]

BY_ID = {c.id: c for c in DATASET}
BY_CATEGORY: dict[str, list[Case]] = {}
for _c in DATASET:
    BY_CATEGORY.setdefault(_c.category, []).append(_c)
