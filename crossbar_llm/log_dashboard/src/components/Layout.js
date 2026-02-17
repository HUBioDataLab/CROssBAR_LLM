import React, { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  Box,
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Typography,
  IconButton,
  Divider,
  Tooltip,
  useMediaQuery,
  useTheme,
  AppBar,
  Toolbar,
  Breadcrumbs,
  Link as MuiLink,
} from '@mui/material';
import {
  Dashboard as DashboardIcon,
  FormatListBulleted as LogsIcon,
  DarkMode as DarkModeIcon,
  LightMode as LightModeIcon,
  ChevronLeft as CollapseIcon,
  ChevronRight as ExpandIcon,
  Menu as MenuIcon,
  BarChart as BrandIcon,
} from '@mui/icons-material';
import { useColorMode } from '../App';

const DRAWER_WIDTH = 240;
const DRAWER_COLLAPSED = 68;

const NAV_ITEMS = [
  { label: 'Overview', path: '/', icon: <DashboardIcon /> },
  { label: 'Logs Explorer', path: '/logs', icon: <LogsIcon /> },
];

function getPageTitle(pathname) {
  if (pathname === '/') return 'Overview';
  if (pathname === '/logs') return 'Logs Explorer';
  if (pathname.startsWith('/logs/')) return 'Log Detail';
  return 'Dashboard';
}

function getBreadcrumbs(pathname) {
  const crumbs = [{ label: 'Dashboard', path: '/' }];
  if (pathname === '/logs') {
    crumbs.push({ label: 'Logs Explorer', path: '/logs' });
  } else if (pathname.startsWith('/logs/')) {
    crumbs.push({ label: 'Logs Explorer', path: '/logs' });
    crumbs.push({ label: 'Detail', path: pathname });
  }
  return crumbs;
}

export default function Layout() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const navigate = useNavigate();
  const location = useLocation();
  const { mode, toggleColorMode } = useColorMode();

  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const drawerWidth = collapsed ? DRAWER_COLLAPSED : DRAWER_WIDTH;
  const pageTitle = getPageTitle(location.pathname);
  const breadcrumbs = getBreadcrumbs(location.pathname);

  const isActive = (path) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  const drawerContent = (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        py: 1,
      }}
    >
      {/* Brand */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          px: collapsed ? 1.5 : 2.5,
          py: 2,
          justifyContent: collapsed ? 'center' : 'flex-start',
        }}
      >
        <Box
          sx={{
            width: 36,
            height: 36,
            borderRadius: '10px',
            bgcolor: 'primary.main',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <BrandIcon sx={{ color: '#fff', fontSize: 20 }} />
        </Box>
        {!collapsed && (
          <Typography
            variant="h6"
            noWrap
            sx={{ fontWeight: 700, fontSize: '0.9375rem', mb: 0 }}
          >
            CROssBAR Logs
          </Typography>
        )}
      </Box>

      <Divider sx={{ mx: collapsed ? 1 : 2, mb: 1 }} />

      {/* Navigation */}
      <List sx={{ flex: 1, px: collapsed ? 0.5 : 1 }}>
        {NAV_ITEMS.map((item) => {
          const active = isActive(item.path);
          return (
            <Tooltip
              key={item.path}
              title={collapsed ? item.label : ''}
              placement="right"
              arrow
            >
              <ListItemButton
                onClick={() => {
                  navigate(item.path);
                  if (isMobile) setMobileOpen(false);
                }}
                sx={{
                  borderRadius: '8px',
                  mb: 0.5,
                  mx: collapsed ? 0.5 : 0,
                  px: collapsed ? 1.5 : 2,
                  minHeight: 44,
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  bgcolor: active ? 'action.selected' : 'transparent',
                  '&:hover': { bgcolor: active ? 'action.selected' : 'action.hover' },
                }}
              >
                <ListItemIcon
                  sx={{
                    minWidth: collapsed ? 0 : 36,
                    color: active ? 'primary.main' : 'text.secondary',
                    justifyContent: 'center',
                  }}
                >
                  {item.icon}
                </ListItemIcon>
                {!collapsed && (
                  <ListItemText
                    primary={item.label}
                    primaryTypographyProps={{
                      fontSize: '0.8125rem',
                      fontWeight: active ? 600 : 400,
                      color: active ? 'text.primary' : 'text.secondary',
                    }}
                  />
                )}
              </ListItemButton>
            </Tooltip>
          );
        })}
      </List>

      {/* Bottom actions */}
      <Divider sx={{ mx: collapsed ? 1 : 2, mb: 1 }} />
      <Box sx={{ px: collapsed ? 0.5 : 1, pb: 1 }}>
        <Tooltip title={mode === 'dark' ? 'Light mode' : 'Dark mode'} placement="right" arrow>
          <ListItemButton
            onClick={toggleColorMode}
            sx={{
              borderRadius: '8px',
              mx: collapsed ? 0.5 : 0,
              px: collapsed ? 1.5 : 2,
              minHeight: 44,
              justifyContent: collapsed ? 'center' : 'flex-start',
            }}
          >
            <ListItemIcon
              sx={{ minWidth: collapsed ? 0 : 36, justifyContent: 'center', color: 'text.secondary' }}
            >
              {mode === 'dark' ? <LightModeIcon /> : <DarkModeIcon />}
            </ListItemIcon>
            {!collapsed && (
              <ListItemText
                primary={mode === 'dark' ? 'Light Mode' : 'Dark Mode'}
                primaryTypographyProps={{ fontSize: '0.8125rem', color: 'text.secondary' }}
              />
            )}
          </ListItemButton>
        </Tooltip>
      </Box>

      {/* Collapse toggle (desktop only) */}
      {!isMobile && (
        <Box sx={{ display: 'flex', justifyContent: 'center', pb: 1 }}>
          <IconButton size="small" onClick={() => setCollapsed(!collapsed)}>
            {collapsed ? <ExpandIcon fontSize="small" /> : <CollapseIcon fontSize="small" />}
          </IconButton>
        </Box>
      )}
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* Sidebar */}
      {isMobile ? (
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            '& .MuiDrawer-paper': {
              width: DRAWER_WIDTH,
              bgcolor: 'background.paper',
              borderRight: 'none',
            },
          }}
        >
          {drawerContent}
        </Drawer>
      ) : (
        <Drawer
          variant="permanent"
          sx={{
            width: drawerWidth,
            flexShrink: 0,
            transition: 'width 0.2s ease',
            '& .MuiDrawer-paper': {
              width: drawerWidth,
              transition: 'width 0.2s ease',
              bgcolor: 'background.paper',
              borderRight: (t) =>
                `1px solid ${t.palette.divider}`,
              overflowX: 'hidden',
            },
          }}
        >
          {drawerContent}
        </Drawer>
      )}

      {/* Main content */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          display: 'flex',
          flexDirection: 'column',
          minWidth: 0,
        }}
      >
        {/* Top bar */}
        <AppBar
          position="sticky"
          elevation={0}
          sx={{
            bgcolor: 'background.default',
            borderBottom: (t) => `1px solid ${t.palette.divider}`,
            color: 'text.primary',
          }}
        >
          <Toolbar sx={{ minHeight: '56px !important', px: { xs: 2, md: 3 } }}>
            {isMobile && (
              <IconButton
                edge="start"
                onClick={() => setMobileOpen(true)}
                sx={{ mr: 1.5 }}
              >
                <MenuIcon />
              </IconButton>
            )}
            <Box sx={{ flex: 1 }}>
              <Typography variant="h4" sx={{ mb: 0, lineHeight: 1 }}>
                {pageTitle}
              </Typography>
              <Breadcrumbs
                sx={{ mt: 0.25, '& .MuiBreadcrumbs-separator': { mx: 0.5 } }}
              >
                {breadcrumbs.map((crumb, i) => {
                  const isLast = i === breadcrumbs.length - 1;
                  return isLast ? (
                    <Typography key={crumb.path} variant="caption" color="text.secondary">
                      {crumb.label}
                    </Typography>
                  ) : (
                    <MuiLink
                      key={crumb.path}
                      component="button"
                      variant="caption"
                      underline="hover"
                      color="text.secondary"
                      onClick={() => navigate(crumb.path)}
                      sx={{ cursor: 'pointer' }}
                    >
                      {crumb.label}
                    </MuiLink>
                  );
                })}
              </Breadcrumbs>
            </Box>
          </Toolbar>
        </AppBar>

        {/* Page content */}
        <Box sx={{ flex: 1, p: { xs: 2, md: 3 }, overflow: 'auto' }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
