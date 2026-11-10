"""Analyst Chat Agent: answers follow-up questions about a finished run (retrieval-augmented).

It retrieves the most relevant findings and recommendations (TF-IDF similarity plus question-intent
boosts, e.g. "problem" favours weaknesses and pain points) and answers from them only - through the LLM when one is configured, or by quoting the evidence directly
when running offline. Every answer cites its sources.
"""
from __future__ import annotations

import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..core.agent import GROUNDING_RULES
from ..core.llm import LLMClient
from ..core.store import RunData


INTENTS = [  # question pattern -> which evidence answers it
    (r"problem|issue|weak|complain|pain|wrong|risk|worry|bad", lambda d: d["swot"] in ("W", "T") or "pain point" in d["tags"]),
    (r"compet|rival|threat|enemy", lambda d: 1.0 if "threat" in d["tags"] else 0.5 if "competitor" in d["tags"] else 0.0),
    (r"price|pricing|elastic|expensive|cheap|sensitiv", lambda d: d["area"] == "pricing" or "price" in d["tags"]),
    (r"launch|concept|moisturi[sz]er|new product", lambda d: "concept" in d["tags"]),
    (r"segment|target|persona|audience|who should", lambda d: d["area"] == "segmentation"),
    (r"forecast|outlook|next year|predict|demand|future", lambda d: d["area"] == "forecast"),
    (r"channel|tiktok|shopee|online|e-?commerce|offline", lambda d: "channel" in d["tags"]),
    (r"trend|topic|social|conversation|buzz", lambda d: "trend" in d["tags"] or "social" in d["tags"]),
    (r"market size|how big|cagr|market growth", lambda d: "market size" in d["tags"]),
    (r"strength|good at|love|advantage", lambda d: d["swot"] == "S"),
    (r"recommend|should we|what to do|action|plan|priorit", lambda d: d["kind"] == "recommendation"),
]


class AnalystChatAgent:
    name = "Analyst Chat Agent"
    role = "Research analyst on call. Answers questions about the study, citing the evidence."

    def __init__(self, run: RunData, llm: LLMClient | None = None):
        self.run = run
        self.llm = llm or LLMClient()
        self.docs = []
        for f in run.findings:
            self.docs.append(dict(id=f.id, kind="finding", title=f.title, text=f.statement, source=f.agent, area=f.area,
                                  tags=f.tags, swot=f.swot, priority=f.priority))
        for r in run.json("strategy.recommendations", []) or []:
            self.docs.append(dict(id=r["id"], kind="recommendation", title=r["title"],
                                  text=f"{r['title']}. {r['action']} Why: {r['rationale']} KPI: {r['kpi']}",
                                  source="Strategy Agent", area="strategy", tags=[], swot=None, priority=r["priority"]))
        corpus = [f"{d['title']} {d['text']}" for d in self.docs] or [""]
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        self.matrix = self.vec.fit_transform(corpus)

    def retrieve(self, question: str, k: int = 5) -> list[dict]:
        if not self.docs:
            return []
        sims = cosine_similarity(self.vec.transform([question]), self.matrix).ravel()
        q = question.lower()
        boost = np.zeros(len(self.docs))
        for pattern, wants in INTENTS:
            if re.search(pattern, q):
                boost += 0.35 * np.array([float(wants(d)) for d in self.docs])
        prio = np.array([d["priority"] or 0 for d in self.docs]) / 5
        score = sims + boost + 0.05 * prio * (boost > 0)
        order = np.argsort(-score)[:k]
        return [dict(**self.docs[i], score=round(float(score[i]), 3)) for i in order if score[i] > 0.05]

    def answer(self, question: str, history: list[dict] | None = None) -> dict:
        hits = self.retrieve(question)
        if not hits:
            return dict(answer="I could not find evidence about that in this study. Try asking about the market, "
                               "competitors, consumer sentiment, segments, pricing, the forecast or the recommendations.",
                        sources=[], mode="retrieval")
        if self.llm.available:
            facts = [{k: h[k] for k in ("id", "kind", "title", "text")} for h in hits]
            convo = "\n".join(f"{m['role']}: {m['content']}" for m in (history or [])[-6:])
            prompt = (f"Conversation so far:\n{convo}\n\nQuestion: {question}\n\nEVIDENCE (JSON): {facts}\n\n"
                      "Answer in 2-5 sentences using only the evidence and cite IDs in brackets.")
            text = self.llm.complete(f"You are the {self.name}. {self.role}\n{GROUNDING_RULES}", prompt,
                                     max_tokens=500, agent=self.name)
            if text:
                return dict(answer=text, sources=hits, mode=f"LLM ({self.llm.describe()})")
        lines = [f"- **{h['title']}** - {h['text']} `[{h['id']}]`" for h in hits[:3]]
        return dict(answer="Here is what the evidence says:\n\n" + "\n".join(lines), sources=hits, mode="retrieval (offline)")
