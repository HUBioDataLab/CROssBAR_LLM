import { createTheme } from '@mui/material/styles';

export const getTheme = (mode) =>
  createTheme({
    palette: {
      mode,
      primary: {
        main: mode === 'dark' ? '#818cf8' : '#4f46e5',
        light: mode === 'dark' ? '#a5b4fc' : '#6366f1',
        dark: mode === 'dark' ? '#6366f1' : '#3730a3',
        contrastText: '#FFFFFF',
      },
      secondary: {
        main: mode === 'dark' ? '#34d399' : '#059669',
        light: mode === 'dark' ? '#6ee7b7' : '#10b981',
        dark: mode === 'dark' ? '#10b981' : '#047857',
        contrastText: '#FFFFFF',
      },
      error: {
        main: mode === 'dark' ? '#f87171' : '#dc2626',
      },
      warning: {
        main: mode === 'dark' ? '#fbbf24' : '#d97706',
      },
      info: {
        main: mode === 'dark' ? '#60a5fa' : '#2563eb',
      },
      success: {
        main: mode === 'dark' ? '#34d399' : '#059669',
      },
      background: {
        default: mode === 'dark' ? '#0f0f13' : '#f8fafc',
        paper: mode === 'dark' ? '#18181f' : '#ffffff',
        subtle: mode === 'dark' ? '#1e1e28' : '#f1f5f9',
      },
      text: {
        primary: mode === 'dark' ? '#e2e8f0' : '#0f172a',
        secondary: mode === 'dark' ? '#94a3b8' : '#64748b',
        disabled: mode === 'dark' ? '#475569' : '#cbd5e1',
      },
      divider:
        mode === 'dark'
          ? 'rgba(255, 255, 255, 0.06)'
          : 'rgba(0, 0, 0, 0.06)',
      action: {
        active: mode === 'dark' ? '#e2e8f0' : '#0f172a',
        hover:
          mode === 'dark'
            ? 'rgba(255, 255, 255, 0.04)'
            : 'rgba(0, 0, 0, 0.02)',
        selected:
          mode === 'dark'
            ? 'rgba(129, 140, 248, 0.12)'
            : 'rgba(79, 70, 229, 0.08)',
      },
    },
    typography: {
      fontFamily:
        '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      h1: { fontWeight: 700, fontSize: '2rem', letterSpacing: '-0.025em' },
      h2: { fontWeight: 700, fontSize: '1.5rem', letterSpacing: '-0.02em' },
      h3: { fontWeight: 600, fontSize: '1.25rem', letterSpacing: '-0.015em' },
      h4: { fontWeight: 600, fontSize: '1.125rem', letterSpacing: '-0.01em' },
      h5: { fontWeight: 600, fontSize: '1rem' },
      h6: { fontWeight: 600, fontSize: '0.875rem' },
      subtitle1: {
        fontWeight: 500,
        fontSize: '0.875rem',
        color: mode === 'dark' ? '#94a3b8' : '#64748b',
      },
      subtitle2: {
        fontWeight: 500,
        fontSize: '0.8125rem',
        color: mode === 'dark' ? '#94a3b8' : '#64748b',
      },
      body1: { fontSize: '0.875rem', lineHeight: 1.6 },
      body2: { fontSize: '0.8125rem', lineHeight: 1.6 },
      button: { fontWeight: 600, fontSize: '0.8125rem', textTransform: 'none' },
      caption: { fontSize: '0.75rem', color: mode === 'dark' ? '#64748b' : '#94a3b8' },
      overline: {
        fontWeight: 600,
        fontSize: '0.6875rem',
        letterSpacing: '0.05em',
        textTransform: 'uppercase',
      },
    },
    shape: { borderRadius: 10 },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          html: { fontSize: '16px' },
          body: {
            scrollbarWidth: 'thin',
            WebkitFontSmoothing: 'antialiased',
            MozOsxFontSmoothing: 'grayscale',
            '&::-webkit-scrollbar': { width: '6px', height: '6px' },
            '&::-webkit-scrollbar-track': {
              background: mode === 'dark' ? '#18181f' : '#f1f5f9',
            },
            '&::-webkit-scrollbar-thumb': {
              background: mode === 'dark' ? '#334155' : '#cbd5e1',
              borderRadius: '3px',
            },
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: {
            borderRadius: '8px',
            boxShadow: 'none',
            padding: '8px 16px',
            '&:hover': { boxShadow: 'none' },
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            borderRadius: '12px',
            backgroundImage: 'none',
            border:
              mode === 'dark'
                ? '1px solid rgba(255,255,255,0.06)'
                : '1px solid rgba(0,0,0,0.06)',
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: '12px',
            boxShadow:
              mode === 'dark'
                ? '0 1px 3px rgba(0,0,0,0.4)'
                : '0 1px 3px rgba(0,0,0,0.06)',
          },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: { fontSize: '0.8125rem' },
          head: { fontWeight: 600 },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: { fontWeight: 500, fontSize: '0.75rem' },
        },
      },
      MuiTextField: {
        styleOverrides: {
          root: {
            '& .MuiOutlinedInput-root': {
              borderRadius: '8px',
              fontSize: '0.875rem',
            },
          },
        },
      },
      MuiTooltip: {
        styleOverrides: {
          tooltip: {
            borderRadius: '6px',
            fontSize: '0.75rem',
            padding: '6px 10px',
          },
        },
      },
    },
  });
