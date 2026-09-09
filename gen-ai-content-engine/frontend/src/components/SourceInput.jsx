import { useCallback, useRef, useState } from 'react';

import { cx, ui } from '../lib/ui';

const ACCEPTED_EXTENSIONS = '.pdf,.docx,.txt';
const ACCEPTED_MIME = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
];

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getExt(file) {
  const name = (file?.name || '').toLowerCase();
  if (name.endsWith('.pdf')) return 'PDF';
  if (name.endsWith('.docx')) return 'DOCX';
  if (name.endsWith('.txt')) return 'TXT';
  return 'FILE';
}

const SOURCE_TABS = [
  { key: 'text', label: 'Paste text' },
  { key: 'file', label: 'Upload file' },
  { key: 'url', label: 'URL' },
];

export default function SourceInput({
  sourceType,
  onSourceTypeChange,
  text,
  onTextChange,
  file,
  onFileChange,
  url,
  onUrlChange,
}) {
  const [dragOver, setDragOver] = useState(false);
  const [urlError, setUrlError] = useState('');
  const fileRef = useRef(null);

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;

  const applyFile = useCallback(
    (f) => {
      if (f && (ACCEPTED_MIME.includes(f.type) || f.name?.toLowerCase().endsWith('.docx'))) {
        onFileChange(f);
      }
    },
    [onFileChange]
  );

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragOver(false);
      applyFile(e.dataTransfer.files[0]);
    },
    [applyFile]
  );

  const validateUrl = (val) => {
    setUrlError('');
    if (!val.trim()) return;
    try {
      const parsed = new URL(val.trim());
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        setUrlError('Only http:// and https:// URLs are supported.');
      }
    } catch {
      setUrlError('Enter a valid URL (e.g. https://example.com/article).');
    }
  };

  const openPicker = () => { if (!file) fileRef.current?.click(); };

  return (
    <div>
      {/* Segmented tabs */}
      <div className="inline-flex rounded-lg border border-line bg-inset p-1" role="tablist" aria-label="Source type">
        {SOURCE_TABS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={sourceType === key}
            onClick={() => { onSourceTypeChange(key); setUrlError(''); }}
            className={cx(
              'rounded-md px-3 py-1.5 text-xs font-medium transition',
              sourceType === key ? 'bg-elevated text-ink shadow-panel' : 'text-ink-muted hover:text-ink'
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {/* Paste text */}
        {sourceType === 'text' && (
          <div className="relative">
            <textarea
              className={cx(ui.field, 'min-h-[190px] resize-y leading-relaxed')}
              placeholder="Paste the report, advisory, or article you want to repurpose…"
              value={text}
              onChange={(e) => onTextChange(e.target.value)}
              aria-label="Source text input"
              rows={8}
            />
            {text.length > 0 && (
              <div className="mt-2 flex items-center justify-between text-xs text-ink-subtle">
                <span aria-live="polite">{wordCount} {wordCount === 1 ? 'word' : 'words'}</span>
                <button type="button" onClick={() => onTextChange('')} className="font-medium text-ink-muted hover:text-danger">
                  Clear
                </button>
              </div>
            )}
          </div>
        )}

        {/* Upload file */}
        {sourceType === 'file' && (
          <div
            onDrop={handleDrop}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onClick={openPicker}
            role={file ? undefined : 'button'}
            tabIndex={file ? -1 : 0}
            onKeyDown={(e) => {
              if (!file && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openPicker(); }
            }}
            aria-label={file ? undefined : 'Click or drag a file to attach'}
            className={cx(
              'rounded-lg border border-dashed px-4 py-8 text-center transition',
              file ? 'border-line bg-surface-2' : 'cursor-pointer border-line-strong hover:border-accent hover:bg-accent-soft/40',
              dragOver && 'border-accent bg-accent-soft'
            )}
          >
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              accept={ACCEPTED_EXTENSIONS}
              onChange={(e) => applyFile(e.target.files[0])}
              tabIndex={-1}
            />

            {file ? (
              <div className="flex items-center gap-3 text-left">
                <span className="rounded-md bg-accent-soft px-2 py-1 text-[10px] font-bold tracking-wide text-accent">
                  {getExt(file)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-ink">{file.name}</p>
                  <p className="text-xs text-ink-subtle">{formatBytes(file.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onFileChange(null); if (fileRef.current) fileRef.current.value = ''; }}
                  aria-label={`Remove ${file.name}`}
                  className="rounded-md p-1.5 text-ink-subtle hover:bg-elevated hover:text-danger"
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                    <path d="M2 2l8 8M10 2L2 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-1.5">
                <svg className="text-ink-subtle" width="20" height="20" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path d="M8 11V4M5.5 6.5L8 4l2.5 2.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M3 12.5h10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" opacity="0.45" />
                </svg>
                <span className="text-sm font-medium text-ink">
                  {dragOver ? 'Drop to attach' : 'Drag a file or click to upload'}
                </span>
                <span className="text-xs text-ink-subtle">PDF · DOCX · TXT — up to 10 MB</span>
              </div>
            )}
          </div>
        )}

        {/* URL */}
        {sourceType === 'url' && (
          <div>
            <div className={cx('flex items-center gap-2 rounded-lg border bg-inset px-3', urlError ? 'border-danger' : 'border-line-strong focus-within:border-accent')}>
              <svg className="shrink-0 text-ink-subtle" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <path d="M6.3 8.4a3.5 3.5 0 004.95 0l1.75-1.75a3.5 3.5 0 00-4.95-4.95L7 3.75" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                <path d="M7.7 5.6a3.5 3.5 0 00-4.95 0L1 7.35a3.5 3.5 0 004.95 4.95L7 11.25" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              </svg>
              <input
                type="url"
                className="w-full bg-transparent py-2.5 text-sm text-ink outline-none placeholder:text-ink-subtle"
                placeholder="https://example.com/article-or-report"
                value={url}
                onChange={(e) => { onUrlChange(e.target.value); validateUrl(e.target.value); }}
                aria-label="Source URL"
                autoComplete="off"
              />
              {url && (
                <button
                  type="button"
                  onClick={() => { onUrlChange(''); setUrlError(''); }}
                  aria-label="Clear URL"
                  className="shrink-0 rounded-md p-1 text-ink-subtle hover:text-danger"
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                    <path d="M2 2l8 8M10 2L2 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>
              )}
            </div>
            {urlError && <p className="mt-1.5 text-xs text-danger" role="alert">{urlError}</p>}
            <p className="mt-2 text-xs leading-relaxed text-ink-subtle">
              The backend fetches and extracts the article text. Paywalled or JavaScript-heavy
              pages may not work — paste the text directly instead.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
