import { getToken, TENANT_ID } from './auth.js';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

async function authHeaders() {
  const token = getToken();

  if (!token) {
    throw new Error('Missing Cognito token. Please log in again.');
  }

  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  };
}

async function request(path, options = {}) {
  if (!API_BASE_URL) {
    throw new Error('Missing VITE_API_BASE_URL');
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(await authHeaders()),
      ...(options.headers || {}),
    },
  });

  const text = await res.text();
  const body = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const message = body?.error || `Request failed: ${res.status}`;
    throw new Error(message);
  }

  return body;
}

export function getMonthlyMetrics(month) {
  const params = new URLSearchParams({ month });
  return request(`/frontend/tenants/${encodeURIComponent(TENANT_ID)}/metrics/monthly?${params.toString()}`);
}

export function createCampaign({ body, phones, scheduledAt }) {
  return request(`/frontend/tenants/${encodeURIComponent(TENANT_ID)}/campaigns`, {
    method: 'POST',
    body: JSON.stringify({
      body,
      phone_numbers: phones,
      next_run_time: new Date(scheduledAt).toISOString(),
      active: true,
    }),
  });
}
