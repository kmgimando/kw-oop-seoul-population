import { CONFIG } from "./config.js";
import { adaptResponse } from "./adapter.js";
import { validateQuery } from "./model.js";
import { fetchMock } from "./mock-provider.js";

// Provisional GET contract. This function is NOT used in default mock mode.
export async function fetchHttp(query, { signal, fetchImpl = fetch } = {}) {
  const params = new URLSearchParams({ district_code: query.district_code,
    start_date: query.start_date, end_date: query.end_date, methods: JSON.stringify(query.methods) });
  const response = await fetchImpl(`${CONFIG.apiUrl}?${params}`, { signal, headers: { Accept: "application/json" } });
  if (!response.ok) {
    let message = "";
    try { const body = await response.json(); if (typeof body.error?.message === "string") message = body.error.message; } catch { /* Non-JSON errors use HTTP status. */ }
    throw new Error(message || `분석 요청에 실패했습니다. (HTTP ${response.status})`);
  }
  return response.json();
}
export async function fetchAnalysis(query, { signal } = {}) {
  validateQuery(query);
  const raw = CONFIG.mode === "mock" ? await fetchMock(query, { signal }) : await fetchHttp(query, { signal });
  return adaptResponse(raw, query);
}
