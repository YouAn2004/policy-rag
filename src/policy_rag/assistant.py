"""The full question answering pipeline.

question -> input guard -> rewrite -> filtered retrieval -> answerability check -> grounded answer
         -> citation and number checks (one retry) -> support check -> result
"""

import re
import time
from dataclasses import asdict, dataclass, field

from . import config, guard, prompts
from .judge import find_clause
from .llm import parse_json
from .rewrite import rewrite_query
from .thresholds import threshold_hints
from .verify import problems, says_silent, verify_structure

ABSTAIN = re.compile(r"^\W*not[_ ]in[_ ]policy", re.I)


@dataclass
class Answer:
    status: str  # "answered", "flagged" (answered but a check failed) or "refused"
    text: str
    question: str
    role: str
    rewritten: str = ""
    citations: list = field(default_factory=list)
    verification: dict = field(default_factory=dict)
    retrieved: list = field(default_factory=list)
    refusal_reason: str = ""
    contact: str = ""
    timings: dict = field(default_factory=dict)
    checks: str = ""  # exact threshold comparisons computed by code and given to the model

    def to_dict(self):
        return asdict(self)


def contact_for(owner):
    for key, email in config.CONTACTS.items():
        if key.lower() in (owner or "").lower():
            return f"{key} at {email}"
    name, email = config.DEFAULT_CONTACT
    return f"{name} at {email}"


class PolicyAssistant:
    def __init__(self, retriever, llm, mode=config.DEFAULT_MODE, use_rewrite=config.USE_REWRITE):
        self.retriever = retriever
        self.llm = llm
        self.mode = mode
        self.use_rewrite = use_rewrite
        self._sections = {}
        for c in retriever.index.chunks:
            self._sections.setdefault((c.meta.doc_id, c.meta.version, c.section_no, c.section_title), []).append(c)
        self._by_id = {c.chunk_id: c for c in retriever.index.chunks}

    def build_context(self, hits):
        """Render the sections that contain the best hits. Returns (text, {lower label: chunk})."""
        seen, blocks, available = [], [], {}
        for h in hits:
            m = h.chunk.meta
            key = (m.doc_id, m.version, h.chunk.section_no, h.chunk.section_title)
            if key in seen:
                continue
            seen.append(key)
            if len(seen) > config.MAX_SECTIONS:
                break
            lines = [f"== {m.doc_id} {m.title}, version {m.version}, effective {m.effective_date}, "
                     f"section {h.chunk.section_title} =="]
            for c in self._sections[key]:
                available[c.cite_key.lower()] = c
                lines.append(f"[{c.cite_key}] {c.text}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks), available

    def _refuse(self, question, role, reason, hits, rewritten, timings, t0=None):
        if t0 is not None:
            timings["total"] = time.perf_counter() - t0
        owner = hits[0].chunk.meta.owner if hits else ""
        who = contact_for(owner)
        text = (f"I could not find this in the company policies available to your role. "
                f"Please contact {who}.")
        return Answer("refused", text, question, role, rewritten, [], {}, [h.chunk.citation for h in hits],
                      refusal_reason=reason, contact=who, timings=timings)

    def _blocked(self, question, role, kind, started):
        reason = f"the message reads as an instruction to the assistant ({kind})"
        return Answer("refused", guard.MESSAGE, question, role, refusal_reason=reason,
                      timings={"total": time.perf_counter() - started})

    def ask(self, question, role="employee", as_of=None, judge_only=False, progress=None):
        """progress, when given, is called with each stage name as it starts (rewrite, search, judge, answer, verify)."""
        emit = progress or (lambda stage: None)
        t0 = time.perf_counter()
        if config.INPUT_GUARD and (kind := guard.check(question)):
            return self._blocked(question, role, kind, t0)
        timings = {}
        queries, rewritten = [question], ""
        if self.use_rewrite:
            emit("rewrite")
            rewritten = rewrite_query(self.llm, question)
            if rewritten.strip().lower() != question.strip().lower():
                queries.append(rewritten)
        timings["rewrite"] = time.perf_counter() - t0

        emit("search")
        t = time.perf_counter()
        if len(queries) > 1:
            hits = self.retriever.search_multi(queries, role, config.CONTEXT_HITS, self.mode, as_of)
        else:
            hits = self.retriever.search(question, role, config.CONTEXT_HITS, self.mode, as_of)
        timings["retrieve"] = time.perf_counter() - t
        if not hits:
            return self._refuse(question, role, "nothing retrievable for this role", hits, rewritten, timings, t0)

        context, available = self.build_context(hits)
        checks = (threshold_hints(question, [(c.cite_key, c.text) for c in available.values()])
                  if config.THRESHOLD_HINTS else "")

        emit("judge")
        t = time.perf_counter()
        verdict = find_clause(self.llm, question, context, available, checks)
        timings["judge"] = time.perf_counter() - t
        if not verdict.answerable:
            return self._refuse(question, role, verdict.reason, hits, rewritten, timings, t0)
        if judge_only:  # used by the fast refusal evaluation
            timings["total"] = time.perf_counter() - t0
            return Answer("answered", "(judge only)", question, role, rewritten, [], {}, [h.chunk.citation for h in hits],
                          refusal_reason=verdict.reason, timings=timings, checks=checks)

        emit("answer")
        t = time.perf_counter()
        feedback, text, v, support, cited = "", "", {}, None, []
        for attempt in range(config.MAX_RETRIES + 1):
            last = attempt == config.MAX_RETRIES
            text = self.llm.complete(prompts.answer_user(question, context, feedback, checks), system=prompts.ANSWER_SYSTEM,
                                     purpose="answer")
            if ABSTAIN.match(text) or says_silent(text):  # no clause covers the question
                timings["answer"] = time.perf_counter() - t
                return self._refuse(question, role, "the clauses shown do not contain a rule for this question",
                                    hits, rewritten, timings, t0)
            emit("verify")
            v = verify_structure(text, set(available), context, question)
            feedback = problems(v)
            cited = [available[c.lower()] for c in v["cited"] if c.lower() in available]
            if feedback and not last:
                continue
            support = None
            if cited and not v["invalid_citations"]:
                cited_ctx = "\n".join(f"[{c.cite_key}] {c.text}" for c in cited)
                sv = parse_json(self.llm.complete(prompts.support_user(text, cited_ctx, question, checks),
                                                  system=prompts.SUPPORT_SYSTEM, purpose="support", json_mode=True))
                support = {"supported": sv.get("supported") is True, "problems": sv.get("problems", [])}
            if support and not support["supported"] and not last:
                feedback = ("A reviewer found statements the clauses do not support: "
                            + "; ".join(str(x) for x in support["problems"]) + ". Rewrite the answer so that every "
                            "statement follows from the clauses and the employee's own facts.")
                continue
            break
        timings["answer"] = time.perf_counter() - t
        v["llm_support"] = support

        clean = not (v["uncited"] or v["invalid_citations"] or v["unsupported_numbers"]
                     or (support is not None and not support["supported"]))
        citations = [dict(label=c.cite_key, chunk_id=c.chunk_id, doc_id=c.meta.doc_id, title=c.meta.title,
                          version=c.meta.version, effective_date=c.meta.effective_date, section=c.section_title,
                          source_file=c.meta.source_file, page=c.page, text=c.text) for c in cited]
        timings["total"] = time.perf_counter() - t0
        return Answer("answered" if clean else "flagged", text, question, role, rewritten, citations, v,
                      [h.chunk.citation for h in hits], timings=timings, checks=checks)
