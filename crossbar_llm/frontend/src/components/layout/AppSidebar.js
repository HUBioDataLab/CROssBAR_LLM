import React, { useState } from 'react';
import {
  Box,
  Typography,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Collapse,
} from '@mui/material';
import HomeOutlinedIcon from '@mui/icons-material/HomeOutlined';
import ChatOutlinedIcon from '@mui/icons-material/ChatOutlined';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';

/**
 * Navigation item component.
 */
function NavItem({ icon, label, isSelected, onClick, mode }) {
  return (
    <ListItem disablePadding sx={{ mb: 1 }}>
      <ListItemButton 
        onClick={onClick}
        selected={isSelected}
        sx={{ 
          borderRadius: '12px',
          py: 1.5,
          '&.Mui-selected': {
            backgroundColor: mode === 'dark' 
              ? 'rgba(100, 181, 246, 0.15)' 
              : 'rgba(0, 113, 227, 0.08)',
            '&:hover': {
              backgroundColor: mode === 'dark' 
                ? 'rgba(100, 181, 246, 0.2)' 
                : 'rgba(0, 113, 227, 0.12)',
            }
          }
        }}
      >
        <ListItemIcon sx={{ 
          minWidth: 40,
          color: isSelected 
            ? (mode === 'dark' ? '#64B5F6' : '#0071e3') 
            : 'inherit'
        }}>
          {icon}
        </ListItemIcon>
        <ListItemText 
          primary={label} 
          primaryTypographyProps={{ 
            fontWeight: isSelected ? 600 : 400,
            fontFamily: "'Poppins', 'Roboto', sans-serif",
            color: isSelected 
              ? (mode === 'dark' ? '#64B5F6' : '#0071e3') 
              : 'inherit'
          }}
        />
      </ListItemButton>
    </ListItem>
  );
}

/**
 * Application sidebar with navigation and tips.
 */
function AppSidebar({
  mode,
  tabValue,
  onTabChange,
}) {
  const [autocompleteTipExpanded, setAutocompleteTipExpanded] = useState(false);

  return (
    <Box sx={{ width: 280, height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
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
      
      {/* Navigation */}
      <Box sx={{ flexGrow: 1, px: 2, pt: 1.5, overflowY: 'auto' }}>
        <List sx={{ p: 0, mt: 0 }}>
          <NavItem
            icon={<HomeOutlinedIcon />}
            label="Home"
            isSelected={tabValue === 'home'}
            onClick={() => onTabChange(null, 'home')}
            mode={mode}
          />
          <NavItem
            icon={<ChatOutlinedIcon />}
            label="CROssBAR Chat"
            isSelected={tabValue === 'query'}
            onClick={() => onTabChange(null, 'query')}
            mode={mode}
          />
          <NavItem
            icon={<InfoOutlinedIcon />}
            label="About"
            isSelected={tabValue === 'about'}
            onClick={() => onTabChange(null, 'about')}
            mode={mode}
          />
        </List>
      </Box>
      
      {/* Bottom Section with Tips and Info */}
      <Box sx={{ 
        p: 2, 
        borderTop: theme => `1px solid ${theme.palette.divider}`,
        display: 'flex',
        flexDirection: 'column',
        gap: 1.5,
      }}>
        {/* Autocomplete Tip - Expandable */}
        <Box sx={{ 
          borderRadius: '10px',
          backgroundColor: mode === 'dark' 
            ? 'rgba(100, 181, 246, 0.08)' 
            : 'rgba(0, 113, 227, 0.04)',
          border: mode === 'dark' 
            ? '1px solid rgba(100, 181, 246, 0.15)' 
            : '1px solid rgba(0, 113, 227, 0.1)',
          overflow: 'hidden',
        }}>
          {/* Clickable Header */}
          <Box 
            onClick={() => setAutocompleteTipExpanded(!autocompleteTipExpanded)}
            sx={{ 
              p: 1.5, 
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              '&:hover': {
                backgroundColor: mode === 'dark' 
                  ? 'rgba(100, 181, 246, 0.12)' 
                  : 'rgba(0, 113, 227, 0.06)',
              },
              transition: 'background-color 0.2s ease',
            }}
          >
            <Typography variant="caption" sx={{ 
              color: 'text.secondary', 
              lineHeight: 1.5,
              fontFamily: "'Poppins', 'Roboto', sans-serif",
              flex: 1,
            }}>
              <strong style={{ color: mode === 'dark' ? '#64B5F6' : '#0071e3' }}>
                {autocompleteTipExpanded ? 'Entity Autocomplete Available' : 'Tip:'}
              </strong>{' '}
              {!autocompleteTipExpanded && (
                <>
                  Type <code style={{ 
                    backgroundColor: mode === 'dark' ? 'rgba(100, 181, 246, 0.2)' : 'rgba(0, 113, 227, 0.1)', 
                    padding: '2px 5px', 
                    borderRadius: '4px',
                    fontSize: '0.75rem',
                  }}>@</code> followed by an entity name for autocomplete suggestions
                </>
              )}
              {autocompleteTipExpanded && (
                <span style={{ opacity: 0.7 }}>(click to collapse)</span>
              )}
            </Typography>
            {autocompleteTipExpanded ? (
              <ExpandLessIcon sx={{ fontSize: 18, color: mode === 'dark' ? '#64B5F6' : '#0071e3', ml: 1 }} />
            ) : (
              <ExpandMoreIcon sx={{ fontSize: 18, color: mode === 'dark' ? '#64B5F6' : '#0071e3', ml: 1 }} />
            )}
          </Box>
          
          {/* Expanded Content */}
          <Collapse in={autocompleteTipExpanded}>
            <Box sx={{ 
              px: 1.5, 
              pb: 1.5, 
              borderTop: `1px solid ${mode === 'dark' ? 'rgba(100, 181, 246, 0.15)' : 'rgba(0, 113, 227, 0.1)'}`,
            }}>
              <Typography variant="caption" sx={{ 
                color: 'text.secondary', 
                display: 'block',
                lineHeight: 1.6,
                fontFamily: "'Poppins', 'Roboto', sans-serif",
                mt: 1.5,
                mb: 1,
              }}>
                Type <code style={{ 
                  backgroundColor: mode === 'dark' ? 'rgba(100, 181, 246, 0.2)' : 'rgba(0, 113, 227, 0.1)', 
                  padding: '2px 5px', 
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                }}>@</code> followed by at least 3 characters to search for biomedical entities.
              </Typography>
              
              <Typography variant="caption" sx={{ 
                color: mode === 'dark' ? '#64B5F6' : '#0071e3', 
                display: 'block',
                fontWeight: 600,
                fontFamily: "'Poppins', 'Roboto', sans-serif",
                mb: 0.75,
              }}>
                How to use autocomplete:
              </Typography>
              
              <Box component="ul" sx={{ 
                m: 0, 
                pl: 2, 
                '& li': { 
                  mb: 0.5,
                  fontSize: '0.7rem',
                  color: 'text.secondary',
                  fontFamily: "'Poppins', 'Roboto', sans-serif",
                  lineHeight: 1.5,
                } 
              }}>
                <li>Type <strong>@</strong> symbol followed by the entity name you're looking for.</li>
                <li>After typing at least 3 characters, a dropdown menu will appear with matching entities.</li>
                <li>Use <strong>arrow keys</strong> to navigate the suggestions, <strong>Enter</strong> or <strong>Tab</strong> to select.</li>
                <li>You can also <strong>click</strong> on a suggestion to select it.</li>
                <li>Available entity types include: <em>genes, proteins, diseases, drugs, pathways</em> and more.</li>
              </Box>
              
              <Typography variant="caption" sx={{ 
                color: 'text.secondary', 
                display: 'block',
                fontStyle: 'italic',
                fontFamily: "'Poppins', 'Roboto', sans-serif",
                mt: 1,
                pt: 1,
                borderTop: `1px dashed ${mode === 'dark' ? 'rgba(100, 181, 246, 0.15)' : 'rgba(0, 113, 227, 0.1)'}`,
              }}>
                This feature helps ensure accurate entity names in your queries and improves search results.
              </Typography>
            </Box>
          </Collapse>
        </Box>

        {/* Privacy Notice */}
        <Box sx={{ 
          p: 1.5, 
          borderRadius: '10px',
          backgroundColor: mode === 'dark' 
            ? 'rgba(255, 255, 255, 0.03)' 
            : 'rgba(0, 0, 0, 0.02)',
        }}>
          <Typography variant="caption" sx={{ 
            color: 'text.secondary', 
            display: 'block',
            lineHeight: 1.5,
            fontSize: '0.65rem',
            fontFamily: "'Poppins', 'Roboto', sans-serif"
          }}>
            We save user queries and outputs, but remove all identifiable data once the session is finished. 
            Data is never used for model training. Data is stored on the CROssBAR v2 server. 
            We may analyze data globally to improve the user experience.
          </Typography>
        </Box>
        
        {/* Disclaimer */}
        <Typography variant="caption" sx={{ 
          color: 'text.secondary', 
          textAlign: 'center',
          fontStyle: 'italic',
          lineHeight: 1.5,
          fontFamily: "'Poppins', 'Roboto', sans-serif"
        }}>
          CROssBAR-LLM can make mistakes. If results seem wrong, try rephrasing or switch models.
        </Typography>
        
        {/* Version */}
        <Typography variant="caption" sx={{ 
          color: 'text.secondary', 
          textAlign: 'center',
          fontFamily: "'Poppins', 'Roboto', sans-serif",
          mt: 0.5,
        }}>
          CROssBAR-LLM v1.0
        </Typography>
      </Box>
    </Box>
  );
}

export default AppSidebar;
