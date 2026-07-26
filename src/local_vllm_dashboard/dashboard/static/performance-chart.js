(() => {
  const payload = document.getElementById("performance-chart-data");
  const chart = document.getElementById("performance-chart");
  const legend = document.getElementById("performance-chart-legend");
  if (!payload || !chart || !legend) return;

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

  chart.setAttribute("viewBox", `0 0 ${width} ${height}`);
  chart.setAttribute("preserveAspectRatio", "xMidYMid meet");

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
    const coordinates = trace.points.map((point) => `${xScale(point.concurrency)},${yScale(point.throughput)}`).join(" ");
    chart.appendChild(element("polyline", { points: coordinates, fill: "none", stroke: color, class: "chart-line" }));
    trace.points.forEach((point) => {
      const dot = element("circle", { cx: xScale(point.concurrency), cy: yScale(point.throughput), r: 5, fill: color, class: "chart-dot" });
      const title = element("title");
      title.textContent = `${trace.label}\nConcurrency ${point.concurrency}\n${point.throughput.toFixed(2)} token/s/GPU`;
      dot.appendChild(title);
      chart.appendChild(dot);
    });
    const item = document.createElement("div");
    item.innerHTML = `<span style="background:${color}"></span><b>${trace.label}</b>`;
    legend.appendChild(item);
  });
})();
