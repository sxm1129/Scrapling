const BASE = '';

export async function fetchAPI(path: string, options?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
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

  // Scan trigger
  triggerScan: () => fetchAPI('/api/scan/trigger', { method: 'POST' }),
};
