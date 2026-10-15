"""API response schemas shared by routes and exception handlers."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str = Field(examples=["invalid_request"])
    message: str = Field(examples=["The request could not be processed."])
    request_id: str


class HealthResponse(BaseModel):
    status: str
    request_id: str


class SessionResponse(BaseModel):
    subject: str
    permissions: list[str]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None


class SourceCitationResponse(BaseModel):
    document_id: str
    filename: str
    page: int | None = None


class ChatResponse(BaseModel):
    response: str
    citations: list[SourceCitationResponse] = Field(default_factory=list)
    request_id: str


class MCPToolDescriptor(BaseModel):
    name: str
    description: str
    parameters: dict[str, object]
    required_permission: str


class MCPToolsListResponse(BaseModel):
    tools: list[MCPToolDescriptor]


class MCPCallRequest(BaseModel):
    parameters: dict[str, object] = Field(default_factory=dict)


class MCPCallResponse(BaseModel):
    tool: str
    content: str
    citations: list[SourceCitationResponse] = Field(default_factory=list)
    request_id: str
    truncated: bool = False
