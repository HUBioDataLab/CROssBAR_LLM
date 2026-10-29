import { linkifyCitations } from './citationLinks';

describe('linkifyCitations', () => {
  test('links a single PMID to PubMed', () => {
    expect(linkifyCitations('EGFR drives growth [PMID:12345678].')).toBe(
      'EGFR drives growth \\[[PMID:12345678](<https://pubmed.ncbi.nlm.nih.gov/12345678/>)\\].',
    );
  });

  test('links every identifier in a mixed group', () => {
    const out = linkifyCitations('[PMID:1; PMCID:PMC42; DOI:10.1000/a_b(1)]');
    expect(out).toContain('[PMID:1](<https://pubmed.ncbi.nlm.nih.gov/1/>)');
    expect(out).toContain('[PMCID:PMC42](<https://www.ncbi.nlm.nih.gov/pmc/articles/PMC42/>)');
    expect(out).toContain('[DOI:10.1000/a\\_b(1)](<https://doi.org/10.1000/a_b(1)>)');
  });

  test('carries the PMID prefix across bare numbers', () => {
    const out = linkifyCitations('[PMID:1,2]');
    expect(out).toBe(
      '\\[[PMID:1](<https://pubmed.ncbi.nlm.nih.gov/1/>), [PMID:2](<https://pubmed.ncbi.nlm.nih.gov/2/>)\\]',
    );
  });

  test('leaves non-identifier brackets and malformed IDs alone', () => {
    expect(linkifyCitations('[KG] and [Paperclip source 2]')).toBe('[KG] and [Paperclip source 2]');
    expect(linkifyCitations('[PMID:X]')).toBe('[PMID:X]');
  });

  test('does not rewrite code', () => {
    const text = 'see `[PMID:1]` and\n```\n[PMID:2]\n```';
    expect(linkifyCitations(text)).toBe(text);
  });
});
