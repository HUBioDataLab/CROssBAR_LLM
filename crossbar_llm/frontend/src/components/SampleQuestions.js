import React from 'react';
import { Button, Grid2 } from '@mui/material';

function SampleQuestions({ onClick, isVectorTab }) {
  const examples = [
    { question: 'Which Gene is related to the Disease named psoriasis?' },
    { question: 'What proteins does the drug named Caffeine target?' },
  ];

  const vectorExamples = [
    {
      question: 'Give me the names of top 10 Proteins that are targeted by Small Molecules similar to the given embedding.',
      vectorCategory: 'SmallMolecule',
      embeddingType: 'Selformer',
      vectorData: [0.1, 0.2, 0.3], // Example vector data
      vectorFilePath: 'public/small_molecule_embedding.npy'
    },
    {
      question: 'What are the most similar proteins to the given protein?',
      vectorCategory: 'Protein',
      embeddingType: 'Esm2',
      vectorData: [0.4, 0.5, 0.6], // Example vector data
      vectorFilePath: 'protein_embedding.npy'
    },
  ];

  const currentExamples = isVectorTab ? vectorExamples : examples;

  return (
    <Grid2 container spacing={2} sx={{ mt: 2 }}>
      {currentExamples.map((exampleObj, index) => (
        <Grid2
          item
          xs={12}
          sm={6}
          key={index}
          display="flex"
          justifyContent="center"
        >
          <Button
            variant="outlined"
            fullWidth
            onClick={() => onClick(exampleObj)}
            sx={{
              textTransform: 'none',
              justifyContent: 'center',
              textAlign: 'center',
            }}
          >
            {exampleObj.question}
          </Button>
        </Grid2>
      ))}
    </Grid2>
  );
}

export default SampleQuestions;