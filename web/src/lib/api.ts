const BASE = '';

export class APIError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function fetchAPI(path: string, options?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!res.ok) {
    let msg = `API error: ${res.status}`;
    try {
      const body = await res.json();
      msg = body.detail || body.error || msg;
      // Pydantic validation errors
      if (Array.isArray(body.detail)) {
        msg = body.detail.map((d: any) => `${d.loc?.join('.')}: ${d.msg}`).join('; ');
      }
    } catch {}
    throw new APIError(res.status, msg);
  }
  return res.json();
}

/** Show user-friendly error alert */
export function handleError(e: unknown, context?: string): void {
  const msg = e instanceof APIError
    ? (e.status === 422 ? `输入验证失败: ${e.message}` : e.message)
    : (e instanceof Error ? e.message : '未知错误');
  const prefix = context ? `${context}: ` : '';
  console.error(prefix, e);
  if (typeof window !== 'undefined') {
    alert(`${prefix}${msg}`);
  }
}

export const api = {
  // Dashboard
  getDashboard: () => fetchAPI('/api/dashboard'),

  // Offers
  getOffers: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchAPI(`/api/offers${qs}`);
  },

  // Violations
  getViolations: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchAPI(`/api/violations${qs}`);
  },
  getViolation: (id: number) => fetchAPI(`/api/violations/${id}`),

  // Baselines
  getBaselines: () => fetchAPI('/api/baselines'),
  createBaseline: (data: any) => fetchAPI('/api/baselines', { method: 'POST', body: JSON.stringify(data) }),
  deleteBaseline: (id: number) => fetchAPI(`/api/baselines/${id}`, { method: 'DELETE' }),

  // Keywords
  getKeywords: () => fetchAPI('/api/keywords'),
  addKeyword: (data: any) => fetchAPI('/api/keywords', { method: 'POST', body: JSON.stringify(data) }),
  toggleKeyword: (id: number, enabled: boolean) =>
    fetchAPI(`/api/keywords/${id}`, { method: 'PUT', body: JSON.stringify({ enabled }) }),
  deleteKeyword: (id: number) => fetchAPI(`/api/keywords/${id}`, { method: 'DELETE' }),

  // Whitelist
  getWhitelist: () => fetchAPI('/api/whitelist'),
  createWhitelist: (data: any) => fetchAPI('/api/whitelist', { method: 'POST', body: JSON.stringify(data) }),
  revokeWhitelist: (id: number) => fetchAPI(`/api/whitelist/${id}`, { method: 'DELETE' }),

  // Cookies
  getCookies: () => fetchAPI('/api/cookies'),
  saveCookies: (data: any) => fetchAPI('/api/cookies', { method: 'POST', body: JSON.stringify(data) }),

  // Export
  exportViolations: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchAPI(`/api/export/violations${qs}`);
  },

  // Scan trigger (legacy, kept for backward compat)
  triggerScan: () => fetchAPI('/api/collection/trigger', { method: 'POST' }),

  // Collection Management
  getCollectionStatus: () => fetchAPI('/api/collection/status'),
  getCollectionJobs: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchAPI(`/api/collection/jobs${qs}`);
  },
  getCollectionJob: (id: number) => fetchAPI(`/api/collection/jobs/${id}`),
  triggerFullScan: (keyword?: string) => {
    const qs = keyword ? `?keyword=${encodeURIComponent(keyword)}` : '';
    return fetchAPI(`/api/collection/trigger${qs}`, { method: 'POST' });
  },
  triggerPlatformScan: (platform: string, keyword?: string) =>
    fetchAPI(`/api/collection/trigger/${platform}`, {
      method: 'POST',
      body: JSON.stringify({ keyword: keyword || null }),
    }),
  triggerSingleScrape: (platform: string, url: string) =>
    fetchAPI('/api/collection/scrape-url', {
      method: 'POST',
      body: JSON.stringify({ platform, url }),
    }),
  cancelJob: (id: number) => fetchAPI(`/api/collection/jobs/${id}`, { method: 'DELETE' }),
  getPlatforms: () => fetchAPI('/api/collection/platforms'),
};
