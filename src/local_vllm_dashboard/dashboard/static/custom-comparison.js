(() => {
  const payload = document.getElementById("comparison-chart-data");
  const area = document.getElementById("comparison-chart-area");
  const legend = document.getElementById("comparison-chart-legend");
  const heading = document.getElementById("comparison-chart-heading");
  const unit = document.getElementById("comparison-chart-unit");
  const count = document.getElementById("comparison-selection-count");
  const search = document.getElementById("comparison-search");
  const filterCount = document.getElementById("comparison-filter-count");
  const filterEmpty = document.getElementById("comparison-filter-empty");
  const preview = document.getElementById("comparison-result-preview");
  const previewTitle = document.getElementById("comparison-preview-title");
  const previewSummary = document.getElementById("comparison-preview-summary");
  const previewConfig = document.getElementById("comparison-preview-config");
  const previewClose = document.getElementById("comparison-preview-close");
  const selectAll = document.getElementById("comparison-select-all");
  const clear = document.getElementById("comparison-clear");
  const buttons = [...document.querySelectorAll("[data-comparison-metric]")];
  const rows = [...document.querySelectorAll("[data-comparison-result]")];
  if (!payload || !area || !legend || !heading || !unit || !count || !search || !filterCount || !filterEmpty || !preview || !previewTitle || !previewSummary || !previewConfig || !previewClose || !selectAll || !clear || !buttons.length || !rows.length) return;

  const charts = JSON.parse(payload.textContent || "[]");
  const metrics = {
    total_token_throughput_per_gpu: { label: "Total token throughput", unit: "token/s/GPU" },
    output_token_throughput_per_gpu: { label: "Output token throughput", unit: "token/s/GPU" },
    mean_ttft: { label: "TTFT", unit: "s" },
    mean_tpot: { label: "TPOT", unit: "s" },
  };
  const colors = ["#7559f2", "#3f8cff", "#00a183", "#e96a3a", "#d14da5", "#9a63d8", "#1b7f3a", "#bd3828"];
  let activeMetric = "total_token_throughput_per_gpu";

  const element = (name, attributes = {}) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  };
  const compact = (value) => value >= 1000 ? `${Math.round(value / 100) / 10}k` : String(value ?? "?");
  const valueLabel = (value, metric) => metric.unit === "s" ? value.toFixed(3) : value.toFixed(0);
  const resultFor = (row) => {
    const [chartIndex, pointIndex] = row.dataset.comparisonResult.split(":").map(Number);
    return { model: charts[chartIndex].model, point: charts[chartIndex].points[pointIndex] };
  };
  const selectedRows = () => rows.filter((row) => row.querySelector("input").checked);
  const resultLabel = ({ model, point }) => `${model} · ${point.hardware} · ${compact(point.input_tokens)}/${compact(point.output_tokens)} · C${point.concurrency}`;
  let previewTimer;
  const hidePreview = () => {
    clearTimeout(previewTimer);
    preview.hidden = true;
  };
  const showPreview = (row) => {
    clearTimeout(previewTimer);
    const { model, point } = resultFor(row);
    previewTitle.textContent = model;
    previewSummary.textContent = `${point.hardware}${point.precision ? ` · ${point.precision}` : ""} · completed ${point.completed_at}`;
    previewConfig.textContent = JSON.stringify(point.configuration, null, 2);
    const pickerBounds = row.closest(".comparison-picker").getBoundingClientRect();
    const rowBounds = row.getBoundingClientRect();
    preview.style.top = `${Math.max(10, Math.min(rowBounds.top - pickerBounds.top, pickerBounds.height - 360))}px`;
    preview.hidden = false;
  };
  const queuePreview = (row) => {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(() => showPreview(row), 180);
  };

  const render = () => {
    const metric = metrics[activeMetric];
    const selected = selectedRows().map(resultFor).filter(({ point }) => point.metrics[activeMetric] !== undefined);
    count.textContent = String(selectedRows().length);
    heading.textContent = metric.label;
    unit.textContent = metric.unit;
    buttons.forEach((button) => {
      const active = button.dataset.comparisonMetric === activeMetric;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    area.replaceChildren();
    legend.replaceChildren();
    if (!selected.length) {
      const empty = document.createElement("div");
      empty.className = "comparison-chart-empty";
      empty.innerHTML = `<h3>Select results to compare</h3><p>Choose one or more results on the left that include ${metric.label.toLowerCase()}.</p>`;
      area.appendChild(empty);
      return;
    }

    const width = 920;
    const height = 460;
    const margin = { top: 28, right: 24, bottom: 150, left: 82 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const values = selected.map(({ point }) => point.metrics[activeMetric]);
    const yMax = Math.max(...values) * 1.12 || 1;
    const yScale = (value) => margin.top + plotHeight - (value / yMax) * plotHeight;
    const slotWidth = plotWidth / selected.length;
    const barWidth = Math.min(74, slotWidth * 0.62);
    const svg = element("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${metric.label} comparison` });
    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip";
    area.appendChild(tooltip);

    for (let index = 0; index <= 4; index += 1) {
      const value = (yMax / 4) * index;
      const y = yScale(value);
      svg.appendChild(element("line", { x1: margin.left, x2: width - margin.right, y1: y, y2: y, class: "chart-grid" }));
      const tick = element("text", { x: margin.left - 10, y: y + 4, class: "chart-tick chart-tick-y" });
      tick.textContent = valueLabel(value, metric);
      svg.appendChild(tick);
    }
    const yTitle = element("text", { x: 19, y: margin.top + plotHeight / 2, class: "chart-axis-title", transform: `rotate(-90 19 ${margin.top + plotHeight / 2})` });
    yTitle.textContent = `${metric.label} (${metric.unit})`;
    svg.appendChild(yTitle);

    selected.forEach((result, index) => {
      const { point } = result;
      const value = point.metrics[activeMetric];
      const x = margin.left + index * slotWidth + (slotWidth - barWidth) / 2;
      const y = yScale(value);
      const color = colors[index % colors.length];
      const bar = element("rect", { x, y, width: barWidth, height: margin.top + plotHeight - y, rx: 7, fill: color, class: "comparison-bar", tabindex: 0, role: "link" });
      const show = () => {
        tooltip.innerHTML = `<b>${result.model}</b><span>${point.hardware}${point.precision ? ` · ${point.precision}` : ""}</span><span>ISL ${point.input_tokens ?? "?"} · OSL ${point.output_tokens ?? "?"} · prefix ${point.prefix_cache_tokens || 0}</span><span>Concurrency ${point.concurrency}</span><span>${metric.label}: ${valueLabel(value, metric)} ${metric.unit}</span><small>Click for full run details</small>`;
        tooltip.style.left = `${Math.max(8, Math.min(((index + 0.5) * area.clientWidth) / selected.length, area.clientWidth - 290))}px`;
        tooltip.style.top = "42px";
        tooltip.classList.add("visible");
      };
      const hide = () => tooltip.classList.remove("visible");
      const open = () => window.location.assign(`runs/${point.bundle_id}`);
      bar.addEventListener("mouseenter", show);
      bar.addEventListener("focus", show);
      bar.addEventListener("mouseleave", hide);
      bar.addEventListener("blur", hide);
      bar.addEventListener("click", open);
      bar.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") open();
      });
      svg.appendChild(bar);
      const valueText = element("text", { x: x + barWidth / 2, y: y - 8, class: "comparison-value" });
      valueText.textContent = valueLabel(value, metric);
      svg.appendChild(valueText);
      const label = element("text", { x: x + barWidth / 2, y: margin.top + plotHeight + 18, class: "comparison-label", transform: `rotate(35 ${x + barWidth / 2} ${margin.top + plotHeight + 18})` });
      label.textContent = `${point.hardware} · C${point.concurrency}`;
      svg.appendChild(label);

      const item = document.createElement("div");
      item.innerHTML = `<span style="background:${color}"></span><b>${resultLabel(result)}</b>`;
      legend.appendChild(item);
    });
    area.appendChild(svg);
  };

  rows.forEach((row, index) => {
    const checkbox = row.querySelector("input");
    checkbox.checked = index < Math.min(rows.length, 4);
    checkbox.addEventListener("change", render);
    row.addEventListener("mouseenter", () => queuePreview(row));
    row.addEventListener("mouseleave", () => {
      previewTimer = setTimeout(hidePreview, 120);
    });
    row.addEventListener("focusin", () => showPreview(row));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Escape") hidePreview();
    });
  });
  preview.addEventListener("mouseenter", () => clearTimeout(previewTimer));
  preview.addEventListener("mouseleave", hidePreview);
  previewClose.addEventListener("click", hidePreview);
  buttons.forEach((button) => button.addEventListener("click", () => {
    activeMetric = button.dataset.comparisonMetric;
    render();
  }));
  const filterRows = () => {
    const terms = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    let matches = 0;
    rows.forEach((row) => {
      const searchable = `${row.dataset.searchBase || ""} ${row.dataset.searchConfig || ""}`.toLowerCase();
      const visible = terms.every((term) => searchable.includes(term));
      row.classList.toggle("comparison-result-filtered", !visible);
      row.setAttribute("aria-hidden", String(!visible));
      if (visible) matches += 1;
    });
    filterCount.textContent = String(matches);
    filterEmpty.hidden = matches !== 0;
  };
  search.addEventListener("input", filterRows);
  selectAll.addEventListener("click", () => {
    rows.filter((row) => !row.classList.contains("comparison-result-filtered")).forEach((row) => { row.querySelector("input").checked = true; });
    render();
  });
  clear.addEventListener("click", () => {
    rows.forEach((row) => { row.querySelector("input").checked = false; });
    render();
  });
  filterRows();
  render();
})();
