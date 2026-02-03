import React from 'react';
import {
  AppBar,
  Toolbar,
  Box,
  Typography,
  IconButton,
  Tooltip,
} from '@mui/material';
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';

/**
 * Application header with logo, theme toggle, and sidebar toggle.
 */
function AppHeader({
  mode,
  onThemeToggle,
  drawerVisible,
  onDrawerToggle,
  onLogoClick,
}) {
  return (
    <AppBar 
      position="fixed" 
      elevation={0}
      sx={{ 
        zIndex: (theme) => theme.zIndex.drawer + 1,
        borderBottom: theme => `1px solid ${theme.palette.divider}`,
        width: '100%'
      }}
    >
      <Toolbar sx={{ justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <Box sx={{ 
            display: 'flex', 
            alignItems: 'center',
            backgroundColor: theme => theme.palette.mode === 'dark' 
              ? 'rgba(100, 181, 246, 0.1)' 
              : 'rgba(0, 113, 227, 0.05)',
            borderRadius: '12px',
            px: 2,
            py: 0.5,
            cursor: 'pointer',
            '&:hover': {
              backgroundColor: theme => theme.palette.mode === 'dark' 
                ? 'rgba(100, 181, 246, 0.15)' 
                : 'rgba(0, 113, 227, 0.1)',
            }
          }}
          onClick={onLogoClick}>
            <Typography variant="h6" noWrap component="div" sx={{ 
              fontWeight: 700,
              display: { xs: 'none', sm: 'block' },
              background: mode === 'dark' 
                ? 'linear-gradient(90deg, #64B5F6 0%, #B39DDB 100%)' 
                : 'linear-gradient(90deg, #0071e3 0%, #5e5ce6 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              letterSpacing: '-0.01em'
            }}>
              CROssBAR-LLM
            </Typography>
          </Box>
        </Box>
        
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Tooltip title={drawerVisible ? "Hide sidebar" : "Show sidebar"}>
            <IconButton 
              onClick={onDrawerToggle} 
              color="inherit"
              sx={{ 
                backgroundColor: theme => theme.palette.mode === 'dark' 
                  ? 'rgba(255, 255, 255, 0.05)' 
                  : 'rgba(0, 113, 227, 0.08)',
                backdropFilter: 'blur(10px)',
                border: theme => `1px solid ${theme.palette.mode === 'dark' 
                  ? 'rgba(255, 255, 255, 0.1)' 
                  : 'rgba(0, 113, 227, 0.15)'}`,
                '&:hover': {
                  backgroundColor: theme => theme.palette.mode === 'dark' 
                    ? 'rgba(255, 255, 255, 0.1)' 
                    : 'rgba(0, 113, 227, 0.12)',
                },
                color: theme => theme.palette.mode === 'dark'
                  ? 'inherit'
                  : 'rgba(0, 113, 227, 0.8)'
              }}
            >
              {drawerVisible ? <ChevronLeftIcon /> : <ChevronRightIcon />}
            </IconButton>
          </Tooltip>
          <Tooltip title={mode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}>
            <IconButton 
              onClick={onThemeToggle} 
              color="inherit"
              sx={{ 
                backgroundColor: theme => theme.palette.mode === 'dark' 
                  ? 'rgba(255, 255, 255, 0.05)' 
                  : 'rgba(0, 113, 227, 0.08)',
                backdropFilter: 'blur(10px)',
                border: theme => `1px solid ${theme.palette.mode === 'dark' 
                  ? 'rgba(255, 255, 255, 0.1)' 
                  : 'rgba(0, 113, 227, 0.15)'}`,
                '&:hover': {
                  backgroundColor: theme => theme.palette.mode === 'dark' 
                    ? 'rgba(255, 255, 255, 0.1)' 
                    : 'rgba(0, 113, 227, 0.12)',
                },
                color: theme => theme.palette.mode === 'dark'
                  ? 'inherit'
                  : 'rgba(0, 113, 227, 0.8)'
              }}
            >
              {mode === 'light' ? <Brightness4Icon /> : <Brightness7Icon />}
            </IconButton>
          </Tooltip>
        </Box>
      </Toolbar>
    </AppBar>
  );
}

export default AppHeader;
