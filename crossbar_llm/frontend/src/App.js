import React, { useState, useEffect, useCallback } from 'react';
import { 
  ThemeProvider, 
  CssBaseline, 
  Box, 
  Container, 
  Typography, 
  Button, 
  IconButton,
  Drawer,
  AppBar,
  Toolbar,
  Divider,
  useMediaQuery,
  Paper,
  Fade,
  Avatar,
  Tooltip,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemButton
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';
import MenuIcon from '@mui/icons-material/Menu';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import SecurityOutlinedIcon from '@mui/icons-material/SecurityOutlined';
import ChatOutlinedIcon from '@mui/icons-material/ChatOutlined';
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined';
import HomeOutlinedIcon from '@mui/icons-material/HomeOutlined';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { getTheme } from './theme';
import QueryInput from './components/QueryInput';
import ResultsDisplay from './components/ResultsDisplay';
import About from './components/About';
import VectorSearch from './components/VectorSearch';
import LatestQueries from './components/LatestQueries';
import Home from './components/Home';
import axios, { refreshCsrfToken } from './services/api';

function App() {
  const [tabValue, setTabValue] = useState('home');
  const [queryResult, setQueryResult] = useState(null);
  const [executionResult, setExecutionResult] = useState(null);
  const [realtimeLogs, setRealtimeLogs] = useState('');
  const [showAboutModal, setShowAboutModal] = useState(false);
  const [latestQueries, setLatestQueries] = useState([]);
  const [selectedQuery, setSelectedQuery] = useState(null);
  const [question, setQuestion] = useState('');
  const [provider, setProvider] = useState('');
  const [llmType, setLlmType] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerVisible, setDrawerVisible] = useState(false); // Default to false, will be updated in useEffect
  const [clientIP, setClientIP] = useState('');
  const [mode, setMode] = useState(() => {
    const savedMode = localStorage.getItem('theme-mode');
    if (savedMode) {
      return savedMode;
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  const theme = React.useMemo(() => getTheme(mode), [mode]);
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  // Update drawer visibility based on screen size
  useEffect(() => {
    setDrawerVisible(!isMobile);
  }, [isMobile]);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (e) => {
      if (!localStorage.getItem('theme-mode')) {
        setMode(e.matches ? 'dark' : 'light');
      }
    };
    mediaQuery.addListener(handleChange);
    return () => mediaQuery.removeListener(handleChange);
  }, []);

  useEffect(() => {
    // Initial token fetch
    refreshCsrfToken();

    // Set up periodic token refresh (every 15 minutes)
    const tokenRefreshInterval = setInterval(() => {
      console.log('Refreshing CSRF token periodically');
      refreshCsrfToken();
    }, 15 * 60 * 1000); // 15 minutes

    const navigationType = performance.getEntriesByType('navigation')[0].type;

    if ((navigationType === 'navigate' || navigationType === 'reload') && !localStorage.getItem('hasVisited')) {
      setShowAboutModal(true);
      localStorage.setItem('hasVisited', 'true');
    }
    
    // Always set the tab to home when the app loads
    setTabValue('home');
    
    // Check if there's a prefilled query from the home page
    const prefillQuery = localStorage.getItem('prefillQuery');
    if (prefillQuery) {
      setQuestion(prefillQuery);
      localStorage.removeItem('prefillQuery');
    }
    
    // Clean up on unmount
    return () => {
      clearInterval(tokenRefreshInterval);
    };
  }, []);

  // Fetch client IP on app startup
  useEffect(() => {
    const fetchClientIP = async () => {
      // Check sessionStorage first
      const storedIP = sessionStorage.getItem('client_ip');
      if (storedIP) {
        setClientIP(storedIP);
        return;
      }

      try {
        const response = await fetch('https://api.ipify.org?format=json');
        if (response.ok) {
          const data = await response.json();
          if (data.ip) {
            setClientIP(data.ip);
            sessionStorage.setItem('client_ip', data.ip);
          }
        }
      } catch (error) {
        console.error('Error fetching client IP:', error);
      }
    };

    fetchClientIP();
  }, []);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
    setQueryResult(null);
    setExecutionResult(null);
    setRealtimeLogs('');
    setDrawerOpen(false);
    
    // Reset question field when changing tabs
    setQuestion('');
    
    // Check if there's a prefilled query when switching to the query tab
    if (newValue === 'query') {
      const prefillQuery = localStorage.getItem('prefillQuery');
      if (prefillQuery) {
        setQuestion(prefillQuery);
        localStorage.removeItem('prefillQuery');
      }
    }
  };

  const handleCloseModal = () => {
    setShowAboutModal(false);
  };

  const addLatestQuery = (queryDetails) => {
    const now = new Date(queryDetails.timestamp).getTime();
    const isDuplicate = latestQueries.some(q => {
      const queryTime = new Date(q.timestamp).getTime();
      const timeDiff = now - queryTime;
      return q.question === queryDetails.question && 
             q.queryType === queryDetails.queryType &&
             timeDiff < 2000; // Less than 2 seconds
    });
    
    // If it's a duplicate, don't add it
    if (isDuplicate) return;
    
    if (latestQueries.length >= 10) {
      setLatestQueries([...latestQueries.slice(1), queryDetails]);
    } else {
      setLatestQueries([...latestQueries, queryDetails]);
    }
  }

  const handleSelectQuery = (query) => {
    setSelectedQuery(query);
    setQuestion(query.question);
    
    // If it's a generated query, set the query result
    if (query.queryType === 'generated') {
      setQueryResult(query.query);
      setExecutionResult(null);
    } 
    // If it's a run query, set both query result and execution result
    else if (query.queryType === 'run') {
      setQueryResult(query.query);
      setExecutionResult({
        response: query.response,
        result: [] // We don't store the result in latestQueries, so use an empty array
      });
    }
  }

  const toggleColorMode = () => {
    const newMode = mode === 'light' ? 'dark' : 'light';
    setMode(newMode);
    localStorage.setItem('theme-mode', newMode);
  };

  const toggleDrawer = () => {
    setDrawerOpen(!drawerOpen);
  };

  const toggleDrawerVisibility = () => {
    setDrawerVisible(!drawerVisible);
  };

  const renderTabContent = () => {
    switch(tabValue) {
      case 'home':
        return (
          <Fade in={true} timeout={500}>
            <Box>
              <Home handleTabChange={handleTabChange} />
            </Box>
          </Fade>
        );
      case 'query':
        return (
          <Fade in={true} timeout={500}>
            <Box>
              <QueryInput
                setQueryResult={setQueryResult}
                setExecutionResult={setExecutionResult}
                setRealtimeLogs={setRealtimeLogs}
                addLatestQuery={addLatestQuery}
                provider={provider}
                setProvider={setProvider}
                llmType={llmType}
                setLlmType={setLlmType}
                apiKey={apiKey}
                setApiKey={setApiKey}
                question={question}
                setQuestion={setQuestion}
              />
              <ResultsDisplay
                queryResult={queryResult}
                executionResult={executionResult}
                realtimeLogs={realtimeLogs}
              />
              <LatestQueries 
                queries={latestQueries} 
                onSelectQuery={handleSelectQuery}
              />
            </Box>
          </Fade>
        );
      case 'vectorSearch':
        return (
          <Fade in={true} timeout={500}>
            <Box>
              <VectorSearch
                setQueryResult={setQueryResult}
                setExecutionResult={setExecutionResult}
                setRealtimeLogs={setRealtimeLogs}
                addLatestQuery={addLatestQuery}
                provider={provider}
                setProvider={setProvider}
                llmType={llmType}
                setLlmType={setLlmType}
                apiKey={apiKey}
                setApiKey={setApiKey}
                question={question}
                setQuestion={setQuestion}
              />
              <ResultsDisplay
                queryResult={queryResult}
                executionResult={executionResult}
                realtimeLogs={realtimeLogs}
              />
              <LatestQueries 
                queries={latestQueries} 
                onSelectQuery={handleSelectQuery}
              />
            </Box>
          </Fade>
        );
      case 'about':
        return (
          <Fade in={true} timeout={500}>
            <Box>
              <About />
            </Box>
          </Fade>
        );
      default:
        return null;
    }
  };

  const drawer = (
    <Box sx={{ width: 280, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center', 
        py: 2,
        borderBottom: theme => `1px solid ${theme.palette.divider}`
      }}>
        <Typography variant="h6" sx={{ 
          fontWeight: 600, 
          fontFamily: "'Poppins', 'Roboto', sans-serif",
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
      
      <Box sx={{ flexGrow: 1, px: 2, pt: 1.5, overflowY: 'auto' }}>
        <List sx={{ p: 0, mt: 0 }}>
          <ListItem disablePadding sx={{ mt: 0 }}>
            <ListItemButton 
              onClick={() => handleTabChange(null, 'home')}
              selected={tabValue === 'home'}
              sx={{ 
                borderRadius: '12px',
                py: 1.5,
                '&.Mui-selected': {
                  backgroundColor: theme => theme.palette.mode === 'dark' 
                    ? 'rgba(100, 181, 246, 0.15)' 
                    : 'rgba(0, 113, 227, 0.08)',
                  '&:hover': {
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? 'rgba(100, 181, 246, 0.2)' 
                      : 'rgba(0, 113, 227, 0.12)',
                  }
                }
              }}
            >
              <ListItemIcon sx={{ 
                minWidth: 40,
                color: tabValue === 'home' 
                  ? (theme.palette.mode === 'dark' ? '#64B5F6' : '#0071e3') 
                  : 'inherit'
              }}>
                <HomeOutlinedIcon />
              </ListItemIcon>
              <ListItemText 
                primary="Home" 
                primaryTypographyProps={{ 
                  fontWeight: tabValue === 'home' ? 600 : 400,
                  fontFamily: "'Poppins', 'Roboto', sans-serif",
                  color: tabValue === 'home' 
                    ? (theme.palette.mode === 'dark' ? '#64B5F6' : '#0071e3') 
                    : 'inherit'
                }}
              />
            </ListItemButton>
          </ListItem>
          
          <ListItem disablePadding sx={{ mb: 1 }}>
            <ListItemButton 
              onClick={() => handleTabChange(null, 'query')}
              selected={tabValue === 'query'}
              sx={{ 
                borderRadius: '12px',
                py: 1.5,
                '&.Mui-selected': {
                  backgroundColor: theme => theme.palette.mode === 'dark' 
                    ? 'rgba(100, 181, 246, 0.15)' 
                    : 'rgba(0, 113, 227, 0.08)',
                  '&:hover': {
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? 'rgba(100, 181, 246, 0.2)' 
                      : 'rgba(0, 113, 227, 0.12)',
                  }
                }
              }}
            >
              <ListItemIcon sx={{ 
                minWidth: 40,
                color: tabValue === 'query' 
                  ? (theme.palette.mode === 'dark' ? '#64B5F6' : '#0071e3') 
                  : 'inherit'
              }}>
                <ChatOutlinedIcon />
              </ListItemIcon>
              <ListItemText 
                primary="Graph Explorer" 
                primaryTypographyProps={{ 
                  fontWeight: tabValue === 'query' ? 600 : 400,
                  fontFamily: "'Poppins', 'Roboto', sans-serif",
                  color: tabValue === 'query' 
                    ? (theme.palette.mode === 'dark' ? '#64B5F6' : '#0071e3') 
                    : 'inherit'
                }}
              />
            </ListItemButton>
          </ListItem>
          
          <ListItem disablePadding sx={{ mb: 1 }}>
            <ListItemButton 
              onClick={() => handleTabChange(null, 'vectorSearch')}
              selected={tabValue === 'vectorSearch'}
              sx={{ 
                borderRadius: '12px',
                py: 1.5,
                '&.Mui-selected': {
                  backgroundColor: theme => theme.palette.mode === 'dark' 
                    ? 'rgba(100, 181, 246, 0.15)' 
                    : 'rgba(0, 113, 227, 0.08)',
                  '&:hover': {
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? 'rgba(100, 181, 246, 0.2)' 
                      : 'rgba(0, 113, 227, 0.12)',
                  }
                }
              }}
            >
              <ListItemIcon sx={{ 
                minWidth: 40,
                color: tabValue === 'vectorSearch' 
                  ? (theme.palette.mode === 'dark' ? '#64B5F6' : '#0071e3') 
                  : 'inherit'
              }}>
                <SearchOutlinedIcon />
              </ListItemIcon>
              <ListItemText 
                primary="Semantic Search" 
                primaryTypographyProps={{ 
                  fontWeight: tabValue === 'vectorSearch' ? 600 : 400,
                  fontFamily: "'Poppins', 'Roboto', sans-serif",
                  color: tabValue === 'vectorSearch' 
                    ? (theme.palette.mode === 'dark' ? '#64B5F6' : '#0071e3') 
                    : 'inherit'
                }}
              />
            </ListItemButton>
          </ListItem>
          
          <ListItem disablePadding>
            <ListItemButton 
              onClick={() => handleTabChange(null, 'about')}
              selected={tabValue === 'about'}
              sx={{ 
                borderRadius: '12px',
                py: 1.5,
                '&.Mui-selected': {
                  backgroundColor: theme => theme.palette.mode === 'dark' 
                    ? 'rgba(100, 181, 246, 0.15)' 
                    : 'rgba(0, 113, 227, 0.08)',
                  '&:hover': {
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? 'rgba(100, 181, 246, 0.2)' 
                      : 'rgba(0, 113, 227, 0.12)',
                  }
                }
              }}
            >
              <ListItemIcon sx={{ 
                minWidth: 40,
                color: tabValue === 'about' 
                  ? (theme.palette.mode === 'dark' ? '#64B5F6' : '#0071e3') 
                  : 'inherit'
              }}>
                <InfoOutlinedIcon />
              </ListItemIcon>
              <ListItemText 
                primary="About" 
                primaryTypographyProps={{ 
                  fontWeight: tabValue === 'about' ? 600 : 400,
                  fontFamily: "'Poppins', 'Roboto', sans-serif",
                  color: tabValue === 'about' 
                    ? (theme.palette.mode === 'dark' ? '#64B5F6' : '#0071e3') 
                    : 'inherit'
                }}
              />
            </ListItemButton>
          </ListItem>
        </List>
      </Box>
      
      <Box sx={{ 
        p: 2, 
        borderTop: theme => `1px solid ${theme.palette.divider}`,
        display: 'flex',
        justifyContent: 'center'
      }}>
        <Typography variant="caption" sx={{ 
          color: 'text.secondary', 
          textAlign: 'center',
          fontFamily: "'Poppins', 'Roboto', sans-serif"
        }}>
          CROssBAR-LLM v1.0
        </Typography>
      </Box>
    </Box>
  );

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ 
        display: 'flex', 
        minHeight: '100vh',
        background: theme => theme.palette.mode === 'dark' 
          ? 'linear-gradient(135deg, #1c1c1e 0%, #2c2c2e 100%)' 
          : 'linear-gradient(135deg, #f5f5f7 0%, #ffffff 100%)'
      }}>
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
              onClick={() => handleTabChange(null, 'home')}>
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
                  onClick={toggleDrawerVisibility} 
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
                  onClick={toggleColorMode} 
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
        
        {drawerVisible && (
          <Drawer
            variant="permanent"
            open={true}
            sx={{
              width: 280,
              flexShrink: 0,
              [`& .MuiDrawer-paper`]: { 
                width: 280,
                boxSizing: 'border-box',
                border: 'none',
                background: theme => theme.palette.mode === 'dark' 
                  ? 'rgba(28, 28, 30, 0.8)' 
                  : 'rgba(255, 255, 255, 0.8)',
                backdropFilter: 'blur(10px)',
              }
            }}
          >
            {drawer}
          </Drawer>
        )}
        
        <Box
          component="main"
          sx={{
            flexGrow: 1,
            p: 3,
            width: { xs: '100%', md: drawerVisible ? `calc(100% - 280px)` : '100%' },
            mt: 6,
            mb: 4,
            maxWidth: drawerVisible ? '1200px' : '1480px',
            mx: 'auto',
            display: 'flex',
            flexDirection: 'column',
            transition: 'all 0.3s ease-in-out'
          }}
        >
          <Box sx={{ flexGrow: 1 }}>
            {renderTabContent()}
            
            {showAboutModal && (
              <About onClose={handleCloseModal} />
            )}
          </Box>
          
          {/* Privacy Banner */}
          <Paper 
            elevation={0}
            sx={{ 
              mt: 4,
              p: 2,
              backgroundColor: theme => theme.palette.mode === 'dark' 
                ? 'rgba(100, 181, 246, 0.08)' 
                : 'rgba(0, 113, 227, 0.04)',
              borderRadius: '12px',
              border: theme => `1px solid ${theme.palette.mode === 'dark' 
                ? 'rgba(100, 181, 246, 0.2)' 
                : 'rgba(0, 113, 227, 0.1)'}`,
              display: 'flex',
              alignItems: 'flex-start',
              gap: 1.5
            }}
          >
            <SecurityOutlinedIcon 
              sx={{ 
                fontSize: 20, 
                color: theme => theme.palette.mode === 'dark' ? '#64B5F6' : '#0071e3',
                mt: 0.25,
                flexShrink: 0
              }} 
            />
            <Typography 
              variant="caption" 
              sx={{ 
                color: 'text.secondary',
                lineHeight: 1.6,
                fontFamily: "'Poppins', 'Roboto', sans-serif"
              }}
            >
              We save user queries and outputs, but remove all identifiable data once the session is finished. 
              Data is never used for model training. Data is stored on the CROssBAR v2 server. 
              We may analyze data globally to improve the user experience.
            </Typography>
          </Paper>

          <Box sx={{ 
            mt: 2,
            pt: 2, 
            borderTop: theme => `1px solid ${theme.palette.divider}`,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              © {new Date().getFullYear()} CROssBAR
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              <a href="https://www.flaticon.com/free-icons/chatbot" title="chatbot icons" style={{ color: 'inherit', textDecoration: 'none' }}>
                Chatbot icons created by rukanicon - Flaticon
              </a>
            </Typography>
          </Box>
        </Box>
      </Box>
    </ThemeProvider>
  );
}

export default App;