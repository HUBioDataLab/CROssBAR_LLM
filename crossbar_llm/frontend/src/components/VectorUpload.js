import React, { useState, useEffect } from 'react';
import { 
  Button, 
  InputLabel, 
  MenuItem, 
  FormControl, 
  Select, 
  Typography, 
  Box, 
  Link, 
  useTheme,
  Paper,
  Grid,
  Divider,
  alpha,
  Tooltip,
  IconButton
} from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import axios from '../services/api';

// Helper function to extract text and URL from markdown [text](url)
const extractMarkdownLink = (markdown) => {
  if (!markdown) return { text: '', url: '' };
  const match = markdown.match(/\[(.*?)\]\((.*?)\)/);
  return match ? { text: match[1], url: match[2] } : { text: '', url: '' };
};

function VectorUpload({ 
  vectorCategory, 
  setVectorCategory, 
  embeddingType, 
  setEmbeddingType, 
  vectorFile, 
  setVectorFile,
  selectedFile,
  setSelectedFile,
  handleUpload
}) {
  const theme = useTheme();
  const [showInfo, setShowInfo] = useState(false);

  const nodeLabelToVectorIndexNames = {
    "SmallMolecule": "[Selformer](https://iopscience.iop.org/article/10.1088/2632-2153/acdb30)",
    "Drug": "[Selformer](https://iopscience.iop.org/article/10.1088/2632-2153/acdb30)",
    "Compound": "[Selformer](https://iopscience.iop.org/article/10.1088/2632-2153/acdb30)",
    "Protein": [
      "[Prott5](https://arxiv.org/abs/2007.06225)",
      "[Esm2](https://www.biorxiv.org/content/10.1101/2022.07.20.500902v3)",
    ],
    "GOTerm": "[Anc2vec](https://academic.oup.com/bib/article/23/2/bbac003/6523148)",
    "CellularComponent": "[Anc2vec](https://academic.oup.com/bib/article/23/2/bbac003/6523148)",
    "BiologicalProcess": "[Anc2vec](https://academic.oup.com/bib/article/23/2/bbac003/6523148)",
    "MolecularFunction": "[Anc2vec](https://academic.oup.com/bib/article/23/2/bbac003/6523148)",
    "Phenotype": "[Cada](https://academic.oup.com/nargab/article/3/3/lqab078/6363753)",
    "Disease": "[Doc2vec](https://academic.oup.com/bioinformatics/article/37/2/236/5877941)",
    "ProteinDomain": "[Dom2vec](https://www.mdpi.com/1999-4893/14/1/28)",
    "EcNumber": "[Rxnfp](https://www.nature.com/articles/s42256-020-00284-w)",
    "Pathway": "[Biokeen](https://www.biorxiv.org/content/10.1101/631812v1)",
  };

  useEffect(() => {
    if (selectedFile) {
      handleUpload();
    }
  }, [selectedFile]);

  // Add effect to handle when vectorFile is set directly (e.g., from sample questions)
  useEffect(() => {
    if (vectorFile && !selectedFile) {
      console.log('Vector file loaded directly:', vectorFile);
    }
  }, [vectorFile]);
  
  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      console.log('Selected file:', file);
      setSelectedFile(file);
    }
  };

  const handleCategoryChange = (event) => {
    const category = event.target.value;
    setVectorCategory(category);
    const options = nodeLabelToVectorIndexNames[category];
    if (Array.isArray(options)) {
      setEmbeddingType('');
    } else if (options) {
      const match = options.match(/\[(.*?)\]/);
      setEmbeddingType(match ? match[1] : '');
    } else {
      setEmbeddingType('');
    }
  };

  // Determine the current paper markdown string based on selection
  let currentPaperMarkdown = '';
  if (vectorCategory && nodeLabelToVectorIndexNames[vectorCategory]) {
    const options = nodeLabelToVectorIndexNames[vectorCategory];
    if (Array.isArray(options)) {
      if (embeddingType) {
        currentPaperMarkdown = options.find(option => option && option.includes(`[${embeddingType}]`)) || '';
      }
    } else {
      currentPaperMarkdown = options || '';
    }
  }
  const { text: paperText, url: paperUrl } = extractMarkdownLink(currentPaperMarkdown);

  return (
    <Paper 
      elevation={0} 
      sx={{ 
        p: 2, 
        borderRadius: '16px',
        border: theme => `1px solid ${theme.palette.divider}`,
        backgroundColor: theme => theme.palette.mode === 'dark' 
          ? alpha(theme.palette.background.paper, 0.6)
          : alpha(theme.palette.background.paper, 0.6),
      }}
    >
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          Vector Search Configuration
        </Typography>
        <Tooltip title="About Vector Search">
          <IconButton 
            onClick={() => setShowInfo(!showInfo)} 
            size="small"
            color={showInfo ? "primary" : "default"}
          >
            <InfoOutlinedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
      
      {showInfo && (
        <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
          Vector search enhances query results by finding semantically similar entities in the knowledge graph.
          Select a category and embedding type, then upload your vector file.
        </Typography>
      )}
      
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <FormControl fullWidth size="small">
            <InputLabel id="vector-category-label">Vector Category</InputLabel>
            <Select
              labelId="vector-category-label"
              value={vectorCategory}
              onChange={handleCategoryChange}
              label="Vector Category"
            >
              <MenuItem value="">
                <em>Select a category</em>
              </MenuItem>
              {Object.keys(nodeLabelToVectorIndexNames).map((category) => (
                <MenuItem key={category} value={category}>
                  {category}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>

        <Grid item xs={12} md={6}>
          {Array.isArray(nodeLabelToVectorIndexNames[vectorCategory]) ? (
            <FormControl fullWidth size="small" disabled={!vectorCategory}>
              <InputLabel id="embedding-type-label">Embedding Type</InputLabel>
              <Select
                labelId="embedding-type-label"
                value={embeddingType}
                onChange={(e) => setEmbeddingType(e.target.value)}
                label="Embedding Type"
              >
                <MenuItem value="">
                  <em>Select embedding type</em>
                </MenuItem>
                {nodeLabelToVectorIndexNames[vectorCategory]?.map((option) => {
                  const displayText = option.match(/\[(.*?)\]/)?.[1] || '';
                  return displayText ? (
                    <MenuItem key={displayText} value={displayText}>
                      {displayText}
                    </MenuItem>
                  ) : null;
                })}
              </Select>
            </FormControl>
          ) : (
            <FormControl fullWidth size="small" disabled={!vectorCategory}>
              <InputLabel id="embedding-type-label">Embedding Type</InputLabel>
              <Select
                labelId="embedding-type-label"
                value={embeddingType}
                label="Embedding Type"
              >
                {vectorCategory && (
                  <MenuItem value={embeddingType}>
                    {embeddingType}
                  </MenuItem>
                )}
              </Select>
            </FormControl>
          )}
        </Grid>
      </Grid>

      {/* Render professional hyperlink if a paper link is available */}
      {paperText && paperUrl && (
        <Typography variant="body2" sx={{ mt: 2, mb: 2, color: 'text.secondary' }}>
          Read the associated paper:&nbsp;
          <Link href={paperUrl} target="_blank" rel="noopener" underline="hover" color="primary">
            {paperText}
          </Link>
        </Typography>
      )}

      <Button 
        variant="outlined" 
        component="label" 
        fullWidth
        startIcon={<UploadFileIcon />}
        disabled={!vectorCategory || !embeddingType || vectorFile}
        sx={{ 
          mt: 1,
          borderRadius: '12px',
          height: '44px',
          borderColor: theme => theme.palette.primary.main,
          color: theme => theme.palette.primary.main,
          '&:hover': {
            backgroundColor: theme => alpha(theme.palette.primary.main, 0.04),
          }
        }}
      >
        Upload Vector File (.npy)
        <input
          type="file"
          hidden
          onChange={handleFileChange}
          accept=".npy,.csv"
        />
      </Button>
      
      {selectedFile && (
        <Typography variant="body2" sx={{ mt: 1, color: 'text.secondary' }}>
          Selected file: {selectedFile.name}
        </Typography>
      )}
      
      {vectorFile && !selectedFile && (
        <Typography variant="body2" sx={{ mt: 1, color: 'success.main' }}>
          Vector file loaded successfully for {vectorCategory} ({embeddingType})
        </Typography>
      )}
    </Paper>
  );
}

export default VectorUpload;