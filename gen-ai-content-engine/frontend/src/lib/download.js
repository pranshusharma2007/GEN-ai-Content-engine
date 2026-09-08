/**
 * Trigger a browser download for a Blob without corrupting it.
 *
 * The naive `a.click(); URL.revokeObjectURL(href)` pattern revokes the object URL
 * before the browser has finished reading it, which truncates binary files
 * (.pptx / .pdf show up as "invalid format"). Fix: keep the anchor in the DOM
 * and revoke on a delay.
 */
export function saveBlob(blob, filename) {
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = filename;
  a.rel = 'noopener';
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(href);
    a.remove();
  }, 4000);
}

/** Same, for a data: URL (e.g. html-to-image PNG). No revoke needed. */
export function saveDataUrl(dataUrl, filename) {
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => a.remove(), 1000);
}
