import React from 'react';
import { 
  Typography, 
  Box, 
  Paper, 
  Grid, 
  Divider, 
  alpha, 
  useTheme,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Card,
  CardContent,
  Button,
  Link
} from '@mui/material';
import QuestionAnswerOutlinedIcon from '@mui/icons-material/QuestionAnswerOutlined';
import CodeOutlinedIcon from '@mui/icons-material/CodeOutlined';
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import BiotechOutlinedIcon from '@mui/icons-material/BiotechOutlined';
import LanguageIcon from '@mui/icons-material/Language';
import GitHubIcon from '@mui/icons-material/GitHub';

function About({ onClose }) {
  const theme = useTheme();

  return (
    <Box sx={{ maxWidth: '1000px', mx: 'auto', pb: 6 }}>
      <Box sx={{ 
        textAlign: 'center', 
        mb: 6,
        background: theme => theme.palette.mode === 'dark' 
          ? 'linear-gradient(135deg, rgba(100, 181, 246, 0.2) 0%, rgba(179, 157, 219, 0.2) 100%)' 
          : 'linear-gradient(135deg, rgba(0, 113, 227, 0.05) 0%, rgba(94, 92, 230, 0.05) 100%)',
        py: 6,
        px: 3,
        borderRadius: '24px'
      }}>
        <Typography 
          variant="h3" 
          sx={{ 
            fontWeight: 600, 
            mb: 2,
            background: theme => theme.palette.mode === 'dark' 
              ? 'linear-gradient(90deg, #64B5F6 0%, #B39DDB 100%)' 
              : 'linear-gradient(90deg, #0071e3 0%, #5e5ce6 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            letterSpacing: '-0.02em'
          }}
        >
          CROssBAR-LLM
        </Typography>
        <Typography variant="h6" sx={{ 
          color: 'text.secondary', 
          maxWidth: '700px', 
          mx: 'auto',
          lineHeight: 1.6,
          fontWeight: 400
        }}>
          An advanced interface for querying biomedical knowledge graphs using natural language and large language models
        </Typography>
      </Box>

      <Grid container spacing={4}>
        <Grid item xs={12} md={6}>
          <Paper 
            elevation={0} 
            sx={{ 
              p: 3, 
              height: '100%',
              borderRadius: '20px',
              border: theme => `1px solid ${theme.palette.divider}`,
              backdropFilter: 'blur(10px)',
              backgroundColor: theme => theme.palette.mode === 'dark' 
                ? alpha(theme.palette.background.paper, 0.8)
                : alpha(theme.palette.background.paper, 0.8),
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
              <QuestionAnswerOutlinedIcon sx={{ 
                mr: 1.5, 
                color: theme => theme.palette.mode === 'dark' ? theme.palette.primary.light : theme.palette.primary.main 
              }} />
              <Typography variant="h5" sx={{ fontWeight: 600, letterSpacing: '-0.01em' }}>
                How It Works
              </Typography>
            </Box>
            
            <Typography variant="body1" sx={{ mb: 3, lineHeight: 1.7 }}>
              CROssBAR-LLM allows you to query complex biomedical knowledge graphs using natural language. The system translates your questions into Cypher queries that extract relevant information from the Neo4j database.
            </Typography>
            
            <List sx={{ pl: 2 }}>
              <ListItem sx={{ py: 1, px: 0 }}>
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <Box sx={{ 
                    width: 24, 
                    height: 24, 
                    borderRadius: '50%', 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'center',
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? alpha(theme.palette.primary.main, 0.2)
                      : alpha(theme.palette.primary.main, 0.1),
                    color: theme => theme.palette.mode === 'dark' 
                      ? theme.palette.primary.light
                      : theme.palette.primary.main,
                    fontSize: '0.8rem',
                    fontWeight: 600
                  }}>
                    1
                  </Box>
                </ListItemIcon>
                <ListItemText 
                  primary="Ask a question in natural language about biomedical entities"
                  primaryTypographyProps={{ variant: 'body2' }}
                />
              </ListItem>
              
              <ListItem sx={{ py: 1, px: 0 }}>
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <Box sx={{ 
                    width: 24, 
                    height: 24, 
                    borderRadius: '50%', 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'center',
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? alpha(theme.palette.primary.main, 0.2)
                      : alpha(theme.palette.primary.main, 0.1),
                    color: theme => theme.palette.mode === 'dark' 
                      ? theme.palette.primary.light
                      : theme.palette.primary.main,
                    fontSize: '0.8rem',
                    fontWeight: 600
                  }}>
                    2
                  </Box>
                </ListItemIcon>
                <ListItemText 
                  primary="The LLM generates a Cypher query based on your question"
                  primaryTypographyProps={{ variant: 'body2' }}
                />
              </ListItem>
              
              <ListItem sx={{ py: 1, px: 0 }}>
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <Box sx={{ 
                    width: 24, 
                    height: 24, 
                    borderRadius: '50%', 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'center',
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? alpha(theme.palette.primary.main, 0.2)
                      : alpha(theme.palette.primary.main, 0.1),
                    color: theme => theme.palette.mode === 'dark' 
                      ? theme.palette.primary.light
                      : theme.palette.primary.main,
                    fontSize: '0.8rem',
                    fontWeight: 600
                  }}>
                    3
                  </Box>
                </ListItemIcon>
                <ListItemText 
                  primary="The query is executed against the Neo4j database"
                  primaryTypographyProps={{ variant: 'body2' }}
                />
              </ListItem>
              
              <ListItem sx={{ py: 1, px: 0 }}>
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <Box sx={{ 
                    width: 24, 
                    height: 24, 
                    borderRadius: '50%', 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'center',
                    backgroundColor: theme => theme.palette.mode === 'dark' 
                      ? alpha(theme.palette.primary.main, 0.2)
                      : alpha(theme.palette.primary.main, 0.1),
                    color: theme => theme.palette.mode === 'dark' 
                      ? theme.palette.primary.light
                      : theme.palette.primary.main,
                    fontSize: '0.8rem',
                    fontWeight: 600
                  }}>
                    4
                  </Box>
                </ListItemIcon>
                <ListItemText 
                  primary="Results are presented in both structured and natural language formats"
                  primaryTypographyProps={{ variant: 'body2' }}
                />
              </ListItem>
            </List>
          </Paper>
        </Grid>
        
        <Grid item xs={12} md={6}>
          <Paper 
            elevation={0} 
            sx={{ 
              p: 3, 
              height: '100%',
              borderRadius: '20px',
              border: theme => `1px solid ${theme.palette.divider}`,
              backdropFilter: 'blur(10px)',
              backgroundColor: theme => theme.palette.mode === 'dark' 
                ? alpha(theme.palette.background.paper, 0.8)
                : alpha(theme.palette.background.paper, 0.8),
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
              <BiotechOutlinedIcon sx={{ 
                mr: 1.5, 
                color: theme => theme.palette.mode === 'dark' ? theme.palette.secondary.light : theme.palette.secondary.main 
              }} />
              <Typography variant="h5" sx={{ fontWeight: 600, letterSpacing: '-0.01em' }}>
                Features
              </Typography>
            </Box>
            
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}>
                <Card elevation={0} sx={{ 
                  backgroundColor: theme => theme.palette.mode === 'dark' 
                    ? alpha(theme.palette.background.subtle, 0.5)
                    : alpha(theme.palette.background.subtle, 0.5),
                  borderRadius: '16px',
                  height: '100%'
                }}>
                  <CardContent sx={{ p: 2.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1.5 }}>
                      <CodeOutlinedIcon fontSize="small" sx={{ mr: 1, color: 'primary.main' }} />
                      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                        Multiple LLMs
                      </Typography>
                    </Box>
                    <Typography variant="body2">
                      Support for various LLM providers including OpenAI, Anthropic, Google, and more
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} sm={6}>
                <Card elevation={0} sx={{ 
                  backgroundColor: theme => theme.palette.mode === 'dark' 
                    ? alpha(theme.palette.background.subtle, 0.5)
                    : alpha(theme.palette.background.subtle, 0.5),
                  borderRadius: '16px',
                  height: '100%'
                }}>
                  <CardContent sx={{ p: 2.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1.5 }}>
                      <StorageOutlinedIcon fontSize="small" sx={{ mr: 1, color: 'secondary.main' }} />
                      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                        Vector Search
                      </Typography>
                    </Box>
                    <Typography variant="body2">
                      Advanced vector search capabilities for finding similar biomedical entities
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} sm={6}>
                <Card elevation={0} sx={{ 
                  backgroundColor: theme => theme.palette.mode === 'dark' 
                    ? alpha(theme.palette.background.subtle, 0.5)
                    : alpha(theme.palette.background.subtle, 0.5),
                  borderRadius: '16px',
                  height: '100%'
                }}>
                  <CardContent sx={{ p: 2.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1.5 }}>
                      <SettingsOutlinedIcon fontSize="small" sx={{ mr: 1, color: 'primary.main' }} />
                      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                        Customizable
                      </Typography>
                    </Box>
                    <Typography variant="body2">
                      Control result limits, enable verbose mode, and customize query parameters
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} sm={6}>
                <Card elevation={0} sx={{ 
                  backgroundColor: theme => theme.palette.mode === 'dark' 
                    ? alpha(theme.palette.background.subtle, 0.5)
                    : alpha(theme.palette.background.subtle, 0.5),
                  borderRadius: '16px',
                  height: '100%'
                }}>
                  <CardContent sx={{ p: 2.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1.5 }}>
                      <QuestionAnswerOutlinedIcon fontSize="small" sx={{ mr: 1, color: 'secondary.main' }} />
                      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                        Natural Language
                      </Typography>
                    </Box>
                    <Typography variant="body2">
                      Results presented in both structured data and natural language explanations
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Paper>
        </Grid>
      </Grid>
      
      <Box sx={{ mt: 4, textAlign: 'center' }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          CROssBAR-LLM Interface • Developed by HUBIODATALAB
        </Typography>
        
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2 }}>
          <Button 
            variant="outlined" 
            size="small" 
            startIcon={<LanguageIcon />}
            component={Link}
            href="https://crossbarv2.hubiodatalab.com/"
            target="_blank"
            rel="noopener"
            sx={{ borderRadius: '10px' }}
          >
            CROssBAR Website
          </Button>
          
          <Button 
            variant="outlined" 
            size="small" 
            startIcon={<GitHubIcon />}
            component={Link}
            href="https://github.com/HUBIODATALAB/crossbar_llm"
            target="_blank"
            rel="noopener"
            sx={{ borderRadius: '10px' }}
          >
            GitHub
          </Button>
        </Box>
      </Box>
    </Box>
  );
}

export default About;