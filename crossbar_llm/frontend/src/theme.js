import { createTheme } from '@mui/material/styles';

export const getTheme = (mode) => createTheme({
  palette: {
    mode,
    primary: {
      main: mode === 'dark' ? '#64B5F6' : '#0071e3',
      light: mode === 'dark' ? '#90CAF9' : '#47a9ff',
      dark: mode === 'dark' ? '#1E88E5' : '#0058b0',
      contrastText: '#FFFFFF',
    },
    secondary: {
      main: mode === 'dark' ? '#B39DDB' : '#5e5ce6',
      light: mode === 'dark' ? '#D1C4E9' : '#7d7aef',
      dark: mode === 'dark' ? '#7E57C2' : '#4641c7',
      contrastText: '#FFFFFF',
    },
    background: {
      default: mode === 'dark' ? '#1c1c1e' : '#f5f5f7',
      paper: mode === 'dark' ? '#2c2c2e' : '#FFFFFF',
      subtle: mode === 'dark' ? '#3a3a3c' : '#f2f2f7',
    },
    text: {
      primary: mode === 'dark' ? '#FFFFFF' : '#1d1d1f',
      secondary: mode === 'dark' ? '#aeaeb2' : '#86868b',
      disabled: mode === 'dark' ? '#636366' : '#c7c7cc',
    },
    divider: mode === 'dark' ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.06)',
    action: {
      active: mode === 'dark' ? '#FFFFFF' : '#1d1d1f',
      hover: mode === 'dark' ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.03)',
      selected: mode === 'dark' ? 'rgba(255, 255, 255, 0.16)' : 'rgba(0, 0, 0, 0.06)',
    },
  },
  typography: {
    fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    h1: {
      fontFamily: '"Outfit", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", Arial, sans-serif',
      fontWeight: 600,
      fontSize: '2.5rem',
      letterSpacing: '-0.02em',
      lineHeight: 1.2,
    },
    h2: {
      fontFamily: '"Outfit", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", Arial, sans-serif',
      fontWeight: 600,
      fontSize: '2rem',
      letterSpacing: '-0.015em',
      lineHeight: 1.3,
    },
    h3: {
      fontFamily: '"Outfit", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", Arial, sans-serif',
      fontWeight: 600,
      fontSize: '1.5rem',
      letterSpacing: '-0.01em',
      lineHeight: 1.4,
    },
    h4: {
      fontFamily: '"Outfit", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", Arial, sans-serif',
      fontWeight: 600,
      fontSize: '1.25rem',
      letterSpacing: '-0.01em',
      lineHeight: 1.4,
    },
    h5: {
      fontFamily: '"Outfit", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", Arial, sans-serif',
      fontWeight: 600,
      fontSize: '1.1rem',
      letterSpacing: '-0.005em',
      lineHeight: 1.5,
    },
    h6: {
      fontFamily: '"Outfit", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", Arial, sans-serif',
      fontWeight: 600,
      fontSize: '1rem',
      letterSpacing: '-0.005em',
      lineHeight: 1.5,
    },
    subtitle1: {
      fontWeight: 500,
      fontSize: '0.95rem',
      letterSpacing: '0',
      lineHeight: 1.5,
      color: mode === 'dark' ? '#aeaeb2' : '#86868b',
    },
    subtitle2: {
      fontWeight: 500,
      fontSize: '0.875rem',
      letterSpacing: '0',
      lineHeight: 1.5,
      color: mode === 'dark' ? '#aeaeb2' : '#86868b',
    },
    body1: {
      fontWeight: 400,
      fontSize: '1rem',
      letterSpacing: '0',
      lineHeight: 1.6,
    },
    body2: {
      fontWeight: 400,
      fontSize: '0.875rem',
      letterSpacing: '0',
      lineHeight: 1.6,
    },
    button: {
      fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
      fontWeight: 600,
      fontSize: '0.875rem',
      letterSpacing: '0.01em',
      textTransform: 'none',
    },
    caption: {
      fontWeight: 400,
      fontSize: '0.75rem',
      letterSpacing: '0.01em',
      lineHeight: 1.5,
    },
    overline: {
      fontWeight: 600,
      fontSize: '0.75rem',
      letterSpacing: '0.05em',
      textTransform: 'uppercase',
      lineHeight: 1.5,
    },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        html: {
          fontSize: '16px',
        },
        body: {
          scrollbarWidth: 'thin',
          '-webkit-font-smoothing': 'antialiased',
          '-moz-osx-font-smoothing': 'grayscale',
          textRendering: 'optimizeLegibility',
          letterSpacing: '0',
          '&::-webkit-scrollbar': {
            width: '8px',
            height: '8px',
          },
          '&::-webkit-scrollbar-track': {
            background: mode === 'dark' ? '#2c2c2e' : '#f5f5f7',
          },
          '&::-webkit-scrollbar-thumb': {
            background: mode === 'dark' ? '#636366' : '#c7c7cc',
            borderRadius: '4px',
          },
          '&::-webkit-scrollbar-thumb:hover': {
            background: mode === 'dark' ? '#8e8e93' : '#a1a1a6',
          },
        },
        '.MuiTypography-root': {
          marginBottom: '0.5em',
          '&:last-child': {
            marginBottom: 0,
          }
        },
        '.MuiDrawer-paper': {
          fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        },
        '.MuiAppBar-root': {
          fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        },
        '.MuiMenuItem-root': {
          fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        },
        '.MuiListItem-root': {
          fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        },
        '.MuiTab-root': {
          fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
          fontWeight: 600,
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
          fontWeight: 600,
          borderRadius: '8px',
          boxShadow: 'none',
          padding: '8px 16px',
          transition: 'all 0.2s ease-in-out',
          '&:hover': {
            boxShadow: '0 4px 8px rgba(0, 0, 0, 0.1)',
            transform: 'translateY(-1px)',
          },
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            borderRadius: '12px',
            backgroundColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.02)',
            transition: 'all 0.2s',
            '&:hover': {
              backgroundColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.03)',
            },
            '&.Mui-focused': {
              backgroundColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.04)',
              boxShadow: mode === 'dark' ? '0 0 0 2px rgba(100, 181, 246, 0.4)' : '0 0 0 2px rgba(0, 113, 227, 0.4)',
            },
          },
          '& .MuiOutlinedInput-notchedOutline': {
            borderColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.12)',
          },
          '& .MuiInputLabel-root': {
            fontSize: '0.9rem',
          },
        },
      },
      defaultProps: {
        variant: 'outlined',
        margin: 'normal',
      },
    },
    MuiSelect: {
      styleOverrides: {
        root: {
          borderRadius: '12px',
          backgroundColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.02)',
          '&:hover': {
            backgroundColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.03)',
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: '12px',
          boxShadow: mode === 'dark' 
            ? '0 4px 20px rgba(0, 0, 0, 0.25)' 
            : '0 4px 20px rgba(0, 0, 0, 0.05)',
          transition: 'all 0.3s ease',
          overflow: 'hidden',
        },
      },
    },
    MuiCardHeader: {
      styleOverrides: {
        title: {
          fontFamily: '"Outfit", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", Arial, sans-serif',
          fontWeight: 600,
        },
        subheader: {
          fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        },
      },
    },
    MuiCardContent: {
      styleOverrides: {
        root: {
          padding: '24px',
          '&:last-child': {
            paddingBottom: '24px',
          },
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        root: {
          borderBottom: mode === 'dark' ? '1px solid rgba(255, 255, 255, 0.12)' : '1px solid rgba(0, 0, 0, 0.06)',
        },
        indicator: {
          height: '3px',
          borderRadius: '1.5px',
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 500,
          fontSize: '0.9rem',
          minWidth: '100px',
          padding: '12px 16px',
          transition: 'all 0.2s',
          '&.Mui-selected': {
            fontWeight: 600,
          },
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: '16px',
          boxShadow: mode === 'dark' 
            ? '0 8px 32px rgba(0, 0, 0, 0.5)' 
            : '0 8px 32px rgba(0, 0, 0, 0.1)',
          backdropFilter: 'blur(10px)',
          backgroundColor: mode === 'dark' ? 'rgba(44, 44, 46, 0.9)' : 'rgba(255, 255, 255, 0.9)',
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          borderRadius: '10px',
          padding: '8px',
          transition: 'all 0.2s ease',
          '&:hover': {
            backgroundColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.05)',
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: '16px',
          boxShadow: mode === 'dark' 
            ? '0 4px 20px rgba(0, 0, 0, 0.3)' 
            : '0 2px 12px rgba(0, 0, 0, 0.05)',
          backdropFilter: 'blur(10px)',
          backgroundColor: mode === 'dark' ? 'rgba(44, 44, 46, 0.8)' : 'rgba(255, 255, 255, 0.8)',
        },
        elevation1: {
          boxShadow: mode === 'dark' 
            ? '0 2px 8px rgba(0, 0, 0, 0.3)' 
            : '0 1px 4px rgba(0, 0, 0, 0.05)',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          boxShadow: 'none',
          backdropFilter: 'blur(10px)',
          backgroundColor: mode === 'dark' ? 'rgba(28, 28, 30, 0.8)' : 'rgba(255, 255, 255, 0.8)',
          borderBottom: mode === 'dark' ? '1px solid rgba(255, 255, 255, 0.1)' : '1px solid rgba(0, 0, 0, 0.06)',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backdropFilter: 'blur(10px)',
          backgroundColor: mode === 'dark' ? 'rgba(28, 28, 30, 0.9)' : 'rgba(255, 255, 255, 0.9)',
          borderRight: mode === 'dark' ? '1px solid rgba(255, 255, 255, 0.1)' : '1px solid rgba(0, 0, 0, 0.06)',
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
          fontWeight: 500,
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: mode === 'dark' ? 'rgba(44, 44, 46, 0.9)' : 'rgba(0, 0, 0, 0.8)',
          borderRadius: '8px',
          padding: '8px 12px',
          fontSize: '0.75rem',
          backdropFilter: 'blur(10px)',
        },
      },
    },
    MuiDivider: {
      styleOverrides: {
        root: {
          borderColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.06)',
        },
      },
    },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          borderRadius: '8px',
          margin: '2px 8px',
          padding: '8px 12px',
          '&:hover': {
            backgroundColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.03)',
          },
        },
      },
    },
    MuiInputBase: {
      styleOverrides: {
        root: {
          fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: '8px',
          '& fieldset': {
            borderColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.12)',
          },
          '&:hover fieldset': {
            borderColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.2)' : 'rgba(0, 0, 0, 0.2)',
          },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        },
        head: {
          fontWeight: 600,
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: '8px',
        },
        message: {
          fontFamily: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        },
      },
    },
  },
});