(() => {
  const payload = document.getElementById("performance-chart-data");
  const grid = document.getElementById("performance-chart-grid");
  const buttons = [...document.querySelectorAll("[data-chart-metric]")];
  const heading = document.getElementById("performance-chart-heading");
  if (!payload || !grid || !buttons.length || !heading) return;

  const charts = JSON.parse(payload.textContent || "[]");
  const metrics = {
    total_token_throughput_per_gpu: { label: "Total token throughput", unit: "token/s/GPU" },
    output_token_throughput_per_gpu: { label: "Output token throughput", unit: "token/s/GPU" },
    mean_ttft: { label: "TTFT", unit: "s" },
    mean_tpot: { label: "TPOT", unit: "s", autoRange: true },
  };
  const fallbackColors = ["#7559f2", "#3f8cff", "#9a63d8", "#00a6a6", "#d14da5"];
  const hardwareColors = {
    H100: "#1b7f3a",
    H200: "#2e9d50",
    B200: "#52b96b",
    B300: "#82cf8e",
    MI300X: "#9f241f",
    MI325X: "#bd3828",
    MI350X: "#d75032",
    MI355X: "#e96a3a",
    MI450X: "#f18b45",
    MI455X: "#f6aa57",
  };
  const discoveredHardware = [...new Set(charts.flatMap((chart) => chart.points.map((point) => point.hardware)))].sort();
  const colorFor = (hardware) => hardwareColors[hardware.toUpperCase()] || fallbackColors[discoveredHardware.indexOf(hardware) % fallbackColors.length];
  const element = (name, attributes = {}) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  };
  const compact = (value) => {
    if (value >= 1000) return `${Math.round(value / 100) / 10}k`;
    return String(value ?? "?");
  };
  const valueLabel = (value, metric) => metric.unit === "s" ? value.toFixed(3) : value.toFixed(0);
  const traceKey = (point) => [point.hardware, point.input_tokens, point.output_tokens, point.prefix_cache_tokens || 0].join("|");
  const traceLabel = (point) => `${point.hardware} · ${compact(point.input_tokens)}/${compact(point.output_tokens)} · prefix ${compact(point.prefix_cache_tokens || 0)}`;

  const renderChart = (card, chartData, metricName) => {
    const metric = metrics[metricName];
    const points = chartData.points.filter((point) => point.metrics[metricName] !== undefined);
    const area = card.querySelector(".model-chart-area");
    const legend = card.querySelector(".model-chart-legend");
    const empty = card.querySelector(".model-chart-empty");
    area.replaceChildren();
    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip";
    area.appendChild(tooltip);
    legend.replaceChildren();
    if (!points.length) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    const traces = new Map();
    points.forEach((point) => {
      const key = traceKey(point);
      if (!traces.has(key)) traces.set(key, []);
      traces.get(key).push(point);
    });
    const width = 760;
    const height = 330;
    const margin = { top: 28, right: 22, bottom: 52, left: 68 };
    const values = points.map((point) => point.metrics[metricName]);
    const concurrencies = points.map((point) => point.concurrency);
    const xMin = Math.min(...concurrencies);
    const xMax = Math.max(...concurrencies);
    const dataMin = Math.min(...values);
    const dataMax = Math.max(...values);
    const dataRange = Math.max(dataMax - dataMin, dataMax * 0.1, 0.001);
    const yMin = metric.autoRange ? Math.max(0, dataMin - dataRange * 0.12) : 0;
    const yMax = metric.autoRange ? dataMax + dataRange * 0.12 : Math.max(dataMax * 1.1, 1);
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const xScale = (value) => margin.left + ((value - xMin) / Math.max(xMax - xMin, 1)) * plotWidth;
    const yScale = (value) => margin.top + plotHeight - ((value - yMin) / Math.max(yMax - yMin, 0.001)) * plotHeight;
    const svg = element("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${metric.label} for ${chartData.model}` });
    const yTitle = element("text", {
      x: 17,
      y: margin.top + plotHeight / 2,
      class: "chart-axis-title",
      transform: `rotate(-90 17 ${margin.top + plotHeight / 2})`,
    });
    yTitle.textContent = `${metric.label} (${metric.unit})`;
    svg.appendChild(yTitle);
    const xTitle = element("text", {
      x: margin.left + plotWidth / 2,
      y: height - 4,
      class: "chart-axis-title",
    });
    xTitle.textContent = "Concurrency (requests)";
    svg.appendChild(xTitle);

    for (let index = 0; index <= 4; index += 1) {
      const value = yMin + ((yMax - yMin) / 4) * index;
      const y = yScale(value);
      svg.appendChild(element("line", { x1: margin.left, x2: width - margin.right, y1: y, y2: y, class: "chart-grid" }));
      const tick = element("text", { x: margin.left - 10, y: y + 4, class: "chart-tick chart-tick-y" });
      tick.textContent = valueLabel(value, metric);
      svg.appendChild(tick);
    }
    [...new Set(concurrencies)].sort((left, right) => left - right).forEach((value) => {
      const tick = element("text", { x: xScale(value), y: height - 21, class: "chart-tick chart-tick-x" });
      tick.textContent = String(value);
      svg.appendChild(tick);
    });

    [...traces.entries()].forEach(([, tracePoints]) => {
      const sorted = tracePoints.sort((left, right) => left.concurrency - right.concurrency);
      const color = colorFor(sorted[0].hardware);
      if (sorted.length > 1) {
        svg.appendChild(element("polyline", {
          points: sorted.map((point) => `${xScale(point.concurrency)},${yScale(point.metrics[metricName])}`).join(" "),
          fill: "none",
          stroke: color,
          class: "chart-trace",
        }));
      }
      sorted.forEach((point) => {
        const value = point.metrics[metricName];
        const dot = element("circle", { cx: xScale(point.concurrency), cy: yScale(value), r: 6, fill: color, class: "chart-dot", tabindex: 0, role: "link" });
        const show = (event) => {
          tooltip.innerHTML = `<b>${chartData.model}</b><span>${point.hardware}${point.precision ? ` · ${point.precision}` : ""}</span><span>ISL ${point.input_tokens ?? "?"} · OSL ${point.output_tokens ?? "?"}</span><span>Prefix cache ${point.prefix_cache_tokens || 0} · Concurrency ${point.concurrency}</span><span>${metric.label}: ${valueLabel(value, metric)} ${metric.unit}</span><span>${point.completed_requests ?? "?"} completed · ${point.failed_requests ?? "?"} failed</span><small>Click for full run details</small>`;
          const bounds = area.getBoundingClientRect();
          const clientX = Number.isFinite(event.clientX) ? event.clientX : bounds.left + xScale(point.concurrency);
          const clientY = Number.isFinite(event.clientY) ? event.clientY : bounds.top + yScale(value);
          tooltip.style.left = `${Math.max(8, Math.min(clientX - bounds.left + 12, bounds.width - 290))}px`;
          tooltip.style.top = `${Math.max(clientY - bounds.top - 55, 8)}px`;
          tooltip.classList.add("visible");
        };
        const hide = () => tooltip.classList.remove("visible");
        const open = () => window.location.assign(`runs/${point.bundle_id}`);
        dot.addEventListener("mouseenter", show);
        dot.addEventListener("mousemove", show);
        dot.addEventListener("focus", show);
        dot.addEventListener("mouseleave", hide);
        dot.addEventListener("blur", hide);
        dot.addEventListener("click", open);
        dot.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") open();
        });
        svg.appendChild(dot);
      });
      const item = document.createElement("div");
      item.innerHTML = `<span style="background:${color}"></span><b>${traceLabel(sorted[0])}</b>`;
      legend.appendChild(item);
    });
    area.appendChild(svg);
  };

  const render = (metricName) => {
    const metric = metrics[metricName];
    heading.textContent = `${metric.label} by model`;
    buttons.forEach((button) => {
      const active = button.dataset.chartMetric === metricName;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    grid.replaceChildren();
    charts.forEach((chartData) => {
      const card = document.createElement("article");
      card.className = `model-chart-card${charts.length <= 2 ? " hero" : ""}`;
      card.innerHTML = `<div class="model-chart-title"><div><p>Model performance</p><h3>${chartData.model}</h3></div></div><div class="model-chart-area"><div class="chart-tooltip"></div></div><div class="model-chart-legend"></div><p class="model-chart-empty" hidden>No ${metric.label.toLowerCase()} results for this model.</p>`;
      grid.appendChild(card);
      renderChart(card, chartData, metricName);
    });
  };

  buttons.forEach((button) => button.addEventListener("click", () => render(button.dataset.chartMetric)));
  render("total_token_throughput_per_gpu");
})();
