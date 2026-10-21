document.addEventListener("DOMContentLoaded", () => {
  const navToggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector(".main-nav");

  if (navToggle && nav) {
    navToggle.addEventListener("click", () => {
      const isExpanded = navToggle.getAttribute("aria-expanded") === "true";
      navToggle.setAttribute("aria-expanded", String(!isExpanded));
      nav.classList.toggle("is-open", !isExpanded);
    });
  }

  document.querySelectorAll("[data-table-search]").forEach((input) => {
    const table = document.getElementById(input.dataset.tableSearch);
    if (!table) return;
    const categoryFilter = document.querySelector(`[data-category-filter="${table.id}"]`);
    const filterRows = () => {
      const query = input.value.trim().toLocaleLowerCase();
      const category = categoryFilter?.value || "";
      table.querySelectorAll("tbody tr").forEach((row) => {
        const categoryCell = row.querySelector("[data-category]");
        const matchesCategory = !category || categoryCell?.dataset.category === category;
        row.hidden = !matchesCategory || !row.textContent.toLocaleLowerCase().includes(query);
      });
    };
    input.addEventListener("input", filterRows);
    categoryFilter?.addEventListener("change", filterRows);
  });

  document.querySelectorAll(".loan-items").forEach((container) => {
    const selectors = [...container.querySelectorAll('select[name="item_id"]')];
    const quantities = [...container.querySelectorAll('input[name="quantity"]')];
    const form = container.closest("form");
    const submit = form?.querySelector('button[type="submit"]');
    const updateLimit = () => {
      const total = quantities.reduce((sum, input, index) => {
        return sum + (selectors[index].value ? Number(input.value || 0) : 0);
      }, 0);
      quantities.forEach((input, index) => {
        const remaining = 3 - total + (selectors[index].value ? Number(input.value || 0) : 0);
        input.max = String(Math.max(1, Math.min(3, remaining)));
        if (Number(input.value) > Number(input.max)) input.value = input.max;
      });
      if (submit) submit.disabled = total > 3;
    };
    selectors.forEach((select) => select.addEventListener("change", updateLimit));
    quantities.forEach((input) => input.addEventListener("input", updateLimit));
    updateLimit();
  });

  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
});
