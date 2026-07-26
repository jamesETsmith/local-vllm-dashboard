(() => {
  const payload = document.getElementById("performance-chart-data");
  const chart = document.getElementById("performance-chart");
  const legend = document.getElementById("performance-chart-legend");
  const tooltip = document.getElementById("performance-chart-tooltip");
  if (!payload || !chart || !legend || !tooltip) return;

  const series = JSON.parse(payload.textContent || "[]");
  const colors = ["#7559f2", "#3bbf8a", "#ff9f43", "#e5576d", "#3f8cff", "#9a63d8"];
  const width = 920;
  const height = 360;
  const margin = { top: 24, right: 26, bottom: 44, left: 72 };
  const points = series.flatMap((trace) => trace.points);
  if (!points.length) return;

  const xValues = points.map((point) => point.concurrency);
  const yValues = points.map((point) => point.throughput);
  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);
  const yMax = Math.max(...yValues) * 1.08;
  const xScale = (value) => margin.left + ((value - xMin) / Math.max(xMax - xMin, 1)) * (width - margin.left - margin.right);
  const yScale = (value) => height - margin.bottom - (value / Math.max(yMax, 1)) * (height - margin.top - margin.bottom);
  const element = (name, attributes = {}) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  };
  const hideTooltip = () => tooltip.classList.remove("visible");
  const showTooltip = (event, trace, point) => {
    const completed = point.completed_requests ?? "?";
    const failed = point.failed_requests ?? "?";
    tooltip.innerHTML = `<b>${trace.label}</b><span>${point.model}</span><span>${point.hardware}${point.precision ? ` · ${point.precision}` : ""}</span><span>Concurrency ${point.concurrency} · ${point.throughput.toFixed(2)} token/s/GPU</span><span>${completed} completed · ${failed} failed</span><small>Click for the full run configuration</small>`;
    const bounds = chart.parentElement.getBoundingClientRect();
    tooltip.style.left = `${Math.min(event.clientX - bounds.left + 14, bounds.width - 290)}px`;
    tooltip.style.top = `${Math.max(event.clientY - bounds.top - 45, 8)}px`;
    tooltip.classList.add("visible");
  };

  chart.setAttribute("viewBox", `0 0 ${width} ${height}`);
  chart.setAttribute("preserveAspectRatio", "xMidYMid meet");
  chart.addEventListener("mouseleave", hideTooltip);

  for (let index = 0; index <= 4; index += 1) {
    const value = (yMax / 4) * index;
    const y = yScale(value);
    chart.appendChild(element("line", { x1: margin.left, x2: width - margin.right, y1: y, y2: y, class: "chart-grid" }));
    const label = element("text", { x: margin.left - 12, y: y + 4, class: "chart-tick chart-tick-y" });
    label.textContent = value.toFixed(0);
    chart.appendChild(label);
  }

  [...new Set(xValues)].sort((a, b) => a - b).forEach((value) => {
    const x = xScale(value);
    const label = element("text", { x, y: height - 16, class: "chart-tick chart-tick-x" });
    label.textContent = String(value);
    chart.appendChild(label);
  });

  series.forEach((trace, index) => {
    const color = colors[index % colors.length];
    trace.points.forEach((point) => {
      const dot = element("circle", { cx: xScale(point.concurrency), cy: yScale(point.throughput), r: 7, fill: color, class: "chart-dot", tabindex: 0, role: "link" });
      const open = () => window.location.assign(`runs/${point.bundle_id}`);
      dot.addEventListener("mouseenter", (event) => showTooltip(event, trace, point));
      dot.addEventListener("mousemove", (event) => showTooltip(event, trace, point));
      dot.addEventListener("focus", (event) => showTooltip(event, trace, point));
      dot.addEventListener("mouseleave", hideTooltip);
      dot.addEventListener("blur", hideTooltip);
      dot.addEventListener("click", open);
      dot.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") open();
      });
      chart.appendChild(dot);
    });
    const item = document.createElement("div");
    item.innerHTML = `<span style="background:${color}"></span><b>${trace.label}</b>`;
    legend.appendChild(item);
  });
})();
