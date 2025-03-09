import React, { useState } from 'react';
import { 
  Box, 
  Typography, 
  Button, 
  Container, 
  Grid, 
  Paper, 
  TextField, 
  useTheme, 
  alpha,
  Chip,
  IconButton,
  Fade,
  CircularProgress,
  InputAdornment,
  Alert
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import BiotechOutlinedIcon from '@mui/icons-material/BiotechOutlined';
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';
import QuestionAnswerOutlinedIcon from '@mui/icons-material/QuestionAnswerOutlined';
import CodeOutlinedIcon from '@mui/icons-material/CodeOutlined';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { docco, dracula } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import axios from '../services/api';

// Network Graph SVG Component
const NetworkGraphSVG = () => (
  <svg width="500" height="500" viewBox="0 0 500 500" xmlns="http://www.w3.org/2000/svg">
    <defs>
      {/* Enhanced gradients with smoother transitions */}
      <linearGradient id="nodeGradient1" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#1E88E5" stopOpacity="0.95"/>
        <stop offset="100%" stopColor="#1565C0" stopOpacity="0.95"/>
      </linearGradient>
      <linearGradient id="nodeGradient2" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#7E57C2" stopOpacity="0.95"/>
        <stop offset="100%" stopColor="#5E35B1" stopOpacity="0.95"/>
      </linearGradient>
      <linearGradient id="nodeGradient3" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#039BE5" stopOpacity="0.95"/>
        <stop offset="100%" stopColor="#0288D1" stopOpacity="0.95"/>
      </linearGradient>
      <linearGradient id="nodeGradient4" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#5C6BC0" stopOpacity="0.95"/>
        <stop offset="100%" stopColor="#3949AB" stopOpacity="0.95"/>
      </linearGradient>
      <linearGradient id="nodeGradient5" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#43A047" stopOpacity="0.95"/>
        <stop offset="100%" stopColor="#2E7D32" stopOpacity="0.95"/>
      </linearGradient>
      
      {/* Connection gradients */}
      <linearGradient id="connectionGradient1" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stopColor="#1E88E5" stopOpacity="0.5"/>
        <stop offset="100%" stopColor="#5E35B1" stopOpacity="0.5"/>
      </linearGradient>
      <linearGradient id="connectionGradient2" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stopColor="#7E57C2" stopOpacity="0.5"/>
        <stop offset="100%" stopColor="#0288D1" stopOpacity="0.5"/>
      </linearGradient>
      
      {/* Enhanced glow effect */}
      <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="3" result="blur"/>
        <feComposite in="SourceGraphic" in2="blur" operator="over"/>
      </filter>
      
      {/* Node shadow effect */}
      <filter id="nodeShadow" x="-50%" y="-50%" width="200%" height="200%">
        <feDropShadow dx="0" dy="1" stdDeviation="2" floodColor="#000" floodOpacity="0.3"/>
      </filter>
      
      {/* Text shadow for better readability */}
      <filter id="textShadow" x="-50%" y="-50%" width="200%" height="200%">
        <feDropShadow dx="0" dy="0" stdDeviation="1" floodColor="#000" floodOpacity="0.5"/>
      </filter>
    </defs>
    
    {/* Background grid for professional look */}
    <g id="grid" opacity="0.1">
      <path d="M 40 0 V 500 M 90 0 V 500 M 140 0 V 500 M 190 0 V 500 M 240 0 V 500 M 290 0 V 500 M 340 0 V 500 M 390 0 V 500 M 440 0 V 500 M 490 0 V 500" stroke="#5C6BC0" strokeWidth="0.5"/>
      <path d="M 0 40 H 500 M 0 90 H 500 M 0 140 H 500 M 0 190 H 500 M 0 240 H 500 M 0 290 H 500 M 0 340 H 500 M 0 390 H 500 M 0 440 H 500 M 0 490 H 500" stroke="#5C6BC0" strokeWidth="0.5"/>
    </g>
    
    {/* Connections */}
    <g id="connections">
      {/* Primary connections from center */}
      <path d="M 250 250 L 125 125" stroke="url(#connectionGradient1)" strokeWidth="2.5" strokeLinecap="round" strokeOpacity="0.7">
        <animate attributeName="stroke-opacity" values="0.7;0.3;0.7" dur="4s" repeatCount="indefinite"/>
      </path>
      <path d="M 250 250 L 375 125" stroke="url(#connectionGradient1)" strokeWidth="2.5" strokeLinecap="round" strokeOpacity="0.7">
        <animate attributeName="stroke-opacity" values="0.7;0.3;0.7" dur="4.2s" repeatCount="indefinite"/>
      </path>
      <path d="M 250 250 L 125 375" stroke="url(#connectionGradient1)" strokeWidth="2.5" strokeLinecap="round" strokeOpacity="0.7">
        <animate attributeName="stroke-opacity" values="0.7;0.3;0.7" dur="4.4s" repeatCount="indefinite"/>
      </path>
      <path d="M 250 250 L 375 375" stroke="url(#connectionGradient1)" strokeWidth="2.5" strokeLinecap="round" strokeOpacity="0.7">
        <animate attributeName="stroke-opacity" values="0.7;0.3;0.7" dur="4.6s" repeatCount="indefinite"/>
      </path>
      
      {/* Secondary connections between corner nodes */}
      <path d="M 125 125 C 180 110, 320 110, 375 125" stroke="url(#connectionGradient2)" strokeWidth="1.8" strokeLinecap="round" strokeOpacity="0.5" fill="none"/>
      <path d="M 125 125 C 110 180, 110 320, 125 375" stroke="url(#connectionGradient2)" strokeWidth="1.8" strokeLinecap="round" strokeOpacity="0.5" fill="none"/>
      <path d="M 375 125 C 390 180, 390 320, 375 375" stroke="url(#connectionGradient2)" strokeWidth="1.8" strokeLinecap="round" strokeOpacity="0.5" fill="none"/>
      <path d="M 125 375 C 180 390, 320 390, 375 375" stroke="url(#connectionGradient2)" strokeWidth="1.8" strokeLinecap="round" strokeOpacity="0.5" fill="none"/>
      
      {/* Connections to mid nodes */}
      <path d="M 185 185 L 125 125" stroke="#5C6BC0" strokeWidth="1.5" strokeOpacity="0.5" strokeLinecap="round"/>
      <path d="M 185 185 L 250 250" stroke="#5C6BC0" strokeWidth="1.5" strokeOpacity="0.5" strokeLinecap="round"/>
      <path d="M 315 185 L 375 125" stroke="#5C6BC0" strokeWidth="1.5" strokeOpacity="0.5" strokeLinecap="round"/>
      <path d="M 315 185 L 250 250" stroke="#5C6BC0" strokeWidth="1.5" strokeOpacity="0.5" strokeLinecap="round"/>
      <path d="M 185 315 L 125 375" stroke="#5C6BC0" strokeWidth="1.5" strokeOpacity="0.5" strokeLinecap="round"/>
      <path d="M 185 315 L 250 250" stroke="#5C6BC0" strokeWidth="1.5" strokeOpacity="0.5" strokeLinecap="round"/>
      <path d="M 315 315 L 375 375" stroke="#5C6BC0" strokeWidth="1.5" strokeOpacity="0.5" strokeLinecap="round"/>
      <path d="M 315 315 L 250 250" stroke="#5C6BC0" strokeWidth="1.5" strokeOpacity="0.5" strokeLinecap="round"/>
      
      {/* Cross connections between mid nodes */}
      <path d="M 185 185 C 220 180, 280 180, 315 185" stroke="#5C6BC0" strokeWidth="1.5" strokeOpacity="0.4" strokeLinecap="round" fill="none"/>
      <path d="M 185 315 C 220 320, 280 320, 315 315" stroke="#5C6BC0" strokeWidth="1.5" strokeOpacity="0.4" strokeLinecap="round" fill="none"/>
    </g>
    
    {/* Nodes */}
    <g id="nodes">
      {/* Mid-point nodes (Secondary entities) - Drawn first so they appear behind */}
      <g className="node secondary-node">
        <circle cx="185" cy="185" r="18" fill="url(#nodeGradient1)" filter="url(#nodeShadow)"/>
        <foreignObject x="159" y="175" width="52" height="20">
          <div xmlns="http://www.w3.org/1999/xhtml" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Arial, sans-serif', fontSize: '10px', fontWeight: 500, color: 'white', textAlign: 'center' }}>SNP</div>
        </foreignObject>
      </g>
      
      <g className="node secondary-node">
        <circle cx="315" cy="185" r="18" fill="url(#nodeGradient2)" filter="url(#nodeShadow)"/>
        <foreignObject x="289" y="175" width="52" height="20">
          <div xmlns="http://www.w3.org/1999/xhtml" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Arial, sans-serif', fontSize: '10px', fontWeight: 500, color: 'white', textAlign: 'center' }}>MOA</div>
        </foreignObject>
      </g>
      
      <g className="node secondary-node">
        <circle cx="185" cy="315" r="18" fill="url(#nodeGradient3)" filter="url(#nodeShadow)"/>
        <foreignObject x="151" y="305" width="68" height="20">
          <div xmlns="http://www.w3.org/1999/xhtml" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Arial, sans-serif', fontSize: '10px', fontWeight: 500, color: 'white', textAlign: 'center' }}>Symptom</div>
        </foreignObject>
      </g>
      
      <g className="node secondary-node">
        <circle cx="315" cy="315" r="18" fill="url(#nodeGradient4)" filter="url(#nodeShadow)"/>
        <foreignObject x="281" y="305" width="68" height="20">
          <div xmlns="http://www.w3.org/1999/xhtml" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Arial, sans-serif', fontSize: '10px', fontWeight: 500, color: 'white', textAlign: 'center' }}>Pathway</div>
        </foreignObject>
      </g>
      
      {/* Corner nodes (Main entities) */}
      <g className="node primary-node">
        <circle cx="125" cy="125" r="28" fill="url(#nodeGradient2)" filter="url(#nodeShadow)"/>
        <foreignObject x="97" y="115" width="56" height="20">
          <div xmlns="http://www.w3.org/1999/xhtml" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Arial, sans-serif', fontSize: '14px', fontWeight: 600, color: 'white', textAlign: 'center' }}>Gene</div>
        </foreignObject>
      </g>
      
      <g className="node primary-node">
        <circle cx="375" cy="125" r="28" fill="url(#nodeGradient3)" filter="url(#nodeShadow)"/>
        <foreignObject x="347" y="115" width="56" height="20">
          <div xmlns="http://www.w3.org/1999/xhtml" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Arial, sans-serif', fontSize: '14px', fontWeight: 600, color: 'white', textAlign: 'center' }}>Drug</div>
        </foreignObject>
      </g>
      
      <g className="node primary-node">
        <circle cx="125" cy="375" r="28" fill="url(#nodeGradient4)" filter="url(#nodeShadow)"/>
        <foreignObject x="91" y="365" width="68" height="20">
          <div xmlns="http://www.w3.org/1999/xhtml" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Arial, sans-serif', fontSize: '14px', fontWeight: 600, color: 'white', textAlign: 'center' }}>Disease</div>
        </foreignObject>
      </g>
      
      <g className="node primary-node">
        <circle cx="375" cy="375" r="28" fill="url(#nodeGradient5)" filter="url(#nodeShadow)"/>
        <foreignObject x="341" y="365" width="68" height="20">
          <div xmlns="http://www.w3.org/1999/xhtml" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Arial, sans-serif', fontSize: '14px', fontWeight: 600, color: 'white', textAlign: 'center' }}>Protein</div>
        </foreignObject>
      </g>
      
      {/* Center node (Main hub) - Draw this last so it's on top */}
      <g className="node central-node">
        <circle cx="250" cy="250" r="32" fill="url(#nodeGradient1)" filter="url(#nodeShadow)"/>
        <foreignObject x="218" y="235" width="64" height="30">
          <div xmlns="http://www.w3.org/1999/xhtml" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Arial, sans-serif', fontSize: '16px', fontWeight: 700, color: 'white', textAlign: 'center' }}>LLM</div>
        </foreignObject>
      </g>
    </g>
    
    {/* Animated pulse effect for center node */}
    <circle cx="250" cy="250" r="20" fill="none" stroke="#1E88E5" strokeWidth="3" opacity="0.7">
      <animate attributeName="r" values="32;60" dur="3s" repeatCount="indefinite" />
      <animate attributeName="opacity" values="0.7;0" dur="3s" repeatCount="indefinite" />
    </circle>
    
    {/* Subtle particle effects */}
    <g id="particles" opacity="0.6">
      <circle cx="235" cy="235" r="2" fill="#ffffff">
        <animate attributeName="cx" values="235;265;250" dur="15s" repeatCount="indefinite" />
        <animate attributeName="cy" values="235;265;250" dur="15s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.6;0.2;0.6" dur="15s" repeatCount="indefinite" />
      </circle>
      <circle cx="265" cy="235" r="1.5" fill="#ffffff">
        <animate attributeName="cx" values="265;250;235" dur="12s" repeatCount="indefinite" />
        <animate attributeName="cy" values="235;265;250" dur="12s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.5;0.1;0.5" dur="12s" repeatCount="indefinite" />
      </circle>
      <circle cx="250" cy="265" r="1" fill="#ffffff">
        <animate attributeName="cx" values="250;235;265" dur="10s" repeatCount="indefinite" />
        <animate attributeName="cy" values="265;235;250" dur="10s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.4;0.1;0.4" dur="10s" repeatCount="indefinite" />
      </circle>
    </g>
  </svg>
);

function Home({ handleTabChange }) {
  const theme = useTheme();
  const [demoQuery, setDemoQuery] = useState('');
  const [demoResponse, setDemoResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const syntaxTheme = theme.palette.mode === 'dark' ? dracula : docco;

  const handleDemoSubmit = async (e) => {
    e.preventDefault();
    if (!demoQuery.trim()) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const response = await axios.post('/generate_query/', {
        question: demoQuery,
        provider: 'Google',
        llm_type: 'gemini-2.0-flash',
        api_key: 'demo',
        verbose: false
      });
      
      setDemoResponse({
        query: response.data.query,
        question: demoQuery
      });
    } catch (err) {
      console.error('Error in demo query:', err);
      setError('An error occurred while processing your query. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const sampleQuestions = [
    "What drugs target the BRCA1 gene?",
    "Show me proteins associated with Alzheimer's disease",
    "Find pathways related to inflammation"
  ];

  const handleSampleClick = (question) => {
    setDemoQuery(question);
  };

  return (
    <Box sx={{ pb: 8 }}>
      {/* Hero Section */}
      <Box 
        sx={{ 
          background: theme => theme.palette.mode === 'dark' 
            ? 'linear-gradient(135deg, rgba(100, 181, 246, 0.2) 0%, rgba(179, 157, 219, 0.2) 100%)' 
            : 'linear-gradient(135deg, rgba(0, 113, 227, 0.05) 0%, rgba(94, 92, 230, 0.05) 100%)',
          py: { xs: 8, md: 12 },
          borderRadius: { xs: 0, md: '0 0 24px 24px' },
          mb: 6,
          position: 'relative',
          overflow: 'hidden'
        }}
      >
        <Container maxWidth="lg">
          <Grid container spacing={4} alignItems="center">
            <Grid item xs={12} md={7}>
              <Fade in={true} timeout={1000}>
                <Box>
                  <Typography 
                    variant="h1" 
                    sx={{ 
                      fontWeight: 700, 
                      fontSize: { xs: '2.5rem', md: '3.5rem' },
                      lineHeight: 1.2,
                      mb: 2,
                      background: theme => theme.palette.mode === 'dark' 
                        ? 'linear-gradient(90deg, #64B5F6 0%, #B39DDB 100%)' 
                        : 'linear-gradient(90deg, #0071e3 0%, #5e5ce6 100%)',
                      WebkitBackgroundClip: 'text',
                      WebkitTextFillColor: 'transparent',
                      letterSpacing: '-0.02em'
                    }}
                  >
                    CROssBAR LLM
                  </Typography>
                  <Typography 
                    variant="h5" 
                    sx={{ 
                      color: 'text.secondary', 
                      mb: 4, 
                      fontWeight: 400,
                      maxWidth: '600px',
                      lineHeight: 1.6
                    }}
                  >
                    Explore biomedical knowledge graphs using natural language and the power of large language models
                  </Typography>
                  <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                    <Button 
                      variant="contained" 
                      size="large"
                      onClick={() => handleTabChange(null, 'query')}
                      endIcon={<ArrowForwardIcon />}
                      sx={{ 
                        px: 4, 
                        py: 1.5,
                        fontSize: '1rem',
                        fontWeight: 600,
                        borderRadius: '12px',
                        background: theme => theme.palette.mode === 'dark' 
                          ? 'linear-gradient(90deg, #0071e3 0%, #5e5ce6 100%)' 
                          : 'linear-gradient(90deg, #0071e3 0%, #5e5ce6 100%)',
                        '&:hover': {
                          background: theme => theme.palette.mode === 'dark' 
                            ? 'linear-gradient(90deg, #0077ed 0%, #6a68f0 100%)' 
                            : 'linear-gradient(90deg, #0077ed 0%, #6a68f0 100%)',
                          transform: 'translateY(-2px)',
                          boxShadow: '0 6px 20px rgba(0, 113, 227, 0.3)'
                        },
                        transition: 'all 0.7s cubic-bezier(0.4, 0, 0.2, 1)'
                      }}
                    >
                      Start Querying
                    </Button>
                    <Button 
                      variant="outlined" 
                      size="large"
                      onClick={() => handleTabChange(null, 'about')}
                      sx={{ 
                        px: 4, 
                        py: 1.5,
                        fontSize: '1rem',
                        fontWeight: 600,
                        borderRadius: '12px',
                        borderWidth: '2px',
                        '&:hover': {
                          borderWidth: '2px',
                          transform: 'translateY(-2px)'
                        },
                        transition: 'all 0.7s cubic-bezier(0.4, 0, 0.2, 1)'
                      }}
                    >
                      Learn More
                    </Button>
                  </Box>
                </Box>
              </Fade>
            </Grid>
            <Grid item xs={12} md={5}>
              <Fade in={true} timeout={1500}>
                <Box 
                  sx={{ 
                    display: { xs: 'none', md: 'block' },
                    position: 'relative',
                    height: '400px'
                  }}
                >
                  <Box 
                    sx={{ 
                      position: 'absolute',
                      top: '50%',
                      left: '50%',
                      transform: 'translate(-50%, -50%)',
                      width: '400px',
                      height: '400px',
                      borderRadius: '50%',
                      background: theme => theme.palette.mode === 'dark' 
                        ? 'radial-gradient(circle, rgba(100, 181, 246, 0.2) 0%, rgba(179, 157, 219, 0.1) 70%, rgba(0,0,0,0) 100%)' 
                        : 'radial-gradient(circle, rgba(0, 113, 227, 0.1) 0%, rgba(94, 92, 230, 0.05) 70%, rgba(0,0,0,0) 100%)',
                      filter: 'blur(20px)',
                      zIndex: 0
                    }}
                  />
                  <Box 
                    sx={{ 
                      position: 'absolute',
                      top: '50%',
                      left: '50%',
                      transform: 'translate(-50%, -50%)',
                      width: '400px',
                      height: '400px',
                      zIndex: 1
                    }}
                  >
                    <NetworkGraphSVG />
                  </Box>
                </Box>
              </Fade>
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* Features Section */}
      <Container maxWidth="lg">
        <Box sx={{ mb: 8, textAlign: 'center' }}>
          <Typography 
            variant="h3" 
            sx={{ 
              fontWeight: 600, 
              mb: 2,
              letterSpacing: '-0.01em'
            }}
          >
            Key Features
          </Typography>
          <Typography 
            variant="body1" 
            sx={{ 
              color: 'text.secondary', 
              maxWidth: '700px', 
              mx: 'auto',
              mb: 6
            }}
          >
            CROssBAR LLM combines the power of large language models with biomedical knowledge graphs to enable natural language querying of complex data
          </Typography>

          <Grid container spacing={3}>
            <Grid item xs={12} sm={6} md={3}>
              <Fade in={true} timeout={1000} style={{ transitionDelay: '200ms' }}>
                <Button
                  fullWidth
                  onClick={() => handleTabChange(null, 'query')}
                  sx={{
                    p: 0,
                    textTransform: 'none',
                    borderRadius: '20px',
                    display: 'block',
                    transition: 'all 0.7s cubic-bezier(0.4, 0, 0.2, 1)',
                    '&:hover': {
                      transform: 'translateY(-2px)',
                      backgroundColor: 'transparent'
                    }
                  }}
                >
                  <Paper 
                    elevation={0} 
                    sx={{ 
                      p: 3, 
                      height: '100%',
                      borderRadius: '20px',
                      border: theme => `1px solid ${theme.palette.divider}`,
                      transition: 'all 0.7s cubic-bezier(0.4, 0, 0.2, 1)',
                      '&:hover': {
                        boxShadow: theme => theme.palette.mode === 'dark' 
                          ? `0 6px 20px rgba(0, 0, 0, 0.3), 0 0 15px ${alpha(theme.palette.primary.main, 0.5)}` 
                          : `0 6px 20px rgba(0, 0, 0, 0.1), 0 0 15px ${alpha(theme.palette.primary.main, 0.3)}`,
                      }
                    }}
                  >
                    <Box 
                      sx={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        justifyContent: 'center',
                        mb: 2,
                        width: '60px',
                        height: '60px',
                        borderRadius: '16px',
                        background: theme => theme.palette.mode === 'dark' 
                          ? alpha(theme.palette.primary.main, 0.1)
                          : alpha(theme.palette.primary.main, 0.05),
                        mx: 'auto'
                      }}
                    >
                      <QuestionAnswerOutlinedIcon 
                        sx={{ 
                          fontSize: '30px',
                          color: 'primary.main'
                        }} 
                      />
                    </Box>
                    <Typography variant="h6" sx={{ mb: 1, textAlign: 'center', fontWeight: 600 }}>
                      Natural Language Queries
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'text.secondary', textAlign: 'center' }}>
                      Ask complex biomedical questions in plain English without writing any code
                    </Typography>
                  </Paper>
                </Button>
              </Fade>
            </Grid>
            
            <Grid item xs={12} sm={6} md={3}>
              <Fade in={true} timeout={1000} style={{ transitionDelay: '400ms' }}>
                <Button
                  fullWidth
                  onClick={() => handleTabChange(null, 'query')}
                  sx={{
                    p: 0,
                    textTransform: 'none',
                    borderRadius: '20px',
                    display: 'block',
                    transition: 'all 0.7s cubic-bezier(0.4, 0, 0.2, 1)',
                    '&:hover': {
                      transform: 'translateY(-2px)',
                      backgroundColor: 'transparent'
                    }
                  }}
                >
                  <Paper 
                    elevation={0} 
                    sx={{ 
                      p: 3, 
                      height: '100%',
                      borderRadius: '20px',
                      border: theme => `1px solid ${theme.palette.divider}`,
                      transition: 'all 0.7s cubic-bezier(0.4, 0, 0.2, 1)',
                      '&:hover': {
                        boxShadow: theme => theme.palette.mode === 'dark' 
                          ? `0 6px 20px rgba(0, 0, 0, 0.3), 0 0 15px ${alpha(theme.palette.secondary.main, 0.5)}` 
                          : `0 6px 20px rgba(0, 0, 0, 0.1), 0 0 15px ${alpha(theme.palette.secondary.main, 0.3)}`,
                      }
                    }}
                  >
                    <Box 
                      sx={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        justifyContent: 'center',
                        mb: 2,
                        width: '60px',
                        height: '60px',
                        borderRadius: '16px',
                        background: theme => theme.palette.mode === 'dark' 
                          ? alpha(theme.palette.secondary.main, 0.1)
                          : alpha(theme.palette.secondary.main, 0.05),
                        mx: 'auto'
                      }}
                    >
                      <CodeOutlinedIcon 
                        sx={{ 
                          fontSize: '30px',
                          color: 'secondary.main'
                        }} 
                      />
                    </Box>
                    <Typography variant="h6" sx={{ mb: 1, textAlign: 'center', fontWeight: 600 }}>
                      Cypher Generation
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'text.secondary', textAlign: 'center' }}>
                      Automatically translates questions into optimized Cypher queries for Neo4j
                    </Typography>
                  </Paper>
                </Button>
              </Fade>
            </Grid>
            
            <Grid item xs={12} sm={6} md={3}>
              <Fade in={true} timeout={1000} style={{ transitionDelay: '600ms' }}>
                <Button
                  fullWidth
                  onClick={() => handleTabChange(null, 'about')}
                  sx={{
                    p: 0,
                    textTransform: 'none',
                    borderRadius: '20px',
                    display: 'block',
                    transition: 'all 0.7s cubic-bezier(0.4, 0, 0.2, 1)',
                    '&:hover': {
                      transform: 'translateY(-2px)',
                      backgroundColor: 'transparent'
                    }
                  }}
                >
                  <Paper 
                    elevation={0} 
                    sx={{ 
                      p: 3, 
                      height: '100%',
                      borderRadius: '20px',
                      border: theme => `1px solid ${theme.palette.divider}`,
                      transition: 'all 0.7s cubic-bezier(0.4, 0, 0.2, 1)',
                      '&:hover': {
                        boxShadow: theme => theme.palette.mode === 'dark' 
                          ? `0 6px 20px rgba(0, 0, 0, 0.3), 0 0 15px ${alpha(theme.palette.primary.main, 0.5)}` 
                          : `0 6px 20px rgba(0, 0, 0, 0.1), 0 0 15px ${alpha(theme.palette.primary.main, 0.3)}`,
                      }
                    }}
                  >
                    <Box 
                      sx={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        justifyContent: 'center',
                        mb: 2,
                        width: '60px',
                        height: '60px',
                        borderRadius: '16px',
                        background: theme => theme.palette.mode === 'dark' 
                          ? alpha(theme.palette.primary.main, 0.1)
                          : alpha(theme.palette.primary.main, 0.05),
                        mx: 'auto'
                      }}
                    >
                      <StorageOutlinedIcon 
                        sx={{ 
                          fontSize: '30px',
                          color: 'primary.main'
                        }} 
                      />
                    </Box>
                    <Typography variant="h6" sx={{ mb: 1, textAlign: 'center', fontWeight: 600 }}>
                      Knowledge Graph
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'text.secondary', textAlign: 'center' }}>
                      Access comprehensive biomedical data from the CROssBAR knowledge graph
                    </Typography>
                  </Paper>
                </Button>
              </Fade>
            </Grid>
            
            <Grid item xs={12} sm={6} md={3}>
              <Fade in={true} timeout={1000} style={{ transitionDelay: '800ms' }}>
                <Button
                  fullWidth
                  onClick={() => handleTabChange(null, 'about')}
                  sx={{
                    p: 0,
                    textTransform: 'none',
                    borderRadius: '20px',
                    display: 'block',
                    transition: 'all 0.7s cubic-bezier(0.4, 0, 0.2, 1)',
                    '&:hover': {
                      transform: 'translateY(-2px)',
                      backgroundColor: 'transparent'
                    }
                  }}
                >
                  <Paper 
                    elevation={0} 
                    sx={{ 
                      p: 3, 
                      height: '100%',
                      borderRadius: '20px',
                      border: theme => `1px solid ${theme.palette.divider}`,
                      transition: 'all 0.7s cubic-bezier(0.4, 0, 0.2, 1)',
                      '&:hover': {
                        boxShadow: theme => theme.palette.mode === 'dark' 
                          ? `0 6px 20px rgba(0, 0, 0, 0.3), 0 0 15px ${alpha(theme.palette.secondary.main, 0.5)}` 
                          : `0 6px 20px rgba(0, 0, 0, 0.1), 0 0 15px ${alpha(theme.palette.secondary.main, 0.3)}`,
                      }
                    }}
                  >
                    <Box 
                      sx={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        justifyContent: 'center',
                        mb: 2,
                        width: '60px',
                        height: '60px',
                        borderRadius: '16px',
                        background: theme => theme.palette.mode === 'dark' 
                          ? alpha(theme.palette.secondary.main, 0.1)
                          : alpha(theme.palette.secondary.main, 0.05),
                        mx: 'auto'
                      }}
                    >
                      <BiotechOutlinedIcon 
                        sx={{ 
                          fontSize: '30px',
                          color: 'secondary.main'
                        }} 
                      />
                    </Box>
                    <Typography variant="h6" sx={{ mb: 1, textAlign: 'center', fontWeight: 600 }}>
                      Multiple LLMs
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'text.secondary', textAlign: 'center' }}>
                      Support for various LLM providers including OpenAI, Anthropic, and more
                    </Typography>
                  </Paper>
                </Button>
              </Fade>
            </Grid>
          </Grid>
        </Box>

        {/* Demo Section */}
        <Box sx={{ mb: 8 }}>
          <Typography 
            variant="h3" 
            sx={{ 
              fontWeight: 600, 
              mb: 2,
              textAlign: 'center',
              letterSpacing: '-0.01em'
            }}
          >
            Try It Now
          </Typography>
          <Typography 
            variant="body1" 
            sx={{ 
              color: 'text.secondary', 
              maxWidth: '700px', 
              mx: 'auto',
              mb: 4,
              textAlign: 'center'
            }}
          >
            Experience the power of CROssBAR LLM with this quick demo
          </Typography>

          <Grid container spacing={4} justifyContent="center">
            <Grid item xs={12} md={8}>
              <Paper 
                elevation={0} 
                sx={{ 
                  p: 4, 
                  borderRadius: '24px',
                  border: theme => `1px solid ${theme.palette.divider}`,
                  backdropFilter: 'blur(10px)',
                  backgroundColor: theme => theme.palette.mode === 'dark' 
                    ? alpha(theme.palette.background.paper, 0.8)
                    : alpha(theme.palette.background.paper, 0.8),
                }}
              >
                <Box component="form" onSubmit={handleDemoSubmit}>
                  <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
                    Ask a biomedical question
                  </Typography>
                  
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" sx={{ mb: 1, color: 'text.secondary' }}>
                      Try one of these examples:
                    </Typography>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                      {sampleQuestions.map((q, i) => (
                        <Chip 
                          key={i} 
                          label={q} 
                          onClick={() => handleSampleClick(q)}
                          sx={{ 
                            borderRadius: '8px',
                            '&:hover': {
                              backgroundColor: theme => theme.palette.mode === 'dark' 
                                ? alpha(theme.palette.primary.main, 0.2)
                                : alpha(theme.palette.primary.main, 0.1),
                            }
                          }}
                        />
                      ))}
                    </Box>
                  </Box>
                  
                  <TextField
                    fullWidth
                    variant="outlined"
                    placeholder="Enter your biomedical question..."
                    value={demoQuery}
                    onChange={(e) => setDemoQuery(e.target.value)}
                    sx={{ mb: 2 }}
                    InputProps={{
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton 
                            type="submit" 
                            disabled={loading || !demoQuery.trim()}
                            color="primary"
                          >
                            {loading ? <CircularProgress size={24} /> : <SendIcon />}
                          </IconButton>
                        </InputAdornment>
                      ),
                    }}
                  />
                  
                  {error && (
                    <Alert severity="error" sx={{ mb: 2 }}>
                      {error}
                    </Alert>
                  )}
                  
                  {demoResponse && (
                    <Box sx={{ mt: 3 }}>
                      <Typography variant="subtitle2" sx={{ mb: 1, color: 'text.secondary' }}>
                        Generated Cypher Query:
                      </Typography>
                      <Paper
                        elevation={0}
                        sx={{
                          borderRadius: '12px',
                          backgroundColor: theme => theme.palette.mode === 'dark' 
                            ? alpha(theme.palette.background.subtle, 0.7)
                            : alpha(theme.palette.background.subtle, 0.7),
                          overflowX: 'auto',
                        }}
                      >
                        <SyntaxHighlighter 
                          language="cypher" 
                          style={syntaxTheme}
                          customStyle={{
                            backgroundColor: 'transparent',
                            margin: 0,
                            padding: '16px',
                            borderRadius: '12px',
                            fontSize: '0.875rem',
                            lineHeight: 1.6
                          }}
                          wrapLines={true}
                          wrapLongLines={true}
                        >
                          {demoResponse.query}
                        </SyntaxHighlighter>
                      </Paper>
                      
                      <Box sx={{ mt: 3, textAlign: 'center' }}>
                        <Button
                          variant="contained"
                          color="primary"
                          size="large"
                          onClick={() => {
                            localStorage.setItem('prefillQuery', demoQuery);
                            handleTabChange(null, 'query');
                          }}
                          endIcon={<ArrowForwardIcon />}
                        >
                          Continue to Full Interface
                        </Button>
                      </Box>
                    </Box>
                  )}
                </Box>
              </Paper>
            </Grid>
          </Grid>
        </Box>
      </Container>
    </Box>
  );
}

export default Home; 