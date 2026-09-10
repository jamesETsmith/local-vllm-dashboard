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
  const traceSymbols = ["circle", "square", "diamond", "triangle", "triangle-down", "hexagon", "pentagon", "star"];
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
  const valueLabel = (value, metric) => metric.unit === "s" ? value.toFixed(3) : value.toFixed(0);
  const ignoredTraceFields = new Set(["name", "max_concurrency", "num_prompts", "completed", "failed"]);
  const normalizedConfiguration = (value) => {
    if (Array.isArray(value)) return value.map(normalizedConfiguration);
    if (!value || typeof value !== "object") return value;
    return Object.fromEntries(
      Object.keys(value)
        .filter((key) => !ignoredTraceFields.has(key))
        .sort()
        .map((key) => [key, normalizedConfiguration(value[key])]),
    );
  };
  const traceKey = (point) => JSON.stringify({
    hardware: point.hardware,
    precision: point.precision,
    configuration: normalizedConfiguration(point.configuration),
  });
  const traceDate = (point) => point.completed_at.slice(0, 10);
  const polygonPoints = (sides, x, y, radius, rotation = -Math.PI / 2) => Array.from(
    { length: sides },
    (_, index) => {
      const angle = rotation + (index * Math.PI * 2) / sides;
      return `${x + Math.cos(angle) * radius},${y + Math.sin(angle) * radius}`;
    },
  ).join(" ");
  const starPoints = (x, y, radius) => Array.from(
    { length: 10 },
    (_, index) => {
      const angle = -Math.PI / 2 + (index * Math.PI) / 5;
      const pointRadius = index % 2 ? radius * 0.45 : radius;
      return `${x + Math.cos(angle) * pointRadius},${y + Math.sin(angle) * pointRadius}`;
    },
  ).join(" ");
  const traceSymbol = (name, x, y, color, radius = 6) => {
    const attributes = { fill: color, class: "chart-point-symbol" };
    if (name === "circle") return element("circle", { cx: x, cy: y, r: radius, ...attributes });
    if (name === "square") return element("rect", { x: x - radius, y: y - radius, width: radius * 2, height: radius * 2, rx: 1, ...attributes });
    if (name === "diamond") return element("polygon", { points: polygonPoints(4, x, y, radius * 1.15, 0), ...attributes });
    if (name === "triangle-down") return element("polygon", { points: polygonPoints(3, x, y, radius * 1.2, Math.PI / 2), ...attributes });
    if (name === "hexagon") return element("polygon", { points: polygonPoints(6, x, y, radius * 1.1, 0), ...attributes });
    if (name === "pentagon") return element("polygon", { points: polygonPoints(5, x, y, radius * 1.15), ...attributes });
    if (name === "star") return element("polygon", { points: starPoints(x, y, radius * 1.3), ...attributes });
    return element("polygon", { points: polygonPoints(3, x, y, radius * 1.2), ...attributes });
  };
  const niceStep = (range, targetCount, integer = false) => {
    const rough = Math.max(range / targetCount, Number.EPSILON);
    const magnitude = 10 ** Math.floor(Math.log10(rough));
    const normalized = rough / magnitude;
    const multiplier = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
    return Math.max(integer ? 1 : Number.EPSILON, multiplier * magnitude);
  };
  const tickValues = (minimum, maximum, targetCount, integer = false) => {
    const step = niceStep(maximum - minimum, targetCount, integer);
    const first = Math.ceil(minimum / step) * step;
    const values = [];
    for (let value = first; value <= maximum + step * 0.001; value += step) {
      values.push(Number(value.toPrecision(12)));
    }
    return values;
  };
  const clampDomain = (minimum, maximum, fullDomain) => {
    if (minimum < fullDomain[0]) {
      maximum += fullDomain[0] - minimum;
      minimum = fullDomain[0];
    }
    if (maximum > fullDomain[1]) {
      minimum -= maximum - fullDomain[1];
      maximum = fullDomain[1];
    }
    return [Math.max(minimum, fullDomain[0]), Math.min(maximum, fullDomain[1])];
  };
  const zoomDomain = (domain, fullDomain, scale, anchor = (domain[0] + domain[1]) / 2) => {
    const fullRange = fullDomain[1] - fullDomain[0];
    const range = Math.max(Math.min((domain[1] - domain[0]) * scale, fullRange), fullRange / 64);
    const anchorRatio = (anchor - domain[0]) / Math.max(domain[1] - domain[0], Number.EPSILON);
    const minimum = anchor - range * anchorRatio;
    return clampDomain(minimum, minimum + range, fullDomain);
  };
  const panDomain = (domain, fullDomain, change) => clampDomain(
    domain[0] + change,
    domain[1] + change,
    fullDomain,
  );

  const renderChart = (card, chartData, metricName) => {
    const metric = metrics[metricName];
    const points = chartData.points.filter((point) => point.metrics[metricName] !== undefined);
    const area = card.querySelector(".model-chart-area");
    const empty = card.querySelector(".model-chart-empty");
    const zoomIn = card.querySelector("[data-chart-zoom-in]");
    const zoomOut = card.querySelector("[data-chart-zoom-out]");
    const zoomReset = card.querySelector("[data-chart-zoom-reset]");
    const legend = card.querySelector(".model-chart-legend");
    area.replaceChildren();
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
    const traceEntries = [...traces.entries()];
    traceEntries.forEach(([, tracePoints], index) => {
      const point = tracePoints[0];
      const color = colorFor(point.hardware);
      const link = document.createElement("a");
      link.href = `runs/${point.bundle_id}`;
      link.title = `${point.hardware} trace from ${traceDate(point)}`;
      const icon = element("svg", { viewBox: "0 0 18 18", "aria-hidden": "true" });
      icon.appendChild(traceSymbol(traceSymbols[index % traceSymbols.length], 9, 9, color, 5));
      const date = document.createElement("span");
      date.textContent = traceDate(point);
      link.append(icon, date);
      legend.appendChild(link);
    });
    const width = 760;
    const height = 330;
    const margin = { top: 28, right: 22, bottom: 52, left: 68 };
    const values = points.map((point) => point.metrics[metricName]);
    const concurrencies = points.map((point) => point.concurrency);
    const rawXMin = Math.min(...concurrencies);
    const rawXMax = Math.max(...concurrencies);
    const xPadding = rawXMin === rawXMax ? Math.max(Math.abs(rawXMin) * 0.1, 1) : 0;
    const dataMin = Math.min(...values);
    const dataMax = Math.max(...values);
    const dataRange = Math.max(dataMax - dataMin, dataMax * 0.1, 0.001);
    const fullXDomain = [rawXMin - xPadding, rawXMax + xPadding];
    const fullYDomain = [
      metric.autoRange ? Math.max(0, dataMin - dataRange * 0.12) : 0,
      metric.autoRange ? dataMax + dataRange * 0.12 : Math.max(dataMax * 1.1, 1),
    ];
    let xDomain = [...fullXDomain];
    let yDomain = [...fullYDomain];
    let suppressPointClick = false;
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip";
    area.appendChild(tooltip);

    const draw = () => {
      area.querySelector("svg")?.remove();
      tooltip.classList.remove("visible");
      const [xMin, xMax] = xDomain;
      const [yMin, yMax] = yDomain;
      const xScale = (value) => margin.left + ((value - xMin) / Math.max(xMax - xMin, 0.001)) * plotWidth;
      const yScale = (value) => margin.top + plotHeight - ((value - yMin) / Math.max(yMax - yMin, 0.001)) * plotHeight;
      const svg = element("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${metric.label} for ${chartData.model}` });
      const clipId = `chart-clip-${Math.random().toString(36).slice(2)}`;
      const definitions = element("defs");
      const clipPath = element("clipPath", { id: clipId });
      clipPath.appendChild(element("rect", { x: margin.left, y: margin.top, width: plotWidth, height: plotHeight }));
      definitions.appendChild(clipPath);
      svg.appendChild(definitions);
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

      tickValues(yMin, yMax, 5).forEach((value) => {
        const y = yScale(value);
        svg.appendChild(element("line", { x1: margin.left, x2: width - margin.right, y1: y, y2: y, class: "chart-grid" }));
        const tick = element("text", { x: margin.left - 10, y: y + 4, class: "chart-tick chart-tick-y" });
        tick.textContent = valueLabel(value, metric);
        svg.appendChild(tick);
      });
      tickValues(xMin, xMax, 7, true).forEach((value) => {
        const tick = element("text", { x: xScale(value), y: height - 21, class: "chart-tick chart-tick-x" });
        tick.textContent = String(value);
        svg.appendChild(tick);
      });

      const plot = element("g", { "clip-path": `url(#${clipId})` });
      traceEntries.forEach(([, tracePoints], traceIndex) => {
        const sorted = [...tracePoints].sort((left, right) => left.concurrency - right.concurrency);
        const color = colorFor(sorted[0].hardware);
        const symbol = traceSymbols[traceIndex % traceSymbols.length];
        if (sorted.length > 1) {
          plot.appendChild(element("polyline", {
            points: sorted.map((point) => `${xScale(point.concurrency)},${yScale(point.metrics[metricName])}`).join(" "),
            fill: "none",
            stroke: color,
            class: "chart-trace",
          }));
        }
        sorted.forEach((point) => {
          const value = point.metrics[metricName];
          const dot = element("g", { class: "chart-point-link", tabindex: 0, role: "link" });
          dot.appendChild(traceSymbol(symbol, xScale(point.concurrency), yScale(value), color));
          dot.appendChild(element("circle", { cx: xScale(point.concurrency), cy: yScale(value), r: 10, class: "chart-point-hit" }));
          const show = (event) => {
            const available = (value) => value ?? "unknown";
            const configurationItems = [
              `TP: ${available(point.tensor_parallel_size)}`,
              `EP: ${point.server_settings_available ? point.expert_parallel ? "enabled" : "disabled" : "unknown"}`,
              `Spec decode: ${point.server_settings_available ? point.speculative_decode || "none" : "unknown"}`,
              `DCP: ${available(point.decode_context_parallel_size)}`,
              `KV cache offload: ${point.server_settings_available ? point.kv_cache_offload || "none" : "unknown"}`,
            ];
            tooltip.innerHTML = `<b>${chartData.model}</b><span>${point.hardware}${point.precision ? ` · ${point.precision}` : ""}</span><span>ISL ${point.input_tokens ?? "?"} · OSL ${point.output_tokens ?? "?"}</span><span>Prefix cache ${point.prefix_cache_tokens || 0} · Concurrency ${point.concurrency}</span><ul>${configurationItems.map((item) => `<li>${item}</li>`).join("")}</ul><span>${metric.label}: ${valueLabel(value, metric)} ${metric.unit}</span><span>${point.completed_requests ?? "?"} completed · ${point.failed_requests ?? "?"} failed</span><small>Click for full run details</small>`;
            const bounds = area.getBoundingClientRect();
            const clientX = Number.isFinite(event.clientX) ? event.clientX : bounds.left + xScale(point.concurrency);
            const clientY = Number.isFinite(event.clientY) ? event.clientY : bounds.top + yScale(value);
            const tooltipWidth = tooltip.offsetWidth;
            const tooltipHeight = tooltip.offsetHeight;
            const left = Math.max(8, Math.min(clientX + 12, window.innerWidth - tooltipWidth - 8));
            const preferredTop = clientY - tooltipHeight - 12;
            const top = preferredTop >= 8 ? preferredTop : clientY + 12;
            tooltip.style.left = `${left}px`;
            tooltip.style.top = `${Math.max(8, Math.min(top, window.innerHeight - tooltipHeight - 8))}px`;
            tooltip.classList.add("visible");
          };
          const hide = () => tooltip.classList.remove("visible");
          const open = () => {
            if (suppressPointClick) {
              suppressPointClick = false;
              return;
            }
            window.location.assign(`runs/${point.bundle_id}`);
          };
          dot.addEventListener("mouseenter", show);
          dot.addEventListener("mousemove", show);
          dot.addEventListener("focus", show);
          dot.addEventListener("mouseleave", hide);
          dot.addEventListener("blur", hide);
          dot.addEventListener("click", open);
          dot.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") open();
          });
          plot.appendChild(dot);
        });
      });
      svg.appendChild(plot);
      svg.classList.toggle("chart-pannable", xDomain[0] !== fullXDomain[0] || xDomain[1] !== fullXDomain[1]);
      svg.addEventListener("mousedown", (event) => {
        if (event.button !== 0 || (xDomain[0] === fullXDomain[0] && xDomain[1] === fullXDomain[1])) return;
        event.preventDefault();
        tooltip.classList.remove("visible");
        svg.classList.add("chart-panning");
        const startX = event.clientX;
        const startY = event.clientY;
        const startXDomain = [...xDomain];
        const startYDomain = [...yDomain];
        const bounds = svg.getBoundingClientRect();
        const move = (moveEvent) => {
          const movedX = moveEvent.clientX - startX;
          const movedY = moveEvent.clientY - startY;
          if (Math.hypot(movedX, movedY) < 3) return;
          suppressPointClick = true;
          const xChange = -(movedX / bounds.width) * (width / plotWidth) * (startXDomain[1] - startXDomain[0]);
          const yChange = (movedY / bounds.height) * (height / plotHeight) * (startYDomain[1] - startYDomain[0]);
          xDomain = panDomain(startXDomain, fullXDomain, xChange);
          yDomain = panDomain(startYDomain, fullYDomain, yChange);
          draw();
        };
        const stop = () => {
          window.removeEventListener("mousemove", move);
          window.removeEventListener("mouseup", stop);
          window.setTimeout(() => {
            suppressPointClick = false;
          }, 0);
        };
        window.addEventListener("mousemove", move);
        window.addEventListener("mouseup", stop);
      });
      svg.addEventListener("wheel", (event) => {
        event.preventDefault();
        const bounds = svg.getBoundingClientRect();
        const svgX = ((event.clientX - bounds.left) / bounds.width) * width;
        const svgY = ((event.clientY - bounds.top) / bounds.height) * height;
        if (svgX < margin.left || svgX > width - margin.right || svgY < margin.top || svgY > height - margin.bottom) return;
        const xAnchor = xDomain[0] + ((svgX - margin.left) / plotWidth) * (xDomain[1] - xDomain[0]);
        const yAnchor = yDomain[1] - ((svgY - margin.top) / plotHeight) * (yDomain[1] - yDomain[0]);
        const scale = event.deltaY < 0 ? 0.82 : 1 / 0.82;
        xDomain = zoomDomain(xDomain, fullXDomain, scale, xAnchor);
        yDomain = zoomDomain(yDomain, fullYDomain, scale, yAnchor);
        draw();
      }, { passive: false });
      area.appendChild(svg);
      const atFullZoom = xDomain[0] === fullXDomain[0] && xDomain[1] === fullXDomain[1];
      const atMaximumZoom = xDomain[1] - xDomain[0] <= (fullXDomain[1] - fullXDomain[0]) / 64;
      zoomIn.disabled = atMaximumZoom;
      zoomOut.disabled = atFullZoom;
      zoomReset.disabled = atFullZoom;
    };

    zoomIn.addEventListener("click", () => {
      xDomain = zoomDomain(xDomain, fullXDomain, 0.65);
      yDomain = zoomDomain(yDomain, fullYDomain, 0.65);
      draw();
    });
    zoomOut.addEventListener("click", () => {
      xDomain = zoomDomain(xDomain, fullXDomain, 1 / 0.65);
      yDomain = zoomDomain(yDomain, fullYDomain, 1 / 0.65);
      draw();
    });
    zoomReset.addEventListener("click", () => {
      xDomain = [...fullXDomain];
      yDomain = [...fullYDomain];
      draw();
    });
    draw();
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
      card.innerHTML = `<div class="model-chart-title"><div><p>Model performance</p><h3>${chartData.model}</h3></div><div class="chart-zoom-controls" role="group" aria-label="Zoom ${chartData.model} plot"><button type="button" data-chart-zoom-in aria-label="Zoom in">+</button><button type="button" data-chart-zoom-out aria-label="Zoom out">−</button><button type="button" data-chart-zoom-reset>Reset</button></div></div><div class="model-chart-area"></div><p class="model-chart-empty" hidden>No ${metric.label.toLowerCase()} results for this model.</p><div class="model-chart-legend" aria-label="Benchmark traces"></div>`;
      grid.appendChild(card);
      renderChart(card, chartData, metricName);
    });
  };

  buttons.forEach((button) => button.addEventListener("click", () => render(button.dataset.chartMetric)));
  render("total_token_throughput_per_gpu");
})();
