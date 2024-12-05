import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'light', 
    primary: {
      main: '#1976d2', 
    },
    secondary: {
      main: '#ffffff', 
    },
    background: {
      default: '#f5f5f5', 
      paper: '#ffffff', 
    },
    text: {
      primary: '#000000', 
      secondary: '#555555', 
    },
  },
  typography: {
    fontFamily: 'Inter, sans-serif', 
    h5: {
      fontWeight: 600, 
    },
    subtitle1: {
      color: '#888888', 
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
          backgroundColor: '#000000', 
          color: '#ffffff', 
          '&:hover': {
            backgroundColor: '#333333', 
          },
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          backgroundColor: '#ffffff', 
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
          backgroundColor: '#ffffff', 
          borderRadius: '8px',
        },
      },
    },
  },
});

export default theme;