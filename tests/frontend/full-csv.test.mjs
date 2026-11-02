import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { parseProfile, dataMode, districtOptions, sourcePresentation, DISTRICTS } from "../../static/js/config.js";
import { adaptResponse } from "../../static/js/adapter.js";
import { summarize } from "../../static/js/model.js";
import { populationConfig } from "../../static/js/charts.js";

const profile = { profile_version: 1, default_mode: "api", districts: DISTRICTS,
  start_date: "2023-01-01", end_date: "2026-09-13", default_start_date: "2026-06-16",
  default_end_date: "2026-09-13", source: { kind: "seoul_population", label: "서울 생활인구 CSV" },
  missing_dates: ["2024-02-29"] };

test("real CSV profile enables exactly the supported 25 regions and API default", () => {
  const parsed = parseProfile(JSON.stringify(profile));
  assert.ok(parsed);
  assert.equal(dataMode("", parsed), "api");
  assert.deepEqual(districtOptions("api", parsed), DISTRICTS);
  assert.ok(districtOptions("api", parsed).every(([code]) => code !== "11000"));
});
test("real data labels and empty-result guidance are not marked synthetic", () => {
  const text = sourcePresentation(profile);
  assert.equal(text.label, "CSV API");
  assert.match(text.description, /25개 자치구.*2023-01-01.*2026-09-13/);
  assert.match(text.description, /2024-02-29/);
  assert.doesNotMatch(text.title + text.description + text.empty, /합성|실제 서울시 분석 결과가 아닙니다/);
  assert.match(text.empty, /서울 생활인구 CSV/);
});
test("default period cannot advertise dates outside the actual CSV coverage", () => {
  for (const changed of [{ default_start_date: "2022-01-01" },
    { default_end_date: "2030-01-01" }, { default_start_date: "2026-09-14" }]) {
    assert.equal(parseProfile(JSON.stringify({ ...profile, ...changed })), null);
  }
});
test("invalid calendar dates and malformed missing-date metadata are rejected safely", () => {
  for (const changed of [{ start_date: "2023-02-29" }, { end_date: "2026-09-31" },
    { default_start_date: "2026-06-31" }, { missing_dates: "2024-02-29" },
    { missing_dates: ["2024-02-30"] }, { missing_dates: null }]) {
    assert.equal(parseProfile(JSON.stringify({ ...profile, ...changed })), null);
  }
});
test("explicit Mock selection and synthetic identity remain available", () => {
  assert.equal(dataMode("?source=mock", profile), "mock");
  const sample = { ...profile, source: { kind: "synthetic_sample", label: "합성 샘플 CSV" } };
  assert.match(sourcePresentation(sample).description, /실제 서울시 분석 결과가 아닙니다/);
});

const evidence = process.env.FULL_CSV_EVIDENCE
  ? JSON.parse(await readFile(process.env.FULL_CSV_EVIDENCE, "utf8")) : null;
const optional = { skip: evidence ? false : "Set FULL_CSV_EVIDENCE to real Flask responses" };
test("real 25-region Flask payloads preserve every number and detail in the adapter", optional, () => {
  assert.equal(evidence.district_count, 25);
  assert.equal(new Set(evidence.cases.filter(c => c.label === "all_districts")
    .map(c => c.query.district_code)).size, 25);
  assert.ok(parseProfile(JSON.stringify(evidence.profile)));
  for (const c of evidence.cases) {
    const view = adaptResponse(c.payload, c.query);
    for (const block of c.payload.methods) {
      assert.deepEqual(view.methods[block.method].results, block.results);
      assert.deepEqual(view.methods[block.method].details, block.details);
    }
  }
});
test("annual comparison and chart values preserve actual CSV results", optional, () => {
  const annual = evidence.cases.find(c => c.label === "annual");
  const view = adaptResponse(annual.payload, annual.query);
  for (const [method, expected] of Object.entries({ moving_average: 120, z_score: 1, seasonal: 46 })) {
    assert.equal(summarize(view.methods[method].results).anomaly, expected);
    const chart = populationConfig(view.methods[method].results, () => {});
    assert.deepEqual(chart.data.datasets[2].data, view.methods[method].results.map(row => row.actual));
  }
  assert.match(view.methods.seasonal.details["2025-09-13"].explanation, /19\.8% 많았습니다/);
});
test("missing leap day stays absent and does not become a normal zero-valued point", optional, () => {
  const gap = evidence.cases.find(c => c.label === "gap");
  const view = adaptResponse(gap.payload, gap.query);
  for (const block of Object.values(view.methods)) {
    assert.ok(block.results.every(row => row.date !== "2024-02-29"));
    assert.equal(block.results.find(row => row.date === "2024-03-01").is_anomaly, null);
  }
});

test("live real-data HTTP responses match verified Flask payloads", {
  skip: evidence && process.env.FULL_CSV_BASE_URL ? false : "Set FULL_CSV_BASE_URL and FULL_CSV_EVIDENCE",
  timeout: 60000,
}, async () => {
  for (const c of evidence.cases) {
    const url = new URL("/api/analysis", process.env.FULL_CSV_BASE_URL);
    for (const key of ["district_code", "start_date", "end_date"]) url.searchParams.set(key, c.query[key]);
    url.searchParams.set("methods", JSON.stringify(c.query.methods));
    const response = await fetch(url);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), c.payload);
  }
});
