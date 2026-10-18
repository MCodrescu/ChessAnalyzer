/** Native modal: focus containment, Escape dismissal, and focus restoration. */
export const importDialog = document.getElementById('import-dialog');

document.getElementById('load-game').addEventListener('click', () => {
  if (!importDialog.open) importDialog.showModal();
});
document.getElementById('close-import').addEventListener('click', () => importDialog.close());

// Wrap Tab within the modal instead of letting it escape into browser chrome.
importDialog.addEventListener('keydown', (event) => {
  if (event.key !== 'Tab') return;
  const controls = [...importDialog.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex="0"]')]
    .filter((control) => control.getClientRects().length > 0);
  const first = controls[0];
  const last = controls.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last?.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first?.focus();
  }
});

/** Keep progress visible both while loading a game and after dismissing the modal. */
export function setReviewStatus(message) {
  document.getElementById('status').textContent = message;
  document.getElementById('import-status').textContent = message;
}