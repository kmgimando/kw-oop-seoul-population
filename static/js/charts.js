import { METHODS } from "./config.js";
import { number, stateOf, summarize, STATE_LABELS } from "./model.js";

const COLORS = { actual: "#3268cb", expected: "#148779", anomaly: "#cd4b50", unavailable: "#8998a7" };
const unavailableBands = {
  id: "unavailableBands",
  beforeDatasetsDraw(chart, args, options) {
    const { ctx, chartArea, scales: { x } } = chart;
    if (!chartArea) return;
    const width = options.states.length > 1 ? Math.abs(x.getPixelForValue(1) - x.getPixelForValue(0)) : chartArea.width;
    ctx.save(); ctx.fillStyle = "rgba(137,152,167,0.10)";
    options.states.forEach((state, i) => {
      if (state !== "unavailable") return;
      const left = Math.max(chartArea.left, x.getPixelForValue(i) - width / 2);
      const right = Math.min(chartArea.right, x.getPixelForValue(i) + width / 2);
      ctx.fillRect(left, chartArea.top, right - left, chartArea.height);
    });
    ctx.restore();
  },
};
const selectedDate = {
  id: "selectedDate",
  afterDatasetsDraw(chart, args, options) {
    if (options.index < 0 || !chart.chartArea) return;
    const x = chart.scales.x.getPixelForValue(options.index);
    const { ctx, chartArea } = chart;
    ctx.save(); ctx.strokeStyle = "#778da5"; ctx.setLineDash([3, 4]);
    ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke(); ctx.restore();
  },
};
export function populationConfig(results, onSelect) {
  const points = key => results.map(row => row[key]);
  return {
    type: "line",
    plugins: [unavailableBands, selectedDate],
    data: {
      labels: results.map(row => row.date),
      datasets: [
        { label: "정상 범위 하한", data: points("lower_bound"), borderColor: "#14877944", borderWidth: 1, pointRadius: 0, order: 3 },
        { label: "정상 범위 상한", data: points("upper_bound"), borderColor: "#14877944", borderWidth: 1, pointRadius: 0, fill: "-1", backgroundColor: "#14877912", order: 3 },
        { label: "실제 생활인구", data: points("actual"), borderColor: COLORS.actual, borderWidth: 2, pointRadius: results.length < 5 ? 3 : 0, pointHoverRadius: 4, order: 2 },
        { label: "기준값", data: points("expected"), borderColor: COLORS.expected, borderWidth: 1.6, borderDash: [5, 3], pointRadius: 0, order: 2 },
        { label: "이상", data: results.map(row => row.is_anomaly === true ? row.actual : null), borderColor: COLORS.anomaly, backgroundColor: COLORS.anomaly, showLine: false, pointRadius: 4, pointHoverRadius: 6, order: 0 },
        { label: "판정불가", data: results.map(row => row.is_anomaly === null ? row.actual : null), backgroundColor: COLORS.unavailable, borderColor: COLORS.unavailable, showLine: false, pointStyle: "rectRot", pointRadius: 3, order: 1 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      onClick: (event, elements) => { if (elements.length) onSelect(results[elements[0].index].date); },
      plugins: {
        legend: { display: false },
        unavailableBands: { states: results.map(stateOf) }, selectedDate: { index: -1 },
        tooltip: { backgroundColor: "#142b45", padding: 12,
          callbacks: {
            title: items => `${results[items[0].dataIndex].date} · ${STATE_LABELS[stateOf(results[items[0].dataIndex])]}`,
            label: context => `${context.dataset.label}: ${number(context.raw)}명`,
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0, color: "#73869a", font: { size: 10 }, callback(value) { return this.getLabelForValue(value).slice(5); } }, border: { display: false } },
        y: { beginAtZero: true, ticks: { maxTicksLimit: 5, color: "#73869a", font: { size: 10 }, callback: value => value >= 10000 ? `${Number((value / 10000).toFixed(1))}만` : number(value) }, grid: { color: "#eef2f6" }, border: { display: false } },
      },
    },
  };
}
export function comparisonConfig(methods) {
  const blocks = Object.values(methods);
  const stats = blocks.map(block => summarize(block.results));
  return {
    type: "bar",
    data: { labels: blocks.map(block => METHODS[block.method].name), datasets: [
      { label: "이상", data: stats.map(s => s.anomaly), backgroundColor: COLORS.anomaly },
      { label: "정상", data: stats.map(s => s.normal), backgroundColor: COLORS.expected },
      { label: "판정불가", data: stats.map(s => s.unavailable), backgroundColor: "#b6c2ce" },
    ] },
    options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: false,
      datasets: { bar: { maxBarThickness: 25 } },
      plugins: { legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "rect", boxWidth: 8, font: { size: 10 } } }, tooltip: { callbacks: { label: c => `${c.dataset.label}: ${c.raw}건` } } },
      scales: { x: { stacked: true, beginAtZero: true, ticks: { precision: 0, font: { size: 10 } }, grid: { color: "#eef2f6" }, title: { display: true, text: "날짜 수 (건)", font: { size: 10 } } }, y: { stacked: true, grid: { display: false }, ticks: { font: { size: 11 } }, border: { display: false } } },
    },
  };
}
let populationChart, comparisonChart;
export function renderCharts(block, methods, onSelect) {
  if (typeof globalThis.Chart !== "function") throw new Error("Chart.js를 불러오지 못했습니다. static/vendor 파일을 확인하세요.");
  populationChart?.destroy(); comparisonChart?.destroy();
  populationChart = new globalThis.Chart(document.getElementById("population-chart"), populationConfig(block.results, onSelect));
  comparisonChart = new globalThis.Chart(document.getElementById("comparison-chart"), comparisonConfig(methods));
}
export function highlightDate(day) {
  if (!populationChart) return;
  populationChart.options.plugins.selectedDate.index = populationChart.data.labels.indexOf(day);
  populationChart.draw();
}
