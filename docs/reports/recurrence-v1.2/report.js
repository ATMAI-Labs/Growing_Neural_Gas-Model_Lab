/* Every plotted value comes from the frozen result embedded by the builder. */
(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("report-data").textContent);
  const seedControl = document.getElementById("seed-select");
  const metricControl = document.getElementById("metric-select");
  const svg = document.getElementById("timeline-chart");
  const ns = "http://www.w3.org/2000/svg";
  const styles = [
    {stroke: "#f2f2f0", dash: ""}, {stroke: "#c9c9c6", dash: "12 7"},
    {stroke: "#a3a3a0", dash: "3 5"}, {stroke: "#737370", dash: "8 5 2 5"}
  ];
  const names = ["Representation error (QE)", "Topographic error (TE)", "Connected components"];
  const definitions = ["Pre-update mean squared distance to the nearest node.", "Fraction of nearest-node pairs without an edge.", "Connected graph components at window end."];
  function element(tag, attrs, text) {
    const node = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function label(x, y, text, anchor = "start", size = 15) {
    return element("text", {x, y, fill: "#a3a3a0", "font-family": "IBM Plex Mono, monospace", "font-size": size, "text-anchor": anchor}, text);
  }
  function draw() {
    const seed = seedControl.value, metric = Number(metricControl.value);
    const selected = data.series[seed];
    const seedName = seed === "all" ? `Mean of ${data.n} seeds` : `Seed ${seed.padStart(2, "0")}`;
    const values = data.arms.flatMap(arm => selected[arm].map(row => row[metric]));
    const logarithmic = metric === 0;
    const transform = value => logarithmic ? Math.log10(value) : value;
    const min = logarithmic ? Math.floor(Math.log10(Math.min(...values))) : 0;
    const observedMax = Math.max(...values);
    const max = logarithmic ? Math.ceil(Math.log10(observedMax)) : metric === 2 ? Math.max(2, Math.ceil(observedMax)) : Math.ceil(observedMax * 20) / 20 || .05;
    const left = 86, right = 1070, top = 56, bottom = 360;
    const x = t => left + t / (data.phase * 2) * (right - left);
    const y = value => bottom - (transform(value) - min) / (max - min) * (bottom - top);
    svg.replaceChildren(element("title", {id: "chart-title"}, `${names[metric]}, ${seedName}`),
      element("desc", {id: "chart-desc"}, `Four experimental arms. A returns at sample ${data.phase}. ${logarithmic ? "Logarithmic" : "Linear"} vertical axis. Exact plotted values are available in the table below.`));
    svg.append(label(left, 22, "INTERVENTION"), label(x(data.phase) + 16, 22, "RETURN A"));
    const ticks = logarithmic ? Array.from({length: max - min + 1}, (_, i) => 10 ** (min + i)) : Array.from({length: 5}, (_, i) => max * i / 4);
    ticks.forEach(value => {
      const at = y(value);
      svg.append(element("line", {x1:left, x2:right, y1:at, y2:at, stroke:"#262626"}),
        label(left - 14, at + 5, logarithmic ? value.toPrecision(1) : value.toFixed(metric === 2 ? 1 : 4).replace(/0+$/, "").replace(/\.$/, ""), "end"));
    });
    svg.append(element("line", {x1:x(data.phase), x2:x(data.phase), y1:top-12, y2:bottom, stroke:"#737370", "stroke-dasharray":"4 6"}));
    for (let i = 0; i <= 4; i++) {
      const time = data.phase * i / 2;
      svg.append(label(x(time), bottom + 30, time.toLocaleString("en-US"), "middle"));
    }
    svg.append(label((left + right) / 2, bottom + 68, "Samples after warmup", "middle"));
    // Reverse draw order keeps the primary arm visible where curves coincide.
    [...data.arms.keys()].reverse().forEach(index => {
      const arm = data.arms[index];
      const points = selected[arm].map((row, i) => [x((i + 1) * data.window), y(row[metric])]);
      const path = points.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(3)},${py.toFixed(3)}`).join(" ");
      const line = element("path", {d:path, fill:"none", stroke:styles[index].stroke, "stroke-width":index === 0 ? 2.5 : 2, "stroke-dasharray":styles[index].dash, "stroke-linejoin":"round"});
      line.append(element("title", {}, data.labels[index])); svg.append(line);
    });
    document.getElementById("chart-status").textContent = `${seedName} / ${data.window}-sample windows`;
    document.getElementById("chart-caption").textContent = `${names[metric]}: ${seedName.toLowerCase()}. ${definitions[metric]} ${logarithmic ? "Logarithmic vertical axis." : "Linear vertical axis."} A returns at sample ${data.phase.toLocaleString("en-US")}. Each point is one recorded window; connecting lines are visual guides.`;
    document.getElementById("values-caption").textContent = `${names[metric]}: ${seedName.toLowerCase()}`;
    const table = document.getElementById("chart-values"); table.replaceChildren();
    selected[data.arms[0]].forEach((_, i) => {
      const time = (i + 1) * data.window;
      const values = [time <= data.phase ? "Intervention" : "Return A", (time <= data.phase ? time : time-data.phase).toLocaleString("en-US"), ...data.arms.map(arm => selected[arm][i][metric].toPrecision(7))];
      const row = document.createElement("tr");
      values.forEach(value => {const cell = document.createElement("td");cell.textContent = value;row.append(cell);}); table.append(row);
    });
  }
  seedControl.addEventListener("change", draw);
  metricControl.addEventListener("change", draw);
  draw();
})();
