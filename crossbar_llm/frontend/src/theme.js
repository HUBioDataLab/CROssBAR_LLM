import { createTheme } from '@mui/material/styles';

export const getTheme = (mode) => createTheme({
  palette: {
    mode,
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: mode === 'dark' ? '#333333' : '#ffffff',
    },
    background: {
      default: mode === 'dark' ? '#121212' : '#f5f5f5',
      paper: mode === 'dark' ? '#1e1e1e' : '#ffffff',
    },
    text: {
      primary: mode === 'dark' ? '#ffffff' : '#000000',
      secondary: mode === 'dark' ? '#a0a0a0' : '#555555',
    },
  },
  typography: {
    fontFamily: 'Inter, sans-serif',
    h5: {
      fontWeight: 600,
    },
    subtitle1: {
      color: mode === 'dark' ? '#888888' : '#666666',
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: '8px',
          textTransform: 'none',
          boxShadow: 'none',
        },
        containedPrimary: {
          backgroundColor: mode === 'dark' ? '#1976d2' : '#000000',
          color: '#ffffff',
          '&:hover': {
            backgroundColor: mode === 'dark' ? '#1565c0' : '#333333',
          },
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          backgroundColor: mode === 'dark' ? '#1e1e1e' : '#ffffff',
          borderRadius: '8px',
        },
      },
      defaultProps: {
        variant: 'outlined',
        margin: 'normal',
      },
    },
    MuiSelect: {
      styleOverrides: {
        select: {
          backgroundColor: mode === 'dark' ? '#1e1e1e' : '#ffffff',
          borderRadius: '8px',
        },
      },
    },
  },
});