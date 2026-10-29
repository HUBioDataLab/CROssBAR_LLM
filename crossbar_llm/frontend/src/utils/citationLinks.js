/**
 * Turn the publication identifiers agents cite inline into Markdown links.
 *
 * The synthesizer and the literature agents cite as `[PMID:12345678]`,
 * `[PMID:1; DOI:10.1000/x]`, `[PMID:1, PMID:2]` or `[PMID:1,2,3]`. Each
 * identifier becomes its own link; the brackets stay as plain text. A bracket
 * holding anything that is not a valid identifier is left untouched, so
 * `[KG]` and `[Paperclip source 2]` render as before.
 */

const ID_PATTERNS = {
  pmid: /^\d{1,9}$/,
  pmcid: /^PMC\d+$/i,
  doi: /^10\.\d{4,9}\/\S+$/,
};

const ID_URLS = {
  pmid: (id) => `https://pubmed.ncbi.nlm.nih.gov/${id}/`,
  pmcid: (id) => `https://www.ncbi.nlm.nih.gov/pmc/articles/${id.toUpperCase()}/`,
  doi: (id) => `https://doi.org/${encodeURI(id)}`,
};

const CITATION_GROUP = /\[((?:PMID|PMCID|DOI)\s*:[^\]\n]+)\]/gi;
const PREFIXED = /^(PMID|PMCID|DOI)\s*:\s*(.+)$/i;
// Fenced blocks and inline code spans are never rewritten.
const CODE = /(```[\s\S]*?```|`[^`\n]*`)/;

const escapeLinkText = (text) => text.replace(/([\\`*_[\]<>])/g, '\\$1');

/** One citation group's inner text → linked Markdown, or null if any part is not an identifier. */
const linkGroup = (inner) => {
  let prefix = null;
  const parts = inner.split(/([;,])/);
  const linked = [];
  for (const part of parts) {
    if (part === ';' || part === ',') {
      linked.push(`${part} `);
      continue;
    }
    const token = part.trim();
    const match = token.match(PREFIXED);
    let id = token;
    if (match) {
      prefix = match[1].toLowerCase();
      id = match[2].trim();
    }
    // A bare number after `PMID:` continues that prefix (`[PMID:1,2,3]`).
    if (!prefix || !ID_PATTERNS[prefix].test(id)) return null;
    const label = escapeLinkText(`${prefix === 'doi' ? 'DOI' : prefix.toUpperCase()}:${id}`);
    linked.push(`[${label}](<${ID_URLS[prefix](id)}>)`);
  }
  return `\\[${linked.join('')}\\]`;
};

const linkSegment = (text) =>
  text.replace(CITATION_GROUP, (whole, inner) => linkGroup(inner) ?? whole);

export const linkifyCitations = (markdown) => {
  if (typeof markdown !== 'string' || !markdown) return markdown;
  return markdown
    .split(CODE)
    .map((segment, index) => (index % 2 === 1 ? segment : linkSegment(segment)))
    .join('');
};
