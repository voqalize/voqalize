/**
 * Copy buttons, on any page that has one: `data-copy` copies its value; `data-copy-from` copies the
 * text of the element it names. Where the clipboard is blocked, the text is selected instead, so
 * Ctrl+C or Cmd+C still works.
 */
document.addEventListener('click', async (e) => {
  const btn = (e.target as Element | null)?.closest<HTMLButtonElement>('button[data-copy], button[data-copy-from]');
  if (!btn) return;
  const from = btn.dataset.copyFrom ? document.querySelector(btn.dataset.copyFrom) : null;
  const text = btn.dataset.copy ?? from?.textContent?.trim() ?? '';
  const label = btn.textContent;
  try { await navigator.clipboard.writeText(text); btn.textContent = 'Copied'; }
  catch {
    btn.textContent = 'Press Ctrl+C to copy';
    window.getSelection()?.selectAllChildren(btn.closest('.email')?.querySelector('.email__addr') ?? from ?? btn);
  }
  window.setTimeout(() => { btn.textContent = label; }, 1800);
});
