import React from 'react';
import { Button, Grid2 } from '@mui/material';

function SampleQuestions({ onClick }) {
  const examples = [
    'Which Gene is related to Disease named psoriasis?',
    'What proteins does the drug named Caffeine target?',
  ];

  return (
    <Grid2 container spacing={2} sx={{ mt: 2 }}>
      {examples.map((example, index) => (
        <Grid2 item xs={12} sm={6} key={index} display="flex" justifyContent="center">
          <Button
            variant="outlined"
            fullWidth
            onClick={() => onClick(example)}
            sx={{
              textTransform: 'none',
              justifyContent: 'center',
              textAlign: 'center',
            }}
          >
            {example}
          </Button>
        </Grid2>
      ))}
    </Grid2>
  );
}

export default SampleQuestions;