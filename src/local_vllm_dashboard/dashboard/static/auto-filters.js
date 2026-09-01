const filterForm = document.querySelector("form.filters");

if (filterForm) {
  const submitFilters = () => filterForm.requestSubmit();

  filterForm.querySelectorAll("select").forEach((select) => {
    select.addEventListener("change", submitFilters);
  });

  filterForm.querySelectorAll(".filter-dropdown").forEach((dropdown) => {
    const checkboxes = [...dropdown.querySelectorAll('input[type="checkbox"]')];
    const clearButton = dropdown.querySelector(".filter-clear");

    checkboxes.forEach((checkbox) => {
      checkbox.addEventListener("change", submitFilters);
    });

    clearButton?.addEventListener("click", () => {
      checkboxes.forEach((checkbox) => {
        checkbox.checked = false;
      });
      submitFilters();
    });
  });

  document.addEventListener("click", (event) => {
    filterForm.querySelectorAll(".filter-dropdown[open]").forEach((dropdown) => {
      if (!dropdown.contains(event.target)) {
        dropdown.removeAttribute("open");
      }
    });
  });
}
