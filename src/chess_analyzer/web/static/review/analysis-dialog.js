const dialog = document.getElementById('analysis-dialog');
const trigger = document.getElementById('show-analysis');
const summary = document.querySelector('.review-column');
const workspace = summary.parentElement;
const modalContent = document.getElementById('analysis-modal-content');
const compactScreen = window.matchMedia('(max-width: 1024px), (max-height: 600px)');

function updateAnalysisLayout() {
  if (!compactScreen.matches && dialog.open) dialog.close();
  (compactScreen.matches ? modalContent : workspace).append(summary);
}

trigger.addEventListener('click', () => {
  if (compactScreen.matches && !dialog.open) dialog.showModal();
});
document.getElementById('close-analysis').addEventListener('click', () => dialog.close());
dialog.addEventListener('keydown', (event) => {
  if (event.key !== 'Tab') return;
  const controls = [...dialog.querySelectorAll('button:not(:disabled), input:not(:disabled), [href], [tabindex="0"]')]
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
compactScreen.addEventListener('change', updateAnalysisLayout);
updateAnalysisLayout();