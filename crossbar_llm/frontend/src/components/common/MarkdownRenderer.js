import React from 'react';
import { Box, alpha, useTheme } from '@mui/material';
import ReactMarkdown from 'react-markdown';

/**
 * Styled markdown renderer component.
 */
function MarkdownRenderer({ children, sx = {} }) {
  const theme = useTheme();

  return (
    <Box
      sx={{
        '& p': { 
          margin: 0, 
          marginBottom: 1.5,
          lineHeight: 1.7,
          '&:last-child': { marginBottom: 0 }
        },
        '& strong': { fontWeight: 600 },
        '& em': { fontStyle: 'italic' },
        '& ul, & ol': { 
          margin: 0, 
          marginBottom: 1.5,
          paddingLeft: 2.5,
          '&:last-child': { marginBottom: 0 }
        },
        '& li': { 
          marginBottom: 0.5,
          lineHeight: 1.6,
        },
        '& code': {
          backgroundColor: alpha(theme.palette.primary.main, 0.1),
          padding: '2px 6px',
          borderRadius: '4px',
          fontSize: '0.875em',
          fontFamily: 'monospace',
        },
        '& pre': {
          backgroundColor: theme.palette.mode === 'dark' ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.05)',
          padding: 2,
          borderRadius: '8px',
          overflow: 'auto',
          marginBottom: 1.5,
          '& code': {
            backgroundColor: 'transparent',
            padding: 0,
          },
          '&:last-child': { marginBottom: 0 }
        },
        '& h1, & h2, & h3, & h4, & h5, & h6': {
          marginTop: 2,
          marginBottom: 1,
          fontWeight: 600,
          '&:first-of-type': { marginTop: 0 }
        },
        '& a': {
          color: theme.palette.primary.main,
          textDecoration: 'none',
          '&:hover': { textDecoration: 'underline' }
        },
        '& blockquote': {
          borderLeft: `3px solid ${theme.palette.primary.main}`,
          margin: 0,
          marginBottom: 1.5,
          paddingLeft: 2,
          color: 'text.secondary',
          '&:last-child': { marginBottom: 0 }
        },
        '& hr': {
          border: 'none',
          borderTop: `1px solid ${theme.palette.divider}`,
          margin: '16px 0',
        },
        '& table': {
          borderCollapse: 'collapse',
          width: '100%',
          marginBottom: 1.5,
          '&:last-child': { marginBottom: 0 }
        },
        '& th, & td': {
          border: `1px solid ${theme.palette.divider}`,
          padding: '8px 12px',
          textAlign: 'left',
        },
        '& th': {
          backgroundColor: alpha(theme.palette.primary.main, 0.05),
          fontWeight: 600,
        },
        ...sx,
      }}
    >
      <ReactMarkdown>{children}</ReactMarkdown>
    </Box>
  );
}

export default MarkdownRenderer;
