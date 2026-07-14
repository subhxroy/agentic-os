# Volume 6: Developer & Customer Platforms

## Chapter 17: Developer Platform

### 17.1 Why a Developer Platform

A developer platform transforms AgentOS from a product into a platform. It enables third-party developers to:
- Build custom agents for specific domains
- Create and distribute tools/plugins
- Integrate AgentOS into their own applications
- Automate workflows via API

**Platform flywheel:**
```
More developers → More agents/tools → More value → More users → More developers
```

```mermaid
graph TB
    subgraph "Developer Tools"
        CLI[CLI Tool]
        JS_SDK[JS/TS SDK]
        PY_SDK[Python SDK]
        GO_SDK[Go SDK]
    end

    subgraph "Agent SDK & Plugin SDK"
        AGENT_SDK[Agent SDK<br/>defineAgent()]
        PLUGIN_SDK[Plugin SDK<br/>definePlugin()]
        MARKET[Plugin Marketplace]
    end

    subgraph "API Layer"
        REST[REST API<br/>v1/v2 endpoints]
        GRAPHQL[GraphQL API]
        SSE[SSE Streaming]
        WEBHOOKS[Webhooks]
    end

    subgraph "Core Platform"
        AUTH[Auth Service]
        ORCH[Agent Orchestrator]
        TOOL_REG[Tool Registry]
        MEM[Memory Manager]
        KNOW[Knowledge Manager]
    end

    subgraph "Third-Party Developers"
        DEV1[Developer Apps]
        DEV2[Integration Partners]
        DEV3[Enterprise Teams]
    end

    DEV1 --> REST
    DEV1 --> GRAPHQL
    DEV2 --> WEBHOOKS
    DEV3 --> CLI

    CLI --> AUTH
    JS_SDK --> REST
    PY_SDK --> REST
    GO_SDK --> REST

    AGENT_SDK --> ORCH
    AGENT_SDK --> TOOL_REG
    PLUGIN_SDK --> TOOL_REG
    MARKET --> PLUGIN_SDK

    REST --> AUTH
    REST --> ORCH
    REST --> MEM
    REST --> KNOW
    GRAPHQL --> ORCH
    SSE --> ORCH
    WEBHOOKS --> ORCH
```

### 17.2 REST API Design

**API versioning:**
```
https://api.agentos.com/v1/sessions
https://api.agentos.com/v2/sessions  (breaking changes)

Version strategy:
  - URL-versioned (v1, v2)
  - Deprecation notice 6 months in advance
  - Sunset header with migration guide URL
```

**Core API endpoints:**
```
# Agent Sessions
POST   /v1/agents/sessions                          # Create session
GET    /v1/agents/sessions                           # List sessions
GET    /v1/agents/sessions/:id                       # Get session
POST   /v1/agents/sessions/:id/message               # Send message
POST   /v1/agents/sessions/:id/goal                  # Set goal
POST   /v1/agents/sessions/:id/terminate             # Terminate
GET    /v1/agents/sessions/:id/stream                # SSE stream

# Memory
GET    /v1/memories                                  # Search memories
POST   /v1/memories                                  # Create memory
GET    /v1/memories/:id                              # Get memory
PUT    /v1/memories/:id                              # Update memory
DELETE /v1/memories/:id                              # Delete memory

# Knowledge
POST   /v1/knowledge/documents                       # Upload document
GET    /v1/knowledge/documents                       # List documents
DELETE /v1/knowledge/documents/:id                   # Delete document
POST   /v1/knowledge/search                          # Search knowledge
POST   /v1/knowledge/entities                        # Create entity
GET    /v1/knowledge/graph/query                     # Graph traversal

# Tools
GET    /v1/tools                                     # List available tools
GET    /v1/tools/:id                                 # Get tool details
POST   /v1/tools/:id/execute                         # Execute tool directly
POST   /v1/tools/custom                              # Register custom tool

# Admin
GET    /v1/org                                        # Get org details
PUT    /v1/org                                        # Update org
GET    /v1/org/members                                # List members
GET    /v1/org/usage                                  # Get usage stats
GET    /v1/org/billing                                # Get billing info
```

**API authentication:**
```
Authorization: Bearer sk_live_xxxxxxxxxxxxx
X-API-Version: 2026-07-01  (optional date-based versioning)
```

**Pagination:**
```
GET /v1/sessions?cursor=abc123&limit=50

Response:
{
  "data": [...],
  "pagination": {
    "next_cursor": "def456",
    "has_more": true
  }
}
```

**Rate limiting:**
```
Response headers:
  X-RateLimit-Limit: 1000
  X-RateLimit-Remaining: 987
  X-RateLimit-Reset: 1700000000
  Retry-After: 30 (when limited)
```

---

### 17.3 GraphQL API

**Why GraphQL in addition to REST:**
- Real-time subscriptions (agent streaming)
- Clients fetch exactly what they need
- Reduces over-fetching for dashboard/complex queries

**Schema:**
```graphql
type AgentSession {
  id: ID!
  status: SessionStatus!
  agentType: String!
  messages: [Message!]!
  createdAt: DateTime!
  lastActiveAt: DateTime!
  tokenUsage: TokenUsage!
}

type Message {
  id: ID!
  role: MessageRole!
  content: String!
  toolCalls: [ToolCall!]
  createdAt: DateTime!
}

type Subscription {
  agentStream(sessionId: ID!): MessageStreamPayload!
}

type Query {
  sessions(first: Int, after: String): SessionConnection!
  session(id: ID!): AgentSession
  memories(query: String!, limit: Int): [Memory!]!
  knowledgeSearch(query: String!, limit: Int): [KnowledgeResult!]!
}

type Mutation {
  createSession(input: CreateSessionInput!): AgentSession!
  sendMessage(sessionId: ID!, content: String!): Message!
  setGoal(sessionId: ID!, goal: String!): AgentSession!
}
```

---

### 17.4 SDK Design

**SDK principles:**
- Type-safe (TypeScript/Python)
- Zero config for common cases
- Same API as REST but with language convenience
- Auto-pagination
- Error types for every failure mode
- Streaming support natively

**TypeScript SDK example:**
```typescript
import AgentOS from '@agentos/sdk';

const client = new AgentOS({
    apiKey: 'sk_live_xxx',
});

// Basic usage
const session = await client.agents.create({
    type: 'research_agent',
    goal: 'Analyze competitor pricing'
});

// Streaming
const stream = session.stream();
for await (const chunk of stream) {
    if (chunk.type === 'token') {
        process.stdout.write(chunk.token);
    }
    if (chunk.type === 'tool_call') {
        console.log(`Calling tool: ${chunk.tool}`);
    }
}

// Memory
const memories = await client.memories.search({
    query: 'competitor pricing analysis',
    limit: 10
});

// Knowledge
await client.knowledge.upload({
    file: './competitor-report.pdf',
    onProgress: (pct) => console.log(`${pct}% uploaded`)
});
```

**Python SDK example:**
```python
from agentos import AgentOS

client = AgentOS(api_key="sk_live_xxx")

# Create agent
session = client.agents.create(
    type="research_agent",
    goal="Analyze Q2 revenue"
)

# Stream response
for event in session.stream():
    if event.type == "token":
        print(event.token, end="")
    elif event.type == "tool_call":
        print(f"\n[Tool: {event.tool}]")

# Knowledge search
results = client.knowledge.search(
    query="quarterly revenue trends",
    limit=5
)
```

---

### 17.5 Agent SDK

**Purpose:** Allow developers to create custom agent types with specific behaviors, tools, and prompts.

**Agent definition:**
```typescript
// custom_agent.ts
import { defineAgent } from '@agentos/sdk';

export const SecurityAuditAgent = defineAgent({
    name: 'security-audit-agent',
    version: '1.0.0',
    description: 'Analyze code for security vulnerabilities',
    
    system: `You are a security audit agent. Analyze code for:
- SQL injection vulnerabilities
- XSS vulnerabilities
- Insecure authentication
- Hardcoded secrets
- Dependency vulnerabilities

Output format: JSON with findings, severity, and remediation steps.`,
    
    tools: [
        'code_scanner',
        'dependency_checker',
        'secret_detector',
    ],
    
    model: {
        primary: 'claude-sonnet-4',
        fallback_quality: 'claude-haiku-4',
        max_tokens: 8000,
    },
    
    hooks: {
        onToolCall: async (tool, params) => {
            // Custom logging or modification
            console.log(`Security agent calling: ${tool}`);
            return params;
        },
        onResponse: async (response) => {
            // Post-process results
            response.findings.sort((a, b) => b.severity - a.severity);
            return response;
        }
    }
});
```

**Agent deployment:**
```
# Deploy to AgentOS
agentos deploy ./custom_agent.ts --name security-audit

# Use via API
POST /v1/agents/sessions
{
    "type": "security-audit-agent",
    "goal": "Audit ./src for vulnerabilities"
}
```

```mermaid
sequenceDiagram
    participant DEV as Developer
    participant CLI as CLI Tool
    participant REG as Agent Registry
    participant API as API Gateway
    participant SESS as Session Service
    participant AGENT as Agent Worker
    participant USER as End User

    DEV->>DEV: Write agent with defineAgent()
    DEV->>CLI: agentos deploy agent.ts
    CLI->>REG: Register agent type + schema
    REG-->>CLI: agent_id: agent_abc123
    CLI-->>DEV: Deployed: security-audit

    Note over DEV,USER: Later...

    USER->>API: POST /v1/agents/sessions
    Note over USER,API: { type: "security-audit-agent", goal: "Audit ./src" }
    API->>REG: Lookup agent type
    REG-->>API: agent definition + tools
    API->>SESS: Create session
    SESS->>AGENT: Assign session to worker
    AGENT->>AGENT: Load agent code
    AGENT->>AGENT: Execute goal loop
    AGENT-->>API: Stream response
    API-->>USER: SSE events
```

### 17.6 Plugin SDK

**Purpose:** Allow developers to create custom tools that agents can use.

**Plugin definition:**
```typescript
// pagerduty-plugin.ts
import { defineTool } from '@agentos/sdk';

export const PagerDutyTool = defineTool({
    name: 'pagerduty',
    version: '1.0.0',
    description: 'Manage PagerDuty incidents and on-call schedules',
    
    auth: {
        type: 'oauth2',
        provider: 'pagerduty',
        scopes: ['incidents.read', 'incidents.write'],
    },
    
    functions: [
        {
            name: 'list_incidents',
            description: 'List active PagerDuty incidents',
            parameters: {
                type: 'object',
                properties: {
                    status: { 
                        type: 'string', 
                        enum: ['triggered', 'acknowledged', 'resolved']
                    },
                    limit: { type: 'integer', default: 25 }
                }
            },
            handler: async (params, auth) => {
                return pagerdutyApi.listIncidents(auth.token, params);
            }
        },
        {
            name: 'acknowledge_incident',
            description: 'Acknowledge a PagerDuty incident',
            parameters: {
                type: 'object',
                properties: {
                    incident_id: { type: 'string' }
                },
                required: ['incident_id']
            },
            handler: async (params, auth) => {
                return pagerdutyApi.acknowledge(auth.token, params.incident_id);
            }
        }
    ],
    
    rate_limits: {
        per_minute: 30,
        per_hour: 500
    },
    
    webhooks: {
        // Receive PagerDuty webhooks
        events: ['incident.triggered', 'incident.acknowledged'],
        handler: async (event) => {
            // Trigger agent action on incident
            await agentos.triggerAgent('incident-responder', {
                incident: event.data
            });
        }
    }
});
```

---

### 17.7 Plugin Marketplace

**Marketplace architecture:**
```
┌─────────────────────────────────────────────┐
│  Plugin Marketplace                          │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Browse   │  │ Search   │  │ Install  │   │
│  └──────────┘  └──────────┘  └──────────┘   │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Version  │  │ Rating/  │  │ Security │   │
│  │ Manager  │  │ Reviews  │  │ Scan     │   │
│  └──────────┘  └──────────┘  └──────────┘   │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Usage    │  │ Revenue  │  │ Support  │   │
│  │ Metrics  │  │ Share    │  │ Tickets  │   │
│  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────┘
```

**Plugin submission workflow:**
```
1. Developer creates plugin (SDK)
2. Submits to marketplace
3. Automated security scan:
   - Static analysis
   - Dependency audit
   - Permission review
4. Automated sandbox test:
   - Run in isolated environment
   - Verify no data leakage
   - Verify rate limit compliance
5. Manual review (if high-risk):
   - Human reviews code
   - Check documentation
6. Approval / Rejection
7. Published to marketplace
```

---

### 17.8 CLI Tool

**Purpose:** Developer-friendly CLI for managing agents, tools, and deployment.

**Commands:**
```
agentos init              # Initialize project
agentos agent create      # Create new agent
agentos agent deploy      # Deploy agent
agentos agent test        # Test agent locally
agentos tool create       # Create new tool
agentos tool publish      # Publish to marketplace
agentos session list      # List active sessions
agentos session inspect   # Inspect session details
agentos logs              # View agent logs
agentos config            # Manage configuration
agentos whoami            # Show current user
```

---

## Chapter 18: Customer Platform

### 18.1 Dashboard Architecture

```mermaid
graph TB
    subgraph "Frontend Next.js"
        UI[Dashboard UI]
        RQ[React Query Server State]
        ZUS[Zustand Client State]
        WS[WebSocket Client]
        SSE[SSE Client]
        CHART[Recharts / D3 Charts]
    end

    subgraph "API Layer"
        REST[REST API]
        WS_GW[WebSocket Gateway]
        EVT[SSE Event Stream]
    end

    subgraph "Dashboard Sections"
        OVER[Overview Active Sessions Usage Stats]
        AGENTS[Agents Library Config]
        SESS[Session Inspector Messages Tool Calls]
        MEM[Memory Browser Search Preferences]
        KNOW[Knowledge Upload Search Graphviz]
        TOOLS[Tool Market Installed OAuth]
        SETT[Settings Profile Org Team Billing]
    end

    subgraph "Backend Services"
        AUTH[Auth Service]
        SVC[Orchestrator API]
        ANAL[Analytics Service]
        BILL[Billing Service]
    end

    UI --> OVER & AGENTS & SESS & MEM & KNOW & TOOLS & SETT
    OVER --> CHART & RQ
    UI --> WS & SSE
    RQ --> REST
    ZUS --> REST
    WS --> WS_GW
    SSE --> EVT
    REST --> AUTH & SVC & ANAL & BILL
    WS_GW --> SVC
    EVT --> SVC
```

**Dashboard tech stack:**
```
Frontend: Next.js + React + Tailwind + shadcn/ui
State: React Query (server state) + Zustand (client state)
Real-time: WebSocket + SSE
Analytics: Recharts + D3
```

**Dashboard sections:**

```
1. Overview
   - Active agents/sessions
   - Usage stats (today, week, month)
   - Recent activity feed
   - Quick actions

2. Agents
   - Agent library (pre-built)
   - Custom agents
   - Agent configuration
   - Agent performance metrics

3. Sessions
   - Active sessions
   - Session history
   - Session inspector (message log, tool calls, tokens)

4. Memory
   - Memory browser
   - Memory search
   - Preference editor
   - Memory settings (TTL, budget)

5. Knowledge
   - Document upload
   - Document browser
   - Knowledge search
   - Knowledge graph visualizer

6. Tools
   - Tool marketplace
   - Installed tools
   - Tool configuration
   - OAuth management

7. Settings
   - Profile
   - Organization
   - Team members
   - API keys
   - Billing
   - Preferences
```

---

### 18.2 Multi-Organization Management

**Org hierarchy:**
```
Organization
├── Owner (1)
├── Admins (unlimited)
├── Members (unlimited)
├── Projects
│   ├── Project A
│   │   ├── Agents
│   │   ├── Knowledge bases
│   │   └── Team members assigned
│   └── Project B
├── Billing
│   ├── Plan
│   ├── Payment method
│   └── Invoice history
└── Settings
    ├── SSO configuration
    ├── Security policies
    ├── Compliance settings
    └── Audit log viewer
```

**Invitation flow:**
```
Admin → Invite user (email)
  → User receives email with magic link
  → User creates account or logs in
  → User joins organization
  → Admin assigns role
```

---

### 18.3 Billing and Subscriptions

**Pricing model:**
```
Free:
  - 1 agent session at a time
  - 100K tokens/month
  - 10MB knowledge storage
  - 3 tools
  - Community support

Pro ($29/month):
  - 5 concurrent sessions
  - 5M tokens/month
  - 1GB knowledge storage
  - All tools
  - Email support

Team ($99/month per 5 seats):
  - 20 concurrent sessions
  - 25M tokens/month
  - 10GB knowledge storage
  - Custom tools
  - Priority support
  - Team collaboration

Enterprise (Custom):
  - Unlimited sessions
  - Custom token allocation
  - Unlimited storage
  - SSO, audit logs, compliance
  - SLA, dedicated support
  - Self-hosted option
```

**Usage-based billing:**
```
Tracked metrics:
  - Tokens consumed (input + output)
  - Storage used (memory + knowledge)
  - API calls
  - Active agent hours

Billing cycle:
  - Base subscription: charged monthly
  - Overages: billed at end of month
  - Alerts: at 80%, 90%, 100% of plan limit
  - Hard cap: option to enforce or allow overage
```

**Payment provider:**
```
Stripe for payment processing:
  - Customers
  - Subscriptions
  - Invoices
  - Payment methods
  - Webhooks (payment_succeeded, invoice.paid, etc.)
```

---

### 18.4 Usage Tracking

**Usage metrics collected:**
```
Per user:
  - Sessions created
  - Messages sent
  - Tokens consumed (by model)
  - Tool calls executed
  - Memory size
  - Storage used
  - API calls
  - Active time

Per org:
  - Total users
  - Total sessions
  - Sum of all per-user metrics
  - Monthly trend

Per agent:
  - Session count
  - Task success rate
  - Average tokens per task
  - Average execution time
  - Tool usage frequency
```

**Usage dashboard queries:**
```sql
-- Daily token usage trend
SELECT 
    DATE(created_at) as day,
    SUM(input_tokens) as total_input,
    SUM(output_tokens) as total_output,
    SUM(input_tokens + output_tokens) as total
FROM token_usage
WHERE org_id = $1
  AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY day;

-- Agent performance
SELECT 
    agent_type,
    COUNT(*) as sessions,
    AVG(success) as success_rate,
    AVG(execution_time_ms) as avg_time,
    SUM(tokens_used) as total_tokens
FROM agent_sessions
WHERE org_id = $1
GROUP BY agent_type;
```

---

### 18.5 Collaboration

**Collaboration features:**
```
Shared agents:
  - Agent created by one user, usable by team
  - Role-based access: viewer, editor, admin
  - Activity log per agent

Shared knowledge bases:
  - Team knowledge sources
  - Permissioned access
  - Change history

Shared sessions:
  - View teammate's agent session
  - Comment on agent responses
  - Fork session (continue where teammate left off)

Workspace:
  - Shared agent library
  - Common tools
  - Team-wide settings
  - Shared memory (org-level knowledge)
```

---

### 18.6 Version History

**Agent versioning:**
```
- System prompt changes tracked
- Tool configuration changes tracked  
- Model selection changes tracked
- Rollback to previous version
- Compare versions (diff view)
- Audit: who changed what, when
```

**Memory versioning:**
```
- Snapshot memory at session boundaries
- Rollback memory to previous state
- View memory change history
- Audit memory updates per agent
```

---

**Continue to Volume 7: Observability, Deployment & Implementation Roadmap**
