const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const api = {
  async get<T>(path: string): Promise<T> { const response = await fetch(`${API}${path}`); const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(body.detail || `Backend request failed (${response.status})`); return body as T; },
  websocketUrl() { return API.replace(/^http/, "ws") + "/ws/events"; },
};
