import type {
  AgentResponse, Session, Memory, Document, SearchResult,
  UsageAnalytics, App, APIKey, Plugin, PluginInstall,
  Org, StatusResponse, ChangelogEntry,
} from "./types";

export class AgentOSError extends Error {
  constructor(public status: number, message: string) {
    super(`AgentOS API error ${status}: ${message}`);
    this.name = "AgentOSError";
  }
}

export class AgentOS {
  private baseUrl: string;
  private token: string | null;
  private _sessionId: string | null = null;

  constructor(options: { baseUrl?: string; token?: string } = {}) {
    this.baseUrl = (options.baseUrl || "http://localhost:8000").replace(/\/+$/, "");
    this.token = options.token || null;
  }

  get sessionId(): string | null {
    return this._sessionId;
  }

  private async request<T = unknown>(
    method: string,
    path: string,
    data?: Record<string, unknown>,
    params?: Record<string, string | number | undefined>
  ): Promise<T> {
    let url = `${this.baseUrl}${path}`;
    if (params) {
      const qs = Object.entries(params)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => `${k}=${v}`)
        .join("&");
      if (qs) url += `?${qs}`;
    }

    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;

    const resp = await fetch(url, {
      method,
      headers,
      body: data ? JSON.stringify(data) : undefined,
    });

    if (!resp.ok) {
      let msg: string;
      try {
        const body = await resp.json();
        msg = body.error || JSON.stringify(body);
      } catch {
        msg = await resp.text();
      }
      throw new AgentOSError(resp.status, msg);
    }

    return resp.json() as Promise<T>;
  }

  // ---- Auth ----

  async register(email: string, password: string, name?: string) {
    const result = await this.request<{ user: unknown; token: string }>(
      "POST", "/api/auth/register", { email, password, name }
    );
    this.token = result.token;
    return result;
  }

  async login(email: string, password: string) {
    const result = await this.request<{ user: unknown; token: string }>(
      "POST", "/api/auth/login", { email, password }
    );
    this.token = result.token;
    return result;
  }

  setToken(token: string) {
    this.token = token;
  }

  // ---- Chat ----

  async chat(message: string, sessionId?: string): Promise<AgentResponse> {
    const result = await this.request<AgentResponse>(
      "POST", "/api/chat",
      { message, session_id: sessionId || this._sessionId }
    );
    if (!this._sessionId && result.session_id) {
      this._sessionId = result.session_id;
    }
    return result;
  }

  // ---- Sessions ----

  async listSessions(): Promise<Session[]> {
    return this.request<Session[]>("GET", "/api/sessions");
  }

  // ---- Memory ----

  async listMemories(): Promise<Memory[]> {
    return this.request<Memory[]>("GET", "/api/memory");
  }

  async createMemory(content: string): Promise<Memory> {
    return this.request<Memory>("POST", "/api/memory", { content });
  }

  // ---- Knowledge ----

  async uploadDocument(file: File | Buffer, filename: string): Promise<Document> {
    const formData = new FormData();
    formData.append("file", new Blob([file]), filename);
    const headers: Record<string, string> = {};
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
    const resp = await fetch(`${this.baseUrl}/api/knowledge/upload`, {
      method: "POST", headers, body: formData,
    });
    if (!resp.ok) throw new AgentOSError(resp.status, await resp.text());
    return resp.json() as Promise<Document>;
  }

  async searchKnowledge(query: string, limit: number = 5): Promise<SearchResult[]> {
    const result = await this.request<{ results: SearchResult[] }>(
      "POST", "/api/knowledge/search", { query, limit }
    );
    return result.results;
  }

  // ---- Developer ----

  async createApp(name: string, description?: string, scopes?: string[]): Promise<App> {
    return this.request<App>("POST", "/api/developer/apps", { name, description, scopes });
  }

  async listApps(): Promise<App[]> {
    return this.request<App[]>("GET", "/api/developer/apps");
  }

  async deleteApp(appId: string): Promise<void> {
    await this.request("DELETE", `/api/developer/apps/${appId}`);
  }

  async createApiKey(name?: string, appId?: string): Promise<APIKey> {
    return this.request<APIKey>("POST", "/api/developer/keys", { name, app_id: appId });
  }

  async listApiKeys(): Promise<APIKey[]> {
    return this.request<APIKey[]>("GET", "/api/developer/keys");
  }

  async revokeApiKey(keyId: string): Promise<void> {
    await this.request("DELETE", `/api/developer/keys/${keyId}`);
  }

  async getUsage(days: number = 30): Promise<UsageAnalytics> {
    return this.request<UsageAnalytics>("GET", "/api/developer/usage", undefined, { days });
  }

  async listPlugins(status: string = "published"): Promise<Plugin[]> {
    return this.request<Plugin[]>("GET", "/api/developer/plugins", undefined, { status });
  }

  async createPlugin(name: string, displayName: string, description?: string): Promise<Plugin> {
    return this.request<Plugin>("POST", "/api/developer/plugins", {
      name, display_name: displayName, description,
    });
  }

  async installPlugin(pluginId: string, config?: Record<string, unknown>): Promise<PluginInstall> {
    return this.request<PluginInstall>(
      "POST", `/api/developer/plugins/${pluginId}/install`, { config: config || {} }
    );
  }

  async listInstalledPlugins(): Promise<PluginInstall[]> {
    return this.request<PluginInstall[]>("GET", "/api/developer/plugins/installed");
  }

  // ---- Org ----

  async createOrg(name: string): Promise<Org> {
    return this.request<Org>("POST", "/api/orgs", { name });
  }

  async listOrgs(): Promise<Org[]> {
    return this.request<Org[]>("GET", "/api/orgs");
  }

  // ---- GDPR ----

  async requestDataExport(): Promise<unknown> {
    return this.request("POST", "/api/gdpr/export");
  }

  async requestDataDeletion(): Promise<unknown> {
    return this.request("POST", "/api/gdpr/delete");
  }

  // ---- Status ----

  async status(): Promise<StatusResponse> {
    return this.request<StatusResponse>("GET", "/api/developer/status");
  }

  async changelog(): Promise<ChangelogEntry[]> {
    return this.request<ChangelogEntry[]>("GET", "/api/developer/changelog");
  }
}
