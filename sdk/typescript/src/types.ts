export interface AgentResponse {
  response: string;
  tool_calls: ToolCall[];
  session_id?: string;
  tokens_used: number;
  model: string;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
}

export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Memory {
  id: string;
  content: string;
  memory_type: string;
  created_at: string;
}

export interface Document {
  id: string;
  filename: string;
  chunk_count: number;
  created_at: string;
}

export interface SearchResult {
  chunk_id: string;
  content: string;
  score: number;
  document_id: string;
  metadata: Record<string, unknown>;
}

export interface UsageAnalytics {
  total_requests: number;
  by_endpoint: Array<{ endpoint: string; method: string; count: number; avg_ms: number; total_tokens: number }>;
  by_day: Array<{ day: string; count: number; tokens: number }>;
  by_model: Array<{ model: string; count: number; tokens: number }>;
  period_days: number;
}

export interface App {
  id: string;
  name: string;
  description: string;
  status: string;
  scopes: string[];
  created_at: string;
}

export interface APIKey {
  id: string;
  key?: string;
  name: string;
  scopes: string[];
  created_at: string;
}

export interface Plugin {
  id: string;
  name: string;
  display_name: string;
  description: string;
  version: string;
  status: string;
  installs_count: number;
}

export interface PluginInstall {
  id: string;
  plugin_id: string;
  status: string;
  config: Record<string, unknown>;
}

export interface Org {
  id: string;
  name: string;
  role?: string;
}

export interface StatusResponse {
  status: string;
  timestamp: number;
  services: Record<string, { status: string; latency_ms: number }>;
  version: string;
}

export interface ChangelogEntry {
  version: string;
  date: string;
  changes: string[];
}
