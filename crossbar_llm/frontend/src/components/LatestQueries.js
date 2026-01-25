import React, { useState } from 'react';
import { 
  Typography, 
  Box, 
  Paper, 
  Chip, 
  IconButton, 
  Tooltip, 
  Collapse, 
  Divider,
  alpha,
  useTheme,
  List,
  ListItem,
  ListItemText,
  ListItemButton,
  Menu,
  MenuItem,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Select,
  FormControl,
  InputLabel,
  OutlinedInput,
  Badge
} from '@mui/material';
import HistoryIcon from '@mui/icons-material/History';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import QuestionAnswerOutlinedIcon from '@mui/icons-material/QuestionAnswerOutlined';
import CodeIcon from '@mui/icons-material/Code';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import ChatIcon from '@mui/icons-material/Chat';
import StorageIcon from '@mui/icons-material/Storage';
import StarIcon from '@mui/icons-material/Star';
import StarBorderIcon from '@mui/icons-material/StarBorder';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import LabelIcon from '@mui/icons-material/Label';
import HistoryToggleOffIcon from '@mui/icons-material/HistoryToggleOff';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import FilterListIcon from '@mui/icons-material/FilterList';
import CloseIcon from '@mui/icons-material/Close';

function formatTimestamp(timestamp) {
  if (!timestamp) return '';
  
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  
  return date.toLocaleDateString();
}

// Predefined categories for queries
const QUERY_CATEGORIES = [
  'General',
  'Drug Discovery',
  'Protein Analysis',
  'Disease Research',
  'Pathway Analysis',
  'Custom'
];

function LatestQueries({ queries, onSelectQuery }) {
  const [expanded, setExpanded] = useState(false);
  const [favorites, setFavorites] = useState({});
  const [tags, setTags] = useState({});
  const [versions, setVersions] = useState({});
  const [anchorEl, setAnchorEl] = useState(null);
  const [selectedQueryId, setSelectedQueryId] = useState(null);
  const [tagDialogOpen, setTagDialogOpen] = useState(false);
  const [newTag, setNewTag] = useState('');
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);
  const [activeFilters, setActiveFilters] = useState({
    favorites: false,
    categories: [],
    tags: []
  });
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [exportFormat, setExportFormat] = useState('json');
  const theme = useTheme();
  
  if (!queries || queries.length === 0) {
    return null;
  }
  
  const toggleExpanded = () => {
    setExpanded(!expanded);
  };
  
  const handleSelectQuery = (query) => {
    onSelectQuery(query);
  };

  const toggleFavorite = (queryId, event) => {
    event.stopPropagation();
    setFavorites(prev => ({
      ...prev,
      [queryId]: !prev[queryId]
    }));
  };

  const handleMenuOpen = (event, queryId) => {
    event.stopPropagation();
    setAnchorEl(event.currentTarget);
    setSelectedQueryId(queryId);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
    setSelectedQueryId(null);
  };

  const handleTagDialogOpen = () => {
    setTagDialogOpen(true);
    handleMenuClose();
  };

  const handleTagDialogClose = () => {
    setTagDialogOpen(false);
    setNewTag('');
  };

  const handleAddTag = () => {
    if (newTag.trim() && selectedQueryId !== null) {
      setTags(prev => ({
        ...prev,
        [selectedQueryId]: [...(prev[selectedQueryId] || []), newTag.trim()]
      }));
      handleTagDialogClose();
    }
  };

  const handleRemoveTag = (queryId, tagToRemove, event) => {
    event.stopPropagation();
    setTags(prev => ({
      ...prev,
      [queryId]: (prev[queryId] || []).filter(tag => tag !== tagToRemove)
    }));
  };

  const handleFilterDialogOpen = () => {
    setFilterDialogOpen(true);
  };

  const handleFilterDialogClose = () => {
    setFilterDialogOpen(false);
  };

  const handleFilterChange = (filterType, value) => {
    setActiveFilters(prev => {
      if (filterType === 'favorites') {
        return { ...prev, favorites: value };
      } else if (filterType === 'categories') {
        return { ...prev, categories: value };
      } else if (filterType === 'tags') {
        return { ...prev, tags: value };
      }
      return prev;
    });
  };

  const handleExportDialogOpen = () => {
    setExportDialogOpen(true);
    handleMenuClose();
  };

  const handleExportDialogClose = () => {
    setExportDialogOpen(false);
  };

  const handleExportQueries = () => {
    // Get filtered queries
    const queriesToExport = filteredQueries.map(query => {
      const queryId = query.id || `query-${query.timestamp}`;
      return {
        ...query,
        favorite: favorites[queryId] || false,
        tags: tags[queryId] || [],
        versions: versions[queryId] || []
      };
    });

    let exportData;
    let fileName;
    let fileType;

    switch (exportFormat) {
      case 'json':
        exportData = JSON.stringify(queriesToExport, null, 2);
        fileName = 'crossbar-queries.json';
        fileType = 'application/json';
        break;
      case 'csv':
        // Simple CSV conversion
        const headers = ['question', 'query', 'timestamp', 'favorite', 'tags'];
        const csvRows = [
          headers.join(','),
          ...queriesToExport.map(q => [
            `"${q.question.replace(/"/g, '""')}"`,
            `"${(typeof q.query === 'object' ? JSON.stringify(q.query) : q.query).replace(/"/g, '""')}"`,
            q.timestamp || '',
            q.favorite ? 'Yes' : 'No',
            `"${(q.tags || []).join(';')}"`
          ].join(','))
        ];
        exportData = csvRows.join('\n');
        fileName = 'crossbar-queries.csv';
        fileType = 'text/csv';
        break;
      case 'txt':
        exportData = queriesToExport.map(q => 
          `Question: ${q.question}\nQuery: ${typeof q.query === 'object' ? JSON.stringify(q.query) : q.query}\nTimestamp: ${q.timestamp || ''}\nFavorite: ${q.favorite ? 'Yes' : 'No'}\nTags: ${(q.tags || []).join(', ')}\n\n`
        ).join('---\n\n');
        fileName = 'crossbar-queries.txt';
        fileType = 'text/plain';
        break;
      default:
        exportData = JSON.stringify(queriesToExport, null, 2);
        fileName = 'crossbar-queries.json';
        fileType = 'application/json';
    }

    // Create and trigger download
    const blob = new Blob([exportData], { type: fileType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    handleExportDialogClose();
  };

  const handleSaveVersion = () => {
    if (selectedQueryId) {
      const query = queries.find(q => (q.id || `query-${q.timestamp}`) === selectedQueryId);
      if (query) {
        const newVersion = {
          timestamp: new Date().toISOString(),
          query: query.query,
          question: query.question
        };
        
        setVersions(prev => ({
          ...prev,
          [selectedQueryId]: [...(prev[selectedQueryId] || []), newVersion]
        }));
      }
    }
    handleMenuClose();
  };

  // Apply filters to queries
  const filteredQueries = queries.filter(query => {
    const queryId = query.id || `query-${query.timestamp}`;
    
    // Filter by favorites
    if (activeFilters.favorites && !favorites[queryId]) {
      return false;
    }
    
    // Filter by tags (if any tags are selected)
    if (activeFilters.tags.length > 0) {
      const queryTags = tags[queryId] || [];
      if (!activeFilters.tags.some(tag => queryTags.includes(tag))) {
        return false;
      }
    }
    
    // Filter by categories (if any categories are selected)
    if (activeFilters.categories.length > 0) {
      // For this example, we'll use the first tag as the category
      // In a real implementation, you might have a dedicated category field
      const queryTags = tags[queryId] || [];
      const queryCategory = queryTags[0] || 'General';
      if (!activeFilters.categories.includes(queryCategory)) {
        return false;
      }
    }
    
    return true;
  });

  // Get all unique tags for the filter dialog
  const allTags = Object.values(tags).flat();
  const uniqueTags = [...new Set(allTags)];

  return (
    <Paper 
      elevation={0} 
      sx={{ 
        mt: 4, 
        mb: 2,
        borderRadius: '20px',
        border: theme => `1px solid ${theme.palette.divider}`,
        overflow: 'hidden',
        backdropFilter: 'blur(10px)',
        backgroundColor: theme => theme.palette.mode === 'dark' 
          ? alpha(theme.palette.background.paper, 0.8)
          : alpha(theme.palette.background.paper, 0.8),
      }}
    >
      <Box 
        onClick={toggleExpanded}
        sx={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          px: 3,
          py: 2.5,
          borderBottom: expanded ? theme => `1px solid ${theme.palette.divider}` : 'none',
          cursor: 'pointer',
          '&:hover': {
            backgroundColor: theme => theme.palette.mode === 'dark' 
              ? alpha(theme.palette.primary.main, 0.05)
              : alpha(theme.palette.primary.main, 0.03),
          }
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <HistoryIcon sx={{ 
            mr: 1.5, 
            color: theme => theme.palette.mode === 'dark' ? theme.palette.primary.light : theme.palette.primary.main 
          }} />
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            Recent Queries
          </Typography>
          <Chip 
            label={queries.length} 
            size="small" 
            color="primary" 
            sx={{ 
              ml: 1.5, 
              height: '20px', 
              minWidth: '20px',
              fontSize: '0.7rem',
              fontWeight: 600,
              backgroundColor: theme => theme.palette.mode === 'dark' 
                ? alpha(theme.palette.primary.main, 0.2)
                : alpha(theme.palette.primary.main, 0.1),
              color: theme => theme.palette.mode === 'dark' 
                ? theme.palette.primary.light
                : theme.palette.primary.main,
            }} 
          />
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <Tooltip title="Filter queries">
            <IconButton 
              size="small" 
              onClick={(e) => {
                e.stopPropagation();
                handleFilterDialogOpen();
              }}
              sx={{ mr: 1, borderRadius: '10px' }}
            >
              <Badge
                color="primary"
                variant="dot"
                invisible={!activeFilters.favorites && activeFilters.categories.length === 0 && activeFilters.tags.length === 0}
              >
                <FilterListIcon fontSize="small" />
              </Badge>
            </IconButton>
          </Tooltip>
          <IconButton 
            size="small" 
            onClick={(e) => {
              e.stopPropagation(); // Prevent triggering the parent onClick
              toggleExpanded();
            }}
            sx={{ borderRadius: '10px' }}
          >
            {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          </IconButton>
        </Box>
      </Box>
      
      <Collapse in={expanded}>
        <List sx={{ py: 0 }}>
          {filteredQueries.slice().reverse().map((query, index) => {
            const queryId = query.id || `query-${query.timestamp}`;
            const queryTags = tags[queryId] || [];
            const isFavorite = favorites[queryId] || false;
            const queryVersions = versions[queryId] || [];
            
            return (
              <React.Fragment key={index}>
                <ListItemButton 
                  onClick={() => handleSelectQuery(query)}
                  sx={{ 
                    py: 2,
                    px: 3,
                    '&:hover': {
                      backgroundColor: theme => theme.palette.mode === 'dark' 
                        ? alpha(theme.palette.primary.main, 0.1)
                        : alpha(theme.palette.primary.main, 0.05),
                    }
                  }}
                >
                  <ListItemText
                    disableTypography
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
                        <IconButton 
                          size="small" 
                          onClick={(e) => toggleFavorite(queryId, e)}
                          sx={{ 
                            mr: 1, 
                            p: 0.5,
                            color: isFavorite ? 'warning.main' : 'action.disabled'
                          }}
                        >
                          {isFavorite ? <StarIcon fontSize="small" /> : <StarBorderIcon fontSize="small" />}
                        </IconButton>
                        <Typography variant="body2" sx={{ fontWeight: 500, flexGrow: 1 }}>
                          {query.question}
                        </Typography>
                        <IconButton
                          size="small"
                          onClick={(e) => handleMenuOpen(e, queryId)}
                          sx={{ ml: 1 }}
                        >
                          <MoreVertIcon fontSize="small" />
                        </IconButton>
                      </Box>
                    }
                    secondary={
                      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mt: 1 }}>
                        {queryTags.length > 0 && (
                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1 }}>
                            {queryTags.map((tag, tagIndex) => (
                              <Chip
                                key={tagIndex}
                                label={tag}
                                size="small"
                                onDelete={(e) => handleRemoveTag(queryId, tag, e)}
                                onClick={(e) => e.stopPropagation()}
                                sx={{ 
                                  height: '20px',
                                  fontSize: '0.7rem',
                                  backgroundColor: theme => alpha(theme.palette.info.main, 0.1),
                                  color: 'info.main',
                                  '& .MuiChip-deleteIcon': {
                                    fontSize: '0.7rem',
                                    margin: '0 2px 0 -6px'
                                  }
                                }}
                              />
                            ))}
                          </Box>
                        )}
                        
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          {query.queryType === 'run' ? (
                            <PlayArrowIcon 
                              fontSize="small" 
                              sx={{ 
                                fontSize: '0.9rem', 
                                mr: 0.5,
                                color: theme.palette.success.main,
                                opacity: 0.9
                              }} 
                            />
                          ) : (
                            <CodeIcon 
                              fontSize="small" 
                              sx={{ 
                                fontSize: '0.9rem', 
                                mr: 0.5,
                                color: theme.palette.primary.main,
                                opacity: 0.9
                              }} 
                            />
                          )}
                          <Typography 
                            variant="caption" 
                            sx={{ 
                              color: query.queryType === 'run' ? theme.palette.success.main : theme.palette.primary.main,
                              fontWeight: 500,
                              mr: 1
                            }}
                          >
                            {query.queryType === 'run' ? 'Run Query' : 'Generated Query'}
                          </Typography>
                          <QuestionAnswerOutlinedIcon 
                            fontSize="small" 
                            sx={{ 
                              fontSize: '0.9rem', 
                              mr: 0.5,
                              color: 'text.secondary',
                              opacity: 0.7
                            }} 
                          />
                          <Typography 
                            variant="caption" 
                            sx={{ 
                              color: 'text.secondary',
                              display: 'inline-block',
                              maxWidth: '100%',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap'
                            }}
                          >
                            {typeof query.query === 'object' && query.query !== null
                              ? JSON.stringify(query.query).substring(0, 100) + (JSON.stringify(query.query).length > 100 ? '...' : '')
                              : query.query.substring(0, 100) + (query.query.length > 100 ? '...' : '')}
                          </Typography>
                        </Box>
                        
                        {queryVersions.length > 0 && (
                          <Box sx={{ display: 'flex', alignItems: 'center', mt: 0.5, ml: 0.5 }}>
                            <HistoryToggleOffIcon 
                              fontSize="small" 
                              sx={{ 
                                fontSize: '0.9rem', 
                                mr: 0.5,
                                color: theme.palette.secondary.main,
                                opacity: 0.8
                              }} 
                            />
                            <Typography 
                              variant="caption" 
                              sx={{ 
                                color: theme.palette.secondary.main,
                                fontWeight: 500
                              }}
                            >
                              Versions: 
                            </Typography>
                            <Typography 
                              variant="caption" 
                              sx={{ 
                                color: 'text.secondary',
                                ml: 0.5
                              }}
                            >
                              {queryVersions.length}
                            </Typography>
                          </Box>
                        )}
                        
                        {query.queryType === 'run' && query.response && (
                          <Box sx={{ display: 'flex', alignItems: 'flex-start', mt: 0.5, ml: 0.5 }}>
                            <ChatIcon 
                              fontSize="small" 
                              sx={{ 
                                fontSize: '0.9rem', 
                                mr: 0.5,
                                mt: 0.2,
                                color: theme.palette.info.main,
                                opacity: 0.8
                              }} 
                            />
                            <Typography 
                              variant="caption" 
                              sx={{ 
                                color: 'text.primary',
                                display: 'inline-block',
                                fontStyle: 'italic'
                              }}
                            >
                              {query.response.substring(0, 150) + (query.response.length > 150 ? '...' : '')}
                            </Typography>
                          </Box>
                        )}
                        
                        {(query.vectorIndex || query.embedding) && (
                          <Box sx={{ display: 'flex', alignItems: 'center', mt: 0.5, ml: 0.5 }}>
                            <StorageIcon 
                              fontSize="small" 
                              sx={{ 
                                fontSize: '0.9rem', 
                                mr: 0.5,
                                color: theme.palette.warning.main,
                                opacity: 0.8
                              }} 
                            />
                            <Typography 
                              variant="caption" 
                              sx={{ 
                                color: theme.palette.warning.main,
                                fontWeight: 500
                              }}
                            >
                              Vector Search: 
                            </Typography>
                            <Typography 
                              variant="caption" 
                              sx={{ 
                                color: 'text.secondary',
                                ml: 0.5
                              }}
                            >
                              {query.vectorIndex}
                              {query.embedding && ` (${query.embedding})`}
                            </Typography>
                          </Box>
                        )}
                      </Box>
                    }
                  />
                  {query.timestamp && (
                    <Box sx={{ ml: 2, display: 'flex', alignItems: 'center' }}>
                      <AccessTimeIcon 
                        fontSize="small" 
                        sx={{ 
                          fontSize: '0.9rem', 
                          mr: 0.5,
                          color: 'text.secondary',
                          opacity: 0.7
                        }} 
                      />
                      <Typography 
                        variant="caption" 
                        sx={{ 
                          color: 'text.secondary',
                          whiteSpace: 'nowrap'
                        }}
                      >
                        {formatTimestamp(query.timestamp)}
                      </Typography>
                    </Box>
                  )}
                </ListItemButton>
                {index < filteredQueries.length - 1 && (
                  <Divider sx={{ mx: 3 }} />
                )}
              </React.Fragment>
            );
          })}
        </List>
      </Collapse>

      {/* Query Actions Menu */}
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleMenuClose}
        PaperProps={{
          elevation: 3,
          sx: { borderRadius: 2, minWidth: 180 }
        }}
      >
        <MenuItem onClick={handleTagDialogOpen}>
          <LabelIcon fontSize="small" sx={{ mr: 1 }} />
          Add Tag
        </MenuItem>
        <MenuItem onClick={handleSaveVersion}>
          <HistoryToggleOffIcon fontSize="small" sx={{ mr: 1 }} />
          Save Version
        </MenuItem>
        <MenuItem onClick={handleExportDialogOpen}>
          <FileDownloadIcon fontSize="small" sx={{ mr: 1 }} />
          Export
        </MenuItem>
      </Menu>

      {/* Add Tag Dialog */}
      <Dialog open={tagDialogOpen} onClose={handleTagDialogClose} maxWidth="xs" fullWidth>
        <DialogTitle>Add Tag</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Tag"
            fullWidth
            variant="outlined"
            value={newTag}
            onChange={(e) => setNewTag(e.target.value)}
            placeholder="Enter a tag name"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleTagDialogClose}>Cancel</Button>
          <Button onClick={handleAddTag} variant="contained" color="primary">Add</Button>
        </DialogActions>
      </Dialog>

      {/* Filter Dialog */}
      <Dialog open={filterDialogOpen} onClose={handleFilterDialogClose} maxWidth="xs" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">Filter Queries</Typography>
            <IconButton size="small" onClick={handleFilterDialogClose}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" gutterBottom>Show only favorites</Typography>
            <Button 
              variant={activeFilters.favorites ? "contained" : "outlined"} 
              color="primary"
              startIcon={<StarIcon />}
              onClick={() => handleFilterChange('favorites', !activeFilters.favorites)}
              size="small"
              sx={{ mb: 2 }}
            >
              {activeFilters.favorites ? "Showing Favorites" : "Show Favorites"}
            </Button>
          </Box>

          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" gutterBottom>Categories</Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {QUERY_CATEGORIES.map((category) => (
                <Chip
                  key={category}
                  label={category}
                  clickable
                  color={activeFilters.categories.includes(category) ? "primary" : "default"}
                  onClick={() => {
                    const newCategories = activeFilters.categories.includes(category)
                      ? activeFilters.categories.filter(c => c !== category)
                      : [...activeFilters.categories, category];
                    handleFilterChange('categories', newCategories);
                  }}
                  sx={{ m: 0.5 }}
                />
              ))}
            </Box>
          </Box>

          {uniqueTags.length > 0 && (
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" gutterBottom>Tags</Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                {uniqueTags.map((tag) => (
                  <Chip
                    key={tag}
                    label={tag}
                    clickable
                    color={activeFilters.tags.includes(tag) ? "info" : "default"}
                    onClick={() => {
                      const newTags = activeFilters.tags.includes(tag)
                        ? activeFilters.tags.filter(t => t !== tag)
                        : [...activeFilters.tags, tag];
                      handleFilterChange('tags', newTags);
                    }}
                    sx={{ m: 0.5 }}
                  />
                ))}
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button 
            onClick={() => {
              setActiveFilters({
                favorites: false,
                categories: [],
                tags: []
              });
            }}
          >
            Clear Filters
          </Button>
          <Button onClick={handleFilterDialogClose} variant="contained" color="primary">
            Apply
          </Button>
        </DialogActions>
      </Dialog>

      {/* Export Dialog */}
      <Dialog open={exportDialogOpen} onClose={handleExportDialogClose} maxWidth="xs" fullWidth>
        <DialogTitle>Export Queries</DialogTitle>
        <DialogContent>
          <FormControl fullWidth margin="dense">
            <InputLabel id="export-format-label">Format</InputLabel>
            <Select
              labelId="export-format-label"
              value={exportFormat}
              onChange={(e) => setExportFormat(e.target.value)}
              input={<OutlinedInput label="Format" />}
            >
              <MenuItem value="json">JSON</MenuItem>
              <MenuItem value="csv">CSV</MenuItem>
              <MenuItem value="txt">Text</MenuItem>
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleExportDialogClose}>Cancel</Button>
          <Button onClick={handleExportQueries} variant="contained" color="primary">
            Export
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}

export default LatestQueries;