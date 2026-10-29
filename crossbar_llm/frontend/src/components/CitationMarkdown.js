import React from 'react';
import ReactMarkdown from 'react-markdown';
import { linkifyCitations } from '../utils/citationLinks';

const ExternalLink = ({ node, children, ...props }) => (
  <a {...props} target="_blank" rel="noreferrer">{children}</a>
);
const COMPONENTS = { a: ExternalLink };

/** Markdown with cited PMIDs, PMCIDs and DOIs linked to their sources. */
function CitationMarkdown({ children }) {
  return <ReactMarkdown components={COMPONENTS}>{linkifyCitations(children)}</ReactMarkdown>;
}

export default CitationMarkdown;
