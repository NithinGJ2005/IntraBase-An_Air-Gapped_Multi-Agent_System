export interface SourceCitation {
  document_id: string;
  filename: string;
  page?: number | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  citations?: SourceCitation[];
  timestamp: string;
}

export interface ChatResponse {
  response: string;
  citations: SourceCitation[];
  request_id: string;
}

export interface SessionResponse {
  subject: string;
  permissions: string[];
}

export interface MCPToolDescriptor {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  required_permission: string;
}
