import { useState, useRef, useCallback } from 'react';

const ACCEPTED_EXTENSIONS = '.pdf,.docx,.txt';
const ACCEPTED_MIME = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
];

function formatBytes(bytes) {
  if (bytes < 1024)        return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getExt(file) {
  const name = (file?.name || '').toLowerCase();
  if (name.endsWith('.pdf'))  return 'PDF';
  if (name.endsWith('.docx')) return 'DOCX';
  if (name.endsWith('.txt'))  return 'TXT';
  return 'FILE';
}

const SOURCE_TABS = [
  { key: 'text', label: 'Paste text' },
  { key: 'file', label: 'Upload file' },
  { key: 'url',  label: 'URL' },
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
      setUrlError('Please enter a valid URL (e.g. https://example.com/article).');
    }
  };

  const openPicker = () => {
    if (!file) fileRef.current?.click();
  };

  const dropzoneCls = [
    'dropzone',
    dragOver ? 'dropzone--over' : '',
    file      ? 'dropzone--has-file' : '',
  ].filter(Boolean).join(' ');

  return (
    <div className="source-input">
      {/* ── Source type tabs ── */}
      <div className="source-tabs" role="tablist" aria-label="Source type">
        {SOURCE_TABS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={sourceType === key}
            className={`source-tab${sourceType === key ? ' source-tab--active' : ''}`}
            onClick={() => { onSourceTypeChange(key); setUrlError(''); }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Paste text ── */}
      {sourceType === 'text' && (
        <div className="textarea-wrap">
          <textarea
            className="source-textarea"
            placeholder="Start with the idea, context, or source material you want to repurpose…"
            value={text}
            onChange={(e) => onTextChange(e.target.value)}
            aria-label="Source text input"
            rows={8}
          />
          {text.length > 0 && (
            <span className="textarea-count" aria-live="polite">
              {wordCount} {wordCount === 1 ? 'word' : 'words'}
            </span>
          )}
          {text.length > 0 && (
            <button type="button" className="clear-inline" onClick={() => onTextChange('')}>
              Clear
            </button>
          )}
        </div>
      )}

      {/* ── Upload file ── */}
      {sourceType === 'file' && (
        <div
          className={dropzoneCls}
          onDrop={handleDrop}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onClick={openPicker}
          role={file ? undefined : 'button'}
          tabIndex={file ? -1 : 0}
          onKeyDown={(e) => {
            if (!file && (e.key === 'Enter' || e.key === ' ')) {
              e.preventDefault();
              openPicker();
            }
          }}
          aria-label={file ? undefined : 'Click or drag a file to attach'}
        >
          <input
            ref={fileRef}
            type="file"
            className="dropzone-file-input"
            accept={ACCEPTED_EXTENSIONS}
            onChange={(e) => applyFile(e.target.files[0])}
            aria-hidden="true"
            tabIndex={-1}
          />

          {file ? (
            <div className="file-attachment">
              <span className="file-badge">{getExt(file)}</span>
              <div className="file-info">
                <span className="file-name">{file.name}</span>
                <span className="file-size">{formatBytes(file.size)}</span>
              </div>
              <button
                type="button"
                className="file-remove"
                onClick={(e) => { e.stopPropagation(); onFileChange(null); if (fileRef.current) fileRef.current.value = ''; }}
                aria-label={`Remove ${file.name}`}
              >
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                  <path d="M2 2l8 8M10 2L2 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          ) : (
            <div className="dropzone-prompt">
              <svg className="dropzone-prompt-icon" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M8 11V4M5.5 6.5L8 4l2.5 2.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M3 12.5h10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" opacity="0.45" />
              </svg>
              <span className="dropzone-prompt-main">
                {dragOver ? 'Drop to attach' : 'Drag a file or click to upload'}
              </span>
              <span className="dropzone-prompt-types">PDF · DOCX · TXT</span>
            </div>
          )}
        </div>
      )}

      {/* ── URL input ── */}
      {sourceType === 'url' && (
        <div className="url-input-wrap">
          <div className="url-input-row">
            <span className="url-icon" aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M6.3 8.4a3.5 3.5 0 004.95 0l1.75-1.75a3.5 3.5 0 00-4.95-4.95L7 3.75" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                <path d="M7.7 5.6a3.5 3.5 0 00-4.95 0L1 7.35a3.5 3.5 0 004.95 4.95L7 11.25" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              </svg>
            </span>
            <input
              type="url"
              className={`url-input${urlError ? ' url-input--error' : ''}`}
              placeholder="https://example.com/article-or-report"
              value={url}
              onChange={(e) => { onUrlChange(e.target.value); validateUrl(e.target.value); }}
              aria-label="Source URL"
              autoComplete="off"
            />
            {url && (
              <button
                type="button"
                className="url-clear"
                onClick={() => { onUrlChange(''); setUrlError(''); }}
                aria-label="Clear URL"
              >
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                  <path d="M2 2l8 8M10 2L2 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            )}
          </div>
          {urlError && <p className="url-error" role="alert">{urlError}</p>}
          <p className="url-hint">
            The backend will fetch and extract the article content. Paywalled or JavaScript-heavy pages may not work — paste the text directly instead.
          </p>
        </div>
      )}
    </div>
  );
}
