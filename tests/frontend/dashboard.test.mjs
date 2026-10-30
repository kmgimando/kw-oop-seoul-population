import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { DISTRICTS, METHODS } from "../../static/js/config.js";
import { validateQuery, summarize, stateOf, percent, number, LatestRequest, isISODate, settingLabel } from "../../static/js/model.js";
import { adaptResponse } from "../../static/js/adapter.js";
import { buildMockResponse, fetchMock } from "../../static/js/mock-provider.js";
import { fetchHttp } from "../../static/js/api.js";
import { populationConfig, comparisonConfig } from "../../static/js/charts.js";

const fixture = JSON.parse(await readFile(new URL("../../static/mock/detection-fixtures.json", import.meta.url), "utf8"));
const query = () => ({ district_code: "11440", start_date: "2024-01-01", end_date: "2024-03-30", selected_method: "seasonal", scenario: "mixed",
  methods: Object.fromEntries(Object.entries(METHODS).map(([key, value]) => [key, { window: value.window, threshold: value.threshold, ...(key === "seasonal" ? { min_samples: 4 } : {}) }])) });
const result = q => adaptResponse(buildMockResponse(fixture, q), q);

test("all 25 districts and three methods can be requested", () => {
  assert.equal(DISTRICTS.length, 25); assert.equal(new Set(DISTRICTS.map(d => d[0])).size, 25);
  for (const [code, name] of DISTRICTS) {
    for (const method of Object.keys(METHODS)) {
      const q = query(); q.district_code = code; q.selected_method = method;
      validateQuery(q);
      const rows = result(q).methods[method].results;
      assert.equal(rows.length, 90);
      assert.ok(rows.every(r => r.district_code === code && r.district_name === name && r.method === method));
    }
  }
});
test("valid calendar days, leap day, invalid date and reversed period", () => {
  assert.ok(isISODate("2024-02-29"));
  for (const day of ["0000-01-01", "2023-02-29", "2024-02-30", "2024-13-01", "", "2024-2-01"]) assert.equal(isISODate(day), false);
  const q = query(); q.start_date = "2024-03-01"; q.end_date = "2024-02-29";
  assert.throws(() => validateQuery(q), /시작일/);
});
test("invalid threshold and minimum samples are rejected", () => {
  for (const value of [0, -1, NaN, Infinity, "10", true]) {
    const q = query(); q.methods.seasonal.threshold = value;
    assert.throws(() => validateQuery(q), /임계값/);
  }
  for (const value of [0, 1.5, 29, true]) {
    const q = query(); q.methods.seasonal.min_samples = value;
    assert.throws(() => validateQuery(q), /표본/);
  }
});
test("threshold units distinguish ratios and Z-scores", () => {
  assert.match(settingLabel("seasonal", query().methods.seasonal), /10%/);
  assert.match(settingLabel("moving_average", query().methods.moving_average), /10%/);
  assert.match(settingLabel("z_score", query().methods.z_score), /3σ/);
});
test("summary uses evaluated denominator and keeps no-denominator rate null", () => {
  const rows = [{ is_anomaly: true }, { is_anomaly: false }, { is_anomaly: null }, { is_anomaly: null }];
  assert.deepEqual(summarize(rows), { total: 4, anomaly: 1, normal: 1, unavailable: 2, evaluated: 2, rate: 0.5 });
  assert.equal(summarize([{ is_anomaly: null }]).rate, null);
  assert.equal(summarize([]).rate, null);
  assert.equal(percent(null), "—"); assert.equal(number(null), "—"); assert.equal(number(0), "0");
});
test("mock covers normal, anomalous and unavailable results", () => {
  for (const block of Object.values(result(query()).methods)) {
    const stats = summarize(block.results);
    assert.ok(stats.anomaly > 0); assert.ok(stats.normal > 0); assert.ok(stats.unavailable > 0);
  }
});
test("zero baseline/variance are evaluated rather than always unavailable", () => {
  const q = query(); q.scenario = "zero";
  for (const [method, block] of Object.entries(result(q).methods)) {
    const rows = block.results.filter(r => r.status === (method === "z_score" ? "zero_variance" : "zero_baseline"));
    assert.ok(rows.length);
    assert.ok(rows.some(r => stateOf(r) === "normal"));
    assert.ok(rows.some(r => stateOf(r) === "anomaly"));
    assert.ok(rows.every(r => r.score === null));
  }
});
test("chart carries actual, baseline, both bounds, anomaly and missing markers", () => {
  const rows = result(query()).methods.seasonal.results;
  const config = populationConfig(rows, () => {});
  assert.equal(config.data.datasets.length, 6);
  assert.deepEqual(config.data.datasets[0].data, rows.map(r => r.lower_bound));
  assert.deepEqual(config.data.datasets[1].data, rows.map(r => r.upper_bound));
  assert.deepEqual(config.data.datasets[2].data, rows.map(r => r.actual));
  assert.deepEqual(config.data.datasets[3].data, rows.map(r => r.expected));
  assert.equal(config.data.datasets[0].data[0], null);
  assert.equal(config.data.datasets[3].data[0], null);
  assert.equal(config.options.plugins.unavailableBands.states[0], "unavailable");
  assert.equal(config.options.animation, false);
});
test("comparison chart counts match result summary", () => {
  const data = result(query()); const config = comparisonConfig(data.methods);
  Object.values(data.methods).forEach((block, i) => {
    const stats = summarize(block.results);
    assert.equal(config.data.datasets[0].data[i], stats.anomaly);
    assert.equal(config.data.datasets[1].data[i], stats.normal);
    assert.equal(config.data.datasets[2].data[i], stats.unavailable);
  });
});
test("empty scenario and out-of-range dates produce empty arrays", () => {
  const q = query(); q.scenario = "empty";
  assert.ok(Object.values(result(q).methods).every(b => b.results.length === 0));
  q.scenario = "mixed"; q.start_date = "2025-01-01"; q.end_date = "2025-02-01";
  assert.ok(Object.values(result(q).methods).every(b => b.results.length === 0));
});
test("window, threshold and minimum sample changes affect mock output", () => {
  const q = query(); const initial = result(q).methods.seasonal;
  q.methods.seasonal.threshold = 100;
  assert.equal(summarize(result(q).methods.seasonal.results).anomaly, 0);
  q.methods.seasonal.window = 7; q.methods.seasonal.min_samples = 3;
  const changed = result(q).methods.seasonal;
  const weekend = changed.results.find(r => r.date === "2024-02-03");
  assert.equal(weekend.history_size, 7); assert.equal(weekend.is_anomaly, null);
  assert.equal(initial.results.find(r => r.date === "2024-02-03").history_size, 28);
});
test("all preset windows and valid min_samples preserve result contract", () => {
  for (const window of [7, 14, 28, 56]) {
    const q = query();
    Object.values(q.methods).forEach(s => { s.window = window; });
    q.methods.seasonal.min_samples = window;
    validateQuery(q); result(q);
  }
});
test("adapter rejects missing/invalid types, mismatched settings, duplicate dates", () => {
  const q = query();
  const mutate = fn => { const payload = buildMockResponse(fixture, q); fn(payload); assert.throws(() => adaptResponse(payload, q), /형식/); };
  mutate(p => { p.schema_version = 99; });
  mutate(p => { p.methods.pop(); });
  mutate(p => { p.methods[0].settings.window = 14; });
  mutate(p => { p.methods[0].results[0].is_anomaly = "false"; });
  mutate(p => { p.methods[0].results[0].expected = "0"; });
  mutate(p => { p.methods[0].results[0].actual = Infinity; });
  mutate(p => { p.methods[0].results.push(p.methods[0].results[0]); });
});
test("adapter preserves null and source payload is not mutated", () => {
  const q = query(); const payload = buildMockResponse(fixture, q), before = structuredClone(payload);
  const data = adaptResponse(payload, q);
  assert.equal(data.methods.seasonal.results[0].expected, null);
  assert.equal(data.methods.seasonal.results[0].is_anomaly, null);
  assert.deepEqual(payload, before);
});
test("latest request wins even when old transport ignores abort", async () => {
  const resolvers = [];
  const latest = new LatestRequest(() => new Promise(resolve => resolvers.push(resolve)));
  const old = latest.run("old"), newer = latest.run("new");
  resolvers[1]("new data"); assert.deepEqual(await newer, { stale: false, data: "new data" });
  resolvers[0]("old data"); assert.equal((await old).stale, true);
});
test("stale errors and invalidated requests cannot affect newer UI", async () => {
  const resolvers = [];
  const latest = new LatestRequest(() => new Promise((resolve, reject) => resolvers.push({ resolve, reject })));
  const old = latest.run("old"), newer = latest.run("new");
  resolvers[0].reject(new Error("old failure")); assert.equal((await old).stale, true);
  latest.invalidate(); resolvers[1].resolve("outdated"); assert.equal((await newer).stale, true);
});
test("current errors propagate and mock errors are explicit", async () => {
  const latest = new LatestRequest(async () => { throw new Error("current error"); });
  await assert.rejects(latest.run(query()), /current error/);
  const q = query(); q.scenario = "error";
  await assert.rejects(fetchMock(q), /시연용 오류/);
});
test("abort stops slow mock request", async () => {
  const controller = new AbortController(), q = query(); q.scenario = "slow";
  const pending = fetchMock(q, { signal: controller.signal }); controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
});
test("HTTP provider uses provisional contract and handles HTTP JSON error", async () => {
  const q = query(); let url;
  await fetchHttp(q, { fetchImpl: async value => { url = value; return { ok: true, json: async () => ({}) }; } });
  const params = new URL(url, "http://localhost").searchParams;
  assert.equal(params.get("district_code"), q.district_code);
  assert.deepEqual(JSON.parse(params.get("methods")), q.methods);
  await assert.rejects(fetchHttp(q, { fetchImpl: async () => ({ ok: false, status: 400, json: async () => ({ error: { message: "입력 오류" } }) }) }), /입력 오류/);
  await assert.rejects(fetchHttp(q, { fetchImpl: async () => ({ ok: false, status: 503, json: async () => { throw new Error("not JSON"); } }) }), /503/);
});
