"""Typed data classes for AgentOS SDK responses."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class AgentResponse:
    response: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    session_id: Optional[str] = None
    tokens_used: int = 0
    model: str = ""


@dataclass
class Session:
    id: str
    title: str
    created_at: str
    updated_at: str = ""


@dataclass
class Memory:
    id: str
    content: str
    memory_type: str = "long_term"
    created_at: str = ""


@dataclass
class Document:
    id: str
    filename: str
    chunk_count: int = 0
    created_at: str = ""


@dataclass
class SearchResult:
    chunk_id: str
    content: str
    score: float = 0.0
    document_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageAnalytics:
    total_requests: int = 0
    by_endpoint: List[Dict] = field(default_factory=list)
    by_day: List[Dict] = field(default_factory=list)
    by_model: List[Dict] = field(default_factory=list)
    period_days: int = 30


@dataclass
class App:
    id: str
    name: str
    description: str = ""
    status: str = "active"
    scopes: List[str] = field(default_factory=list)
    created_at: str = ""


@dataclass
class APIKey:
    id: str
    key: str = ""
    name: str = ""
    scopes: List[str] = field(default_factory=list)
    created_at: str = ""


@dataclass
class Plugin:
    id: str
    name: str
    display_name: str = ""
    description: str = ""
    version: str = "1.0.0"
    status: str = "draft"
    installs_count: int = 0
