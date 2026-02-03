import React from 'react';
import {
  Box,
  Typography,
  Paper,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Collapse,
  alpha,
  useTheme,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import SectionHeader from './SectionHeader';
import { nodeLabelToVectorIndexNames, getVectorCategories } from '../../constants';

/**
 * Vector search configuration section for the right panel.
 */
function VectorSearchConfig({
  expanded,
  onToggle,
  vectorCategory,
  onCategoryChange,
  embeddingType,
  onEmbeddingTypeChange,
  vectorFile,
  selectedFile,
  onFileChange,
  isConfigValid,
}) {
  const theme = useTheme();
  const categories = getVectorCategories();

  return (
    <Paper 
      elevation={0} 
      sx={{ 
        mb: 2, 
        borderRadius: '16px', 
        border: `1px solid ${theme.palette.secondary.main}`, 
        overflow: 'hidden' 
      }}
    >
      <SectionHeader 
        title="Vector Search Config" 
        icon={<SearchIcon fontSize="small" color="secondary" />} 
        expanded={expanded}
        onToggle={onToggle}
        badge={isConfigValid ? "Ready" : "Configure"}
      />
      <Collapse in={expanded}>
        <Box sx={{ p: 2, pt: 0 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Configure vector search to find semantically similar entities in the knowledge graph.
          </Typography>
          
          {/* Vector Category */}
          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel>Vector Category</InputLabel>
            <Select
              value={vectorCategory}
              onChange={(e) => onCategoryChange(e.target.value)}
              label="Vector Category"
            >
              <MenuItem value=""><em>Select a category</em></MenuItem>
              {categories.map((category) => (
                <MenuItem key={category} value={category}>{category}</MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* Embedding Type */}
          <FormControl fullWidth size="small" sx={{ mb: 2 }} disabled={!vectorCategory}>
            <InputLabel>Embedding Type</InputLabel>
            <Select
              value={embeddingType}
              onChange={(e) => onEmbeddingTypeChange(e.target.value)}
              label="Embedding Type"
            >
              <MenuItem value=""><em>Select embedding type</em></MenuItem>
              {vectorCategory && (
                Array.isArray(nodeLabelToVectorIndexNames[vectorCategory]) 
                  ? nodeLabelToVectorIndexNames[vectorCategory].map((opt) => (
                      <MenuItem key={opt} value={opt}>{opt}</MenuItem>
                    ))
                  : nodeLabelToVectorIndexNames[vectorCategory] && (
                      <MenuItem value={nodeLabelToVectorIndexNames[vectorCategory]}>
                        {nodeLabelToVectorIndexNames[vectorCategory]}
                      </MenuItem>
                    )
              )}
            </Select>
          </FormControl>

          {/* Ready Status */}
          {vectorCategory && embeddingType && !vectorFile && !selectedFile && (
            <Box sx={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 1, 
              p: 1.5, 
              mb: 2,
              borderRadius: '8px',
              backgroundColor: alpha(theme.palette.success.main, 0.08),
              border: `1px solid ${alpha(theme.palette.success.main, 0.3)}`,
            }}>
              <CheckCircleIcon fontSize="small" color="success" />
              <Typography variant="body2" color="success.main">
                Ready for vector search with {vectorCategory} ({embeddingType})
              </Typography>
            </Box>
          )}

          {/* File Upload Button */}
          <Button
            variant="outlined"
            component="label"
            fullWidth
            startIcon={<UploadFileIcon />}
            disabled={!vectorCategory || !embeddingType}
            sx={{
              borderRadius: '12px',
              height: '44px',
              borderColor: theme.palette.secondary.main,
              color: theme.palette.secondary.main,
              textTransform: 'none',
              '&:hover': {
                backgroundColor: alpha(theme.palette.secondary.main, 0.04),
              }
            }}
          >
            Upload Custom Vector File (.npy) - Optional
            <input
              type="file"
              hidden
              onChange={(e) => onFileChange(e.target.files[0])}
              accept=".npy,.csv"
            />
          </Button>

          {selectedFile && (
            <Typography variant="body2" sx={{ mt: 1, color: 'text.secondary' }}>
              Selected: {selectedFile.name}
            </Typography>
          )}
          
          {vectorFile && !selectedFile && (
            <Typography variant="body2" sx={{ mt: 1, color: 'success.main', display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <CheckCircleIcon fontSize="small" />
              Vector file loaded for {vectorCategory} ({embeddingType})
            </Typography>
          )}
        </Box>
      </Collapse>
    </Paper>
  );
}

export default VectorSearchConfig;
