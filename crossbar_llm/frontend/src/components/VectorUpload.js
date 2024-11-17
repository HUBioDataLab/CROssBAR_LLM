import React, { useState } from 'react';
import { Button, InputLabel, MenuItem, FormControl, Select, Typography, Box } from '@mui/material';
import axios from '../services/api';

function VectorUpload({ vectorCategory, setVectorCategory, embeddingType, setEmbeddingType , vectorFile, setVectorFile }) {
  const [selectedFile, setSelectedFile] = useState(null);

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

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleCategoryChange = (event) => {
    const category = event.target.value;
    setVectorCategory(category);
    const options = nodeLabelToVectorIndexNames[category];
    if (Array.isArray(options)) {
      setEmbeddingType('');
    } else {
      setEmbeddingType(options);
    }
  };

  const handleUpload = () => {
    if (!selectedFile || !vectorCategory) {
      alert('Please select a file and vector category.');
      return;
    }

    const formData = new FormData();
    formData.append('vector_category', vectorCategory);
    if (embeddingType) {
      formData.append('embedding_type', embeddingType);
    }
    formData.append('file', selectedFile);

    axios
      .post('/upload_vector/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })
      .then((response) => {
        console.log('File uploaded successfully:', response.data);
        alert('File uploaded successfully.');
        setVectorFile(response.data);
      })
      .catch((error) => {
        console.error('Error uploading file:', error);
        alert(error.response?.data?.detail || 'Error uploading file.');
      });
  };

  return (
    <div>
      <FormControl fullWidth margin="normal">
        <InputLabel id="vector-category-label">Vector Category</InputLabel>
        <Select
          labelId="vector-category-label"
          value={vectorCategory}
          onChange={handleCategoryChange}
          label="Vector Category"
        >
          {Object.keys(nodeLabelToVectorIndexNames).map((category) => (
            <MenuItem key={category} value={category}>
              {category}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {Array.isArray(nodeLabelToVectorIndexNames[vectorCategory]) && (
        <FormControl fullWidth margin="normal">
          <InputLabel id="embedding-type-label">Embedding Type</InputLabel>
          <Select
            labelId="embedding-type-label"
            value={embeddingType}
            onChange={(e) => setEmbeddingType(e.target.value)}
            label="Embedding Type"
          >
            {nodeLabelToVectorIndexNames[vectorCategory].map((option) => {
              const displayText = option.match(/\[(.*?)\]/)[1];
              return (
                <MenuItem key={displayText} value={displayText}>
                  {displayText}
                </MenuItem>
              );
            })}
          </Select>
        </FormControl>
      )}

      <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
        <Button variant="contained" component="label" fullWidth>
          Select Vector File
          <input
            type="file"
            hidden
            onChange={handleFileChange}
            accept=".csv,.npy"
          />
        </Button>
        {selectedFile && (
          <Typography sx={{ mt: 1 }}>
            Selected File: {selectedFile.name}
          </Typography>
        )}
        <Button variant="contained" onClick={handleUpload} fullWidth>
          Upload Vector File
        </Button>
      </Box>
    </div>
  );
}

export default VectorUpload;