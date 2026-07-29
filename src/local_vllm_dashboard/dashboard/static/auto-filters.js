const filterForm = document.querySelector("form.filters");
if (filterForm) {
  filterForm.querySelectorAll("select").forEach((select) => {
    select.addEventListener("change", () => filterForm.requestSubmit());
  });
}
