# Volume 15: Edge, Offline & Hybrid Deployment

## Chapter 33: Edge Deployment Architecture

### 33.1 Why Edge for AgentOS

**Latency-driven use cases:**
- Voice agents: Need < 500ms response for natural conversation
- Code completion on IDE: Need < 200ms for inline suggestions
- Real-time translation: Need < 1s for conversational flow
- IoT agents: Local processing when internet unreliable

**Compliance-driven use cases:**
- Healthcare data cannot leave hospital network
- Financial data must stay in country
- Defense/classified environments
- On-premises enterprise deployment

---

### 33.2 Edge Agent Architecture

```mermaid
graph TB
    subgraph "Edge Node (user device / local server)"
        LOCAL_LLM[Local LLM (Llama 4 8B)]
        LOCAL_VDB[(Local Vector DB)]
        LOCAL_MEM[(Local Memory)]
        LOCAL_AGENT[Edge Agent Runtime]
        LOCAL_CACHE[(Response Cache)]
        
        GUARD[Edge Guardrails]
        FILTER[Content Filter]
    end

    subgraph "Cloud (agentos.com)"
        CLOUD_LLM[Cloud LLM (Claude Opus)]
        CLOUD_VDB[Cloud Vector DB]
        CLOUD_MEM[Cloud Memory]
        CLOUD_AGENT[Cloud Agent]
        MGMT[Management Plane]
    end

    subgraph "Sync Layer"
        SYNC[Sync Engine]
        QUEUE[Offline Queue]
        MERGE[Conflict Resolver]
    end

    LOCAL_AGENT --> LOCAL_LLM
    LOCAL_AGENT --> LOCAL_VDB
    LOCAL_AGENT --> LOCAL_MEM
    LOCAL_AGENT --> GUARD
    GUARD --> FILTER

    LOCAL_AGENT --> SYNC
    SYNC --> CLOUD_AGENT
    SYNC --> QUEUE
    QUEUE --> SYNC
    SYNC --> MERGE

    CLOUD_AGENT --> CLOUD_LLM
    CLOUD_AGENT --> CLOUD_VDB
    CLOUD_AGENT --> CLOUD_MEM

    MGMT --> SYNC
    MGMT --> LOCAL_AGENT
```

---

### 33.3 Offline-First Design

**Agent state machine for connectivity:**
```
ONLINE → Full cloud capabilities
  ↓ (connection lost)
DEGRADED → Local LLM, cached knowledge, limited tools
  ↓ (connection restored)
SYNCING → Upload offline actions, reconcile memories
  ↓ (sync complete)
ONLINE → Full capabilities restored
```

**Offline capabilities:**
```
Available offline:
  - Simple Q&A (local Llama 4 8B)
  - Previously cached knowledge search
  - Local memory retrieval
  - Cached tool responses
  - Logging actions for later sync

Unavailable offline:
  - Complex reasoning (requires cloud LLM)
  - External tool calls (API unavailable)
  - New knowledge ingestion
  - Multi-agent coordination
  - Real-time collaboration
```

**Offline queue:**
```typescript
class OfflineQueue {
    private queue: QueuedAction[] = [];
    private storage: LocalStorage | IndexedDB;
    
    async enqueue(action: QueuedAction): Promise<void> {
        action.timestamp = Date.now();
        action.id = generateId();
        this.queue.push(action);
        await this.persist();
    }
    
    async sync(): Promise<SyncResult> {
        const results: SyncResult = { success: [], failed: [] };
        
        for (const action of this.queue) {
            try {
                // Replay action against cloud
                const result = await this.cloudSync(action);
                results.success.push({ actionId: action.id, result });
            } catch (error) {
                results.failed.push({ actionId: action.id, error });
            }
        }
        
        // Clear synced actions
        this.queue = this.queue.filter(a => 
            results.failed.some(f => f.actionId === a.id)
        );
        await this.persist();
        
        return results;
    }
    
    // Conflict resolution
    async resolveConflicts(local: Memory[], cloud: Memory[]): Promise<Memory[]> {
        const merged: Memory[] = [];
        
        for (const localMem of local) {
            const cloudMatch = cloud.find(m => m.id === localMem.id);
            
            if (!cloudMatch) {
                // New local memory
                merged.push(localMem);
            } else if (localMem.updatedAt > cloudMatch.updatedAt) {
                // Local is newer
                merged.push(localMem);
            } else {
                // Cloud is newer
                merged.push(cloudMatch);
            }
        }
        
        // Add cloud-only memories
        for (const cloudMem of cloud) {
            if (!merged.find(m => m.id === cloudMem.id)) {
                merged.push(cloudMem);
            }
        }
        
        return merged;
    }
}
```

---

### 33.4 Hybrid Compute Model

**Decision: local vs cloud for each request:**

```typescript
class HybridRouter {
    async route(request: AgentRequest): Promise<ExecutionPlan> {
        const decision = await this.evaluate(request);
        
        if (decision === 'local') {
            return this.executeLocal(request);
        }
        
        if (decision === 'cloud') {
            return this.executeCloud(request);
        }
        
        // Hybrid: local pre-processing, cloud reasoning
        const localResult = await this.localPreprocess(request);
        return this.executeCloud({ ...request, localContext: localResult });
    }
    
    private async evaluate(request: AgentRequest): Promise<'local' | 'cloud' | 'hybrid'> {
        const factors = {
            complexity: await this.estimateComplexity(request),
            latencyRequired: request.latencyRequirement,
            dataSensitivity: request.dataSensitivity,
            toolsRequired: request.requiredTools,
            connectivity: await this.checkConnectivity(),
            localModelCapability: this.localModel.canHandle(request),
        };
        
        // Decision tree
        if (factors.dataSensitivity === 'restricted') return 'local';
        if (!factors.connectivity) return 'local';
        if (factors.latencyRequired < 500 && !factors.toolsRequired.includes('external')) return 'local';
        if (factors.complexity === 'simple' && factors.localModelCapability) return 'local';
        if (factors.complexity === 'complex' || factors.toolsRequired.length > 0) return 'cloud';
        
        return 'hybrid';
    }
}
```

**Local model selection:**
```
For edge deployment, model size matters more than quality:

| Model | Size | Quality | RAM | Tokens/s | Use Case |
|-------|------|---------|-----|----------|----------|
| Llama 4 8B | 8B | Medium | 8GB | 40 | General edge assistant |
| Qwen 2.5 7B | 7B | Medium | 8GB | 45 | Code on edge |
| Phi-4 | 14B | High | 16GB | 25 | Quality edge assistant |
| Llama 4 70B | 70B | High | 140GB | 15 | On-prem enterprise |
| Mistral 7B | 7B | Medium | 8GB | 35 | Lightweight edge |
| Ollama + Gemma 2B | 2B | Low | 2GB | 60 | IoT / mobile |
```

---

### 33.5 Memory Sync Protocol

```typescript
interface MemorySyncProtocol {
    // Pull: Get updates from cloud since last sync
    async pull(lastSyncToken: string): Promise<{
        memories: MemoryDelta[];
        newSyncToken: string;
        hasMore: boolean;
    }>;
    
    // Push: Send local changes to cloud
    async push(deltas: MemoryDelta[]): Promise<{
        accepted: string[];
        conflicts: Conflict[];
    }>;
    
    // Resolve: Resolve conflicts with user input
    async resolve(conflicts: Conflict[]): Promise<MemoryDelta[]>;
}

interface MemoryDelta {
    id: string;
    action: 'create' | 'update' | 'delete';
    data?: Memory;
    timestamp: number;
    deviceId: string;
}

interface Conflict {
    memoryId: string;
    localVersion: Memory;
    cloudVersion: Memory;
    resolution?: 'use_local' | 'use_cloud' | 'merge';
}
```

**Sync frequency:**
```
Online: continuous (every 5 seconds)
Background: every 30 seconds
On reconnect: immediate full sync
On battery: every 60 seconds
On metered connection: only on demand
```

---

### 33.6 Local Knowledge Base

**Edge-optimized knowledge:**
```
For edge deployment, you cannot fit the full knowledge base locally.

Strategies:
1. Sync most-frequently-accessed documents only
   - Track access frequency per document
   - Keep top-100 most accessed locally
   - Sync others on-demand

2. Embedding compression
   - Use 256-dim embeddings instead of 1536 (save 6x)
   - Accept minor quality loss (5-10%)

3. On-device chunking
   - Chunk documents on device during upload
   - Save bandwidth (don't upload full file + re-chunk)

4. Incremental sync
   - Sync only changed documents
   - Cache document hashes to detect changes

5. Prioritize recent documents
   - Last 30 days of documents sync to edge
   - Older documents queried from cloud on-demand
```

---

### 33.7 Serverless Agent Deployment

**Agents as serverless functions:**
```
Trigger: API call / WebSocket message / Schedule / Event
Runtime: Firecracker microVM (cold start < 125ms)
Duration: Max 15 minutes
Memory: 128MB - 10GB
Ephemeral storage: 512MB

Each agent run is stateless (state in external Redis)
Each run costs: compute time + LLM calls + storage I/O

Cold start budget:
  Load model:        50ms (if using local model)
  Load config:       10ms
  Connect to Redis:  20ms
  Restore session:   30ms
  Total:             110ms (under 125ms Firecracker cold start)
```

**Warm vs cold starts:**
```
Warm start (session resume within 5 min):   ~50ms
Cold start (new session or expired):        ~125ms + model load (~50ms)

Strategy to reduce cold starts:
  1. Keep last N agent sessions in warm pool (N = expected concurrency)
  2. Predictive warm: pre-warm based on user's typical usage pattern
  3. Session TTL: keep session in Redis for 30 min after last activity
  4. No session persistence: stateless with all state in external services
```

---

### 33.8 Progressive Web Agent

**PWAgent — Running agents in the browser:**
```typescript
// Browser-side agent runtime (WebWorker)
class BrowserAgentRuntime {
    private worker: Worker;
    private localModel: WebLLM;
    private localDB: IndexedDB;
    
    async init() {
        // Load minimal local model (1-2B params) via WebLLM
        this.localModel = await WebLLM.create({
            model: 'gemma-2b-it',
            maxTokens: 1024,
        });
        
        // Open IndexedDB for local storage
        this.localDB = await openDB('agentos-edge', 1, {
            upgrade(db) {
                db.createObjectStore('memories', { keyPath: 'id' });
                db.createObjectStore('knowledge', { keyPath: 'id' });
                db.createObjectStore('offline-queue', { keyPath: 'id' });
            },
        });
        
        // Spawn WebWorker for background processing
        this.worker = new Worker('agent-worker.js');
    }
    
    async handleMessage(message: string): Promise<string> {
        if (navigator.onLine) {
            // Try cloud first
            try {
                return await this.cloudAgent(message);
            } catch {
                // Fallback to local
                return await this.localAgent(message);
            }
        } else {
            // Offline: use local model
            return await this.localAgent(message);
        }
    }
}
```

**Service worker for offline agent:**
```typescript
// service-worker.js
self.addEventListener('fetch', (event) => {
    // Intercept agent API calls
    if (event.request.url.includes('/api/agents/')) {
        event.respondWith(handleAgentRequest(event.request));
    }
});

async function handleAgentRequest(request: Request) {
    // Try network first
    try {
        const response = await fetch(request);
        // Cache successful responses
        if (response.ok) {
            cacheResponse(request, response.clone());
        }
        return response;
    } catch {
        // Network failed: use cached responses
        const cached = await getCachedResponse(request);
        if (cached) return cached;
        
        // No cache: run agent locally
        return localAgentResponse(request);
    }
}
```

---

## Chapter 34: Deployment Topologies

### 34.1 Deployment Models

```
Model A: Single-tenant on-premises
  - Customer runs entire AgentOS in their datacenter
  - All data stays on customer premises
  - Customer provides GPU compute for LLM
  - Vendor provides software + updates

Model B: Hybrid (SaaS + Edge)
  - Core agent runs in cloud (SaaS)
  - Edge node on customer network for sensitive data
  - Knowledge sync selectively (confidential docs stay on edge)
  - Agent routes queries based on data sensitivity

Model C: Fully managed cloud (multi-tenant)
  - Standard SaaS deployment
  - Customer data centers not involved
  - Maximum flexibility for vendor

Model D: Air-gapped (no internet)
  - Complete system runs in isolated network
  - All LLM inference on local GPUs
  - Updates delivered via physical media or secure transfer
  - Used by defense, intelligence, critical infrastructure
```

### 34.2 Hardware Requirements by Deployment

```
Model A (Single-tenant on-prem, 1000 users):

  Compute:
    - 4x GPU nodes (4x H100 each = 16 GPUs total)
    - 8x CPU nodes (64 cores, 256GB RAM each)
    - 3x database nodes (16 cores, 128GB RAM each)
    - 3x Redis nodes (16 cores, 64GB RAM each)
  Storage:
    - 10TB SSD (database primary)
    - 50TB HDD (knowledge base, backups)
  Network:
    - 10GbE internal
    - 1GbE external (management only)
  Power:
    - ~15kW (compute)
    - ~5kW (storage/network)

Model D (Air-gapped, 500 users):

  Compute:
    - 2x GPU nodes (8x H100 total)
    - 4x CPU nodes (48 cores, 192GB RAM)
    - 2x database nodes
  Storage:
    - 5TB SSD
    - 20TB HDD
  Network:
    - 10GbE internal only
    - No external connectivity
  Power:
    - ~10kW
```

---

### 34.3 Update Distribution for Edge/Air-Gapped

```
For edge/on-prem deployments, updates cannot be live-pulled:

1. Differential updates:
   - Only ship changed model weights (delta update)
   - Typical model update: 2-10GB (vs 140GB full model)
   - Binary diff between versions

2. Staged rollout:
   - Stage 1: Update non-critical components
   - Stage 2: Update agent runtime
   - Stage 3: Update LLM model (requires GPU downtime)

3. Rollback capability:
   - Keep previous 2 versions of all components
   - Database migration rollback scripts
   - Model version archive (last 2 models)

4. Offline update package:
   - Signed tarball with all components
   - Checksum manifest
   - Update scripts with dry-run mode
   - Can be delivered via USB drive for air-gapped
```

---

### 34.4 Edge Monitoring

```
What to monitor on edge:
  - GPU utilization (is local model keeping up?)
  - Queue depth (offline queue growing?)
  - Cache hit rate (knowledge requests hitting cloud?)
  - Sync lag (time since last successful sync)
  - Storage usage (memories consuming disk?)
  - Error rate (local model failing?)

How to monitor:
  - Local Prometheus + Grafana
  - Periodically sync metrics to cloud (configurable: every 5min / daily / never)
  - Health endpoint returns summary for external monitoring
  - SNMP traps for on-prem equipment
```
