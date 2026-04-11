from __future__ import annotations

import asyncio
import time
from typing import Any, Optional, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph
from sqlalchemy import insert

from agents.matching_agent import MatchingAgent
from agents.normalization_agent import NormalizationAgent
from agents.parsing_agent import ParsingAgent
from api.models.resume import AgentTrace, JobDescription, MatchResult, NormalizedProfile, ParsedResume
from core.database import PipelineRun


logger = structlog.get_logger(__name__)


class PipelineState(TypedDict):
    raw_file: bytes
    file_type: str
    parsed_resume: Optional[ParsedResume]
    normalized_profile: Optional[NormalizedProfile]
    job_description: Optional[JobDescription]
    match_result: Optional[MatchResult]
    errors: list[str]
    agent_traces: list[AgentTrace]


class PipelineOrchestrator:
    def __init__(self, parsing_agent: ParsingAgent, normalization_agent: NormalizationAgent, matching_agent: MatchingAgent, session_factory=None):
        self.parsing_agent = parsing_agent
        self.normalization_agent = normalization_agent
        self.matching_agent = matching_agent
        self.session_factory = session_factory
        self.graph = self._build_graph()

    def _trace(self, state: PipelineState, agent: str, start: float, ok: bool, err: str = "") -> None:
        latency = int((time.perf_counter() - start) * 1000)
        trace = AgentTrace(agent=agent, success=ok, latency_ms=latency, error=err or None)
        state["agent_traces"].append(trace)
        logger.info("agent_run", agent=agent, success=ok, latency_ms=latency, error=err)

    async def _parse_node(self, state: PipelineState) -> PipelineState:
        start = time.perf_counter()
        try:
            parsed = await self.parsing_agent.parse(state["raw_file"], state["file_type"])
            state["parsed_resume"] = parsed
            self._trace(state, "ParsingAgent", start, True)
        except Exception as e:
            state["errors"].append(f"ParsingAgent: {e}")
            self._trace(state, "ParsingAgent", start, False, str(e))
        return state

    async def _normalization_node(self, state: PipelineState) -> PipelineState:
        start = time.perf_counter()
        try:
            parsed = state.get("parsed_resume")
            if parsed:
                profile = await self.normalization_agent.build_profile(parsed.candidate_id, parsed.skills, parsed.raw_text)
                state["normalized_profile"] = profile
            self._trace(state, "NormalizationAgent", start, True)
        except Exception as e:
            state["errors"].append(f"NormalizationAgent: {e}")
            self._trace(state, "NormalizationAgent", start, False, str(e))
        return state

    async def _matching_node(self, state: PipelineState) -> PipelineState:
        start = time.perf_counter()
        try:
            profile = state.get("normalized_profile")
            job = state.get("job_description")
            if profile and job:
                state["match_result"] = await self.matching_agent.match(profile, job)
            self._trace(state, "MatchingAgent", start, True)
        except Exception as e:
            state["errors"].append(f"MatchingAgent: {e}")
            self._trace(state, "MatchingAgent", start, False, str(e))
        return state

    def _build_graph(self):
        graph = StateGraph(PipelineState)
        graph.add_node("parse", self._parse_node)
        graph.add_node("normalize", self._normalization_node)
        graph.add_node("match", self._matching_node)

        graph.add_edge(START, "parse")
        graph.add_edge("parse", "normalize")
        graph.add_edge("normalize", "match")
        graph.add_edge("match", END)
        return graph.compile()

    async def run(self, raw_file: bytes, file_type: str, job_description: Optional[JobDescription] = None) -> PipelineState:
        initial: PipelineState = {
            "raw_file": raw_file,
            "file_type": file_type,
            "parsed_resume": None,
            "normalized_profile": None,
            "job_description": job_description,
            "match_result": None,
            "errors": [],
            "agent_traces": [],
        }
        final_state = await self.graph.ainvoke(initial)
        await self._store_pipeline_run(final_state)
        return final_state

    async def run_batch(self, payloads: list[tuple[bytes, str, Optional[JobDescription]]]) -> list[PipelineState]:
        sem = asyncio.Semaphore(10)

        async def _one(item):
            raw_file, file_type, job = item
            async with sem:
                return await self.run(raw_file, file_type, job)

        return await asyncio.gather(*[_one(p) for p in payloads], return_exceptions=False)

    async def _store_pipeline_run(self, state: PipelineState) -> None:
        if not self.session_factory:
            return
        parsed = state.get("parsed_resume")
        traces = {t.agent: t for t in state.get("agent_traces", [])}
        parsing_ms = traces.get("ParsingAgent").latency_ms if "ParsingAgent" in traces else 0
        normalization_ms = traces.get("NormalizationAgent").latency_ms if "NormalizationAgent" in traces else 0
        matching_ms = traces.get("MatchingAgent").latency_ms if "MatchingAgent" in traces else 0
        status = "failed" if state.get("errors") else "completed"
        try:
            async with self.session_factory() as session:
                await session.execute(
                    insert(PipelineRun).values(
                        candidate_id=parsed.candidate_id if parsed else "unknown",
                        status=status,
                        parsing_ms=parsing_ms,
                        normalization_ms=normalization_ms,
                        matching_ms=matching_ms,
                        error_log=" | ".join(state.get("errors", [])),
                    )
                )
                await session.commit()
        except Exception as e:
            logger.warning("pipeline_run_store_failed", error=str(e))
