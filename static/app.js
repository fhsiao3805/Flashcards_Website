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

// Deck page: build up a list of new cards, then submit them all with "Add cards".
const addForm = document.getElementById("add-cards-form");
if (addForm) {
  const frontInput = document.getElementById("new-front");
  const backInput = document.getElementById("new-back");
  const list = document.getElementById("pending-list");
  const section = document.getElementById("pending-section");
  const count = document.getElementById("pending-count");
  const submit = document.getElementById("add-cards-submit");
  const errorBox = document.getElementById("add-card-error");
  const template = document.getElementById("pending-item-template");
  let submitting = false;

  const showError = (message) => {
    errorBox.textContent = message;
    errorBox.hidden = !message;
  };

  const refresh = () => {
    const n = list.children.length;
    section.hidden = n === 0;
    count.textContent = `(${n})`;
    submit.textContent = n ? `Add ${n} card${n === 1 ? "" : "s"}` : "Add cards";
  };

  // Moves the entry boxes into the pending list. Returns false if they're incomplete.
  const addToList = () => {
    const front = frontInput.value.trim();
    const back = backInput.value.trim();
    if (!front || !back) {
      showError("Fill in both the front and back before adding the card to the list.");
      (front ? backInput : frontInput).focus();
      return false;
    }
    const item = template.content.firstElementChild.cloneNode(true);
    item.querySelector("[data-front]").textContent = front;
    item.querySelector("[data-back]").textContent = back;
    item.querySelector('input[name="front"]').value = front;
    item.querySelector('input[name="back"]').value = back;
    list.appendChild(item);
    frontInput.value = "";
    backInput.value = "";
    showError("");
    refresh();
    frontInput.focus();
    return true;
  };

  document.getElementById("add-to-list").addEventListener("click", addToList);

  [frontInput, backInput].forEach((input) => {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        addToList();
      }
    });
  });

  list.addEventListener("click", (e) => {
    const remove = e.target.closest("[data-remove]");
    if (remove) {
      remove.closest("li").remove();
      refresh();
    }
  });

  addForm.addEventListener("submit", (e) => {
    const typed = frontInput.value.trim() || backInput.value.trim();
    // A card still in the entry boxes gets added to the list rather than lost.
    if (typed && !addToList()) {
      e.preventDefault();
      return;
    }
    if (list.children.length === 0) {
      e.preventDefault();
      showError("Add at least one card to the list first.");
      frontInput.focus();
      return;
    }
    submitting = true;
  });

  window.addEventListener("beforeunload", (e) => {
    if (!submitting && list.children.length > 0) e.preventDefault();
  });
}
