document.querySelectorAll(".run-row[data-href]").forEach((row) => {
  row.tabIndex = 0;
  row.setAttribute("role", "link");
  const open = () => window.location.assign(row.dataset.href);
  row.addEventListener("click", open);
  row.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      open();
    }
  });
});
