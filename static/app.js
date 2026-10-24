// Reset confirmation pop-up (and any other <dialog> opener).
document.querySelectorAll("[data-open-dialog]").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.getElementById(btn.dataset.openDialog).showModal();
  });
});
document.querySelectorAll("[data-close-dialog]").forEach((btn) => {
  btn.addEventListener("click", () => btn.closest("dialog").close());
});
// Clicking the backdrop closes the dialog.
document.querySelectorAll("dialog.modal").forEach((dialog) => {
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) dialog.close();
  });
});

// Simple confirm() for destructive forms like deleting a card or deck.
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (e) => {
    if (!confirm(form.dataset.confirm)) e.preventDefault();
  });
});

// Study page: flip the card, keyboard shortcuts.
const flashcard = document.getElementById("flashcard");
if (flashcard) {
  flashcard.addEventListener("click", () => flashcard.classList.toggle("flipped"));
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea")) return;
    if (e.key === " " && e.target !== flashcard) {
      e.preventDefault();
      flashcard.classList.toggle("flipped");
    } else if (e.key === "1" || e.key === "2") {
      document.querySelector(`[data-key="${e.key}"]`)?.click();
    }
  });
}
