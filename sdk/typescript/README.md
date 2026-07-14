# AgentOS TypeScript SDK

Build and integrate intelligent agents with AgentOS.

## Install

```bash
npm install agentos
# or from source:
cd sdk/typescript && npm install && npm run build
```

## Quickstart

```typescript
import { AgentOS } from "agentos";

const client = new AgentOS({ baseUrl: "http://localhost:8000" });

// Register and authenticate
await client.register("dev@example.com", "password123");

// Chat with the agent
const response = await client.chat("What is 2 + 2?");
console.log(response.response); // "2 + 2 = 4"

// Upload knowledge
const doc = await client.uploadDocument(fileBuffer, "doc.txt");

// Search knowledge
const results = await client.searchKnowledge("What is the policy?");

// Developer API
const app = await client.createApp("My App");
const key = await client.createApiKey("my-key");
const usage = await client.getUsage(7);

// Plugins
const plugin = await client.createPlugin("my-plugin", "My Plugin");
await client.installPlugin(plugin.id);
```

## Authentication

```typescript
// JWT token
const client = new AgentOS({ token: "your-jwt-token" });

// Or login
const client = new AgentOS();
await client.login("user@example.com", "password");
```

## Error Handling

```typescript
import { AgentOS, AgentOSError } from "agentos";

try {
  const response = await client.chat("Hello");
} catch (e) {
  if (e instanceof AgentOSError) {
    console.error(`Error ${e.status}: ${e.message}`);
  }
}
```

## API Reference

See `src/types.ts` for all type definitions.
Full OpenAPI spec: `GET /api/developer/openapi.json`
