import { DISTRICTS, METHODS, WINDOWS } from "./config.js";

export function isISODate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith("0000")) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function validateQuery(query) {
  if (!DISTRICTS.some(([code]) => code === query.district_code)) throw new Error("서울시 자치구를 선택하세요.");
  if (!isISODate(query.start_date) || !isISODate(query.end_date)) throw new Error("유효한 시작일과 종료일을 입력하세요.");
  if (query.start_date > query.end_date) throw new Error("시작일은 종료일보다 늦을 수 없습니다.");
  if (!Object.hasOwn(METHODS, query.selected_method)) throw new Error("탐지 방법을 선택하세요.");
  for (const method of Object.keys(METHODS)) {
    const settings = query.methods?.[method];
    if (!settings || !WINDOWS.includes(settings.window)) throw new Error("기준 기간은 7·14·28·56일 중 선택하세요.");
    if (!Number.isFinite(settings.threshold) || settings.threshold <= 0) throw new Error("임계값은 0보다 큰 유한한 숫자여야 합니다.");
    if (method === "seasonal" && (!Number.isInteger(settings.min_samples) || settings.min_samples < 1 || settings.min_samples > settings.window)) {
      throw new Error("동일 그룹 최소 표본은 1 이상 기준 기간 이하의 정수여야 합니다.");
    }
  }
  return query;
}

export function stateOf(result) {
  return result.is_anomaly === true ? "anomaly" : result.is_anomaly === false ? "normal" : "unavailable";
}
export const STATE_LABELS = Object.freeze({ anomaly: "이상", normal: "정상", unavailable: "판정불가" });
export const STATUS_LABELS = Object.freeze({ evaluated: "판정 완료", insufficient_history: "표본 부족", zero_baseline: "기준값 0", zero_variance: "표준편차 0" });
export function summarize(results) {
  const stats = { total: results.length, anomaly: 0, normal: 0, unavailable: 0 };
  for (const row of results) stats[stateOf(row)]++;
  stats.evaluated = stats.anomaly + stats.normal;
  stats.rate = stats.evaluated ? stats.anomaly / stats.evaluated : null;
  return stats;
}
export const number = value => value === null || value === undefined ? "—" : value.toLocaleString("ko-KR", { maximumFractionDigits: 1 });
export const percent = value => value === null || value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;
export function settingLabel(method, settings) {
  const threshold = METHODS[method].ratio ? `${Number((settings.threshold * 100).toFixed(6))}%` : `${settings.threshold}σ`;
  return `${settings.window}일 · 임계값 ${threshold}${method === "seasonal" ? ` · 최소 ${settings.min_samples}개` : ""}`;
}

// A generation guard also protects against transports that ignore AbortSignal.
export class LatestRequest {
  constructor(provider) { this.provider = provider; this.generation = 0; }
  invalidate() { this.generation++; this.controller?.abort(); }
  async run(query) {
    this.invalidate();
    const generation = this.generation;
    this.controller = new AbortController();
    try {
      const data = await this.provider(query, { signal: this.controller.signal });
      return { stale: generation !== this.generation, data };
    } catch (error) {
      if (generation !== this.generation) return { stale: true };
      throw error;
    }
  }
}
