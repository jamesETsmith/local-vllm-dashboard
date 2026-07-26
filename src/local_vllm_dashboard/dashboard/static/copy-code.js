document.querySelectorAll(".copy-button[data-copy-target]").forEach((button) => {
  button.addEventListener("click", async () => {
    const target = document.getElementById(button.dataset.copyTarget);
    if (!target) return;
    const rawTarget = target.dataset.rawCode ? document.getElementById(target.dataset.rawCode) : null;
    await navigator.clipboard.writeText(rawTarget ? rawTarget.value : target.textContent);
    const original = button.textContent;
    button.textContent = "Copied";
    window.setTimeout(() => { button.textContent = original; }, 1400);
  });
});
