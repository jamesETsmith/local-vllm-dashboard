(() => {
  const search = document.getElementById("raw-data-search");
  const filterCount = document.getElementById("raw-data-filter-count");
  const filterEmpty = document.getElementById("raw-data-filter-empty");
  const table = document.querySelector(".dataframe-table");
  const rows = [...document.querySelectorAll(".dataframe-table tbody tr")];
  if (!search || !filterCount || !filterEmpty || !table || !rows.length) return;

  const filterRows = () => {
    const terms = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    let matches = 0;
    rows.forEach((row) => {
      const searchable = `${row.textContent || ""} ${row.dataset.searchBase || ""} ${row.dataset.searchConfig || ""}`.toLowerCase();
      const visible = terms.every((term) => searchable.includes(term));
      row.hidden = !visible;
      row.setAttribute("aria-hidden", String(!visible));
      if (visible) matches += 1;
    });
    filterCount.textContent = String(matches);
    filterEmpty.hidden = matches !== 0;
    table.hidden = matches === 0;
  };

  search.addEventListener("input", filterRows);
  filterRows();
})();
