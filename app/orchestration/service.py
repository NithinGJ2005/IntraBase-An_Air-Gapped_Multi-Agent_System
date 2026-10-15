"""High-level Intranet Assistant service orchestrating chat flows."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from app.audit import AuditSink, new_event
from app.auth.service import Identity
from app.config import Settings
from app.documents.models import SourceCitation
from app.llm.service import ChatMessage, LocalLLMClient
from app.orchestration.graph import (
    AssistantState,
    _format_system_prompt,
    build_orchestration_graph,
)
from app.orchestration.mcp import MCPToolRegistry

logger = logging.getLogger("app.orchestration")


@dataclass(frozen=True)
class ChatResult:
    response: str
    citations: tuple[SourceCitation, ...]


class IntranetAssistantService:
    """Service orchestrating employee inquiries using LangGraph and approved MCP tools."""

    def __init__(
        self,
        settings: Settings,
        llm_client: LocalLLMClient,
        tool_registry: MCPToolRegistry,
        audit_sink: AuditSink,
    ) -> None:
        self._settings = settings
        self._llm_client = llm_client
        self._tool_registry = tool_registry
        self._audit_sink = audit_sink
        self._system_prompt = _format_system_prompt(tool_registry)
        self._max_iterations = settings.orchestration_max_iterations
        self._graph = build_orchestration_graph(
            llm_client=self._llm_client,
            tool_registry=self._tool_registry,
            max_iterations=self._max_iterations,
        )

    def ask(
        self,
        message: str,
        identity: Identity,
        request_id: str,
        history: Sequence[ChatMessage] | None = None,
    ) -> ChatResult:
        """Process a user query through the LangGraph bounded orchestration flow."""
        # Check permission for chat
        if "chat:use" not in identity.permissions:
            self._audit_sink.record(
                new_event("assistant_chat", "denied", request_id, identity.subject, "chat")
            )
            raise PermissionError("chat:use permission required")

        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=self._system_prompt)
        ]

        if history:
            messages.extend(history)

        messages.append(ChatMessage(role="user", content=message))

        initial_state: AssistantState = {
            "query": message,
            "messages": messages,
            "identity": identity,
            "request_id": request_id,
            "citations": [],
            "step_count": 0,
            "max_iterations": self._max_iterations,
            "pending_tool_name": None,
            "pending_tool_args": None,
            "final_response": None,
            "error": None,
        }

        result_state = self._graph.invoke(initial_state)

        final_response = result_state.get("final_response") or "I could not produce a response."
        citations = tuple(result_state.get("citations", []))

        self._audit_sink.record(
            new_event("assistant_chat", "allowed", request_id, identity.subject, "chat")
        )

        return ChatResult(response=final_response, citations=citations)
