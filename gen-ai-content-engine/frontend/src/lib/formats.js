/** Output format keys — must match backend SUPPORTED_FORMATS. */
export const OUTPUT_OPTS = [
  { key: 'advisory',          label: 'Advisory' },
  { key: 'executive_summary', label: 'Executive Summary' },
  { key: 'linkedin',          label: 'LinkedIn Post' },
  { key: 'x_thread',          label: 'X / Twitter Thread' },
  { key: 'presentation',      label: 'Presentation' },
  { key: 'infographic',       label: 'Infographic' },
];

export const TONES = [
  'Professional',
  'Authoritative & Strategic',
  'Casual & Engaging',
  'Urgent & Action-Oriented',
  'Inspirational',
];

export const AUDIENCES = [
  'Leadership / Execs',
  'General Public',
  'Tech / Developers',
  'Sales / Marketing',
  'Stakeholders & Investors',
];
