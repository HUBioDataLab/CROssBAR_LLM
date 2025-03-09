import React, { useState } from 'react';
import { 
  Button, 
  Box, 
  Typography, 
  Chip, 
  Tooltip, 
  Menu, 
  MenuItem, 
  IconButton,
  alpha,
  useTheme
} from '@mui/material';
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined';
import MoreHorizIcon from '@mui/icons-material/MoreHoriz';

function SampleQuestions({ onQuestionClick, isVectorTab }) {
  const [anchorEl, setAnchorEl] = useState(null);
  const open = Boolean(anchorEl);
  const theme = useTheme();
  
  const examples = [
    {
      question: "Which Gene is related to the Disease named psoriasis?"
    },
    {
      question: "What proteins does the drug named Caffeine target?"
    },
    {
      question: "What are the drugs that target proteins associated with Alzheimer's disease?"
    },
    {
      question: "Which pathways are associated with both diabetes and obesity?"
    },
    {
      question: "What are the common side effects of drugs targeting the EGFR protein?"
    }
  ];

  const vectorExamples = [
    {
      question: "Give me the names of top 10 Proteins that are targeted by Small Molecules similar to the given embedding.",
      vectorCategory: "SmallMolecule",
      embeddingType: "Selformer",
      vectorFilePath: "small_molecule_embedding.npy"
    },
    {
      question: "What are the most similar proteins to the given protein?",
      vectorCategory: "Protein",
      embeddingType: "Esm2",
      vectorFilePath: "protein_embedding.npy"
    },
    {
      question: "Find diseases related to proteins with similar structure to this embedding.",
      vectorCategory: "Protein",
      embeddingType: "Esm2",
      vectorFilePath: "protein_embedding.npy"
    }
  ];

  const currentExamples = isVectorTab ? vectorExamples : examples;
  
  const handleClick = (event) => {
    setAnchorEl(event.currentTarget);
  };
  
  const handleClose = () => {
    setAnchorEl(null);
  };
  
  const handleSelectQuestion = (question) => {
    if (isVectorTab) {
      onQuestionClick(question);
    } else {
      onQuestionClick(question);
    }
    handleClose();
  };

  return (
    <Box>
      <Tooltip title="Sample questions">
        <Button
          variant="text"
          size="small"
          startIcon={<LightbulbOutlinedIcon fontSize="small" />}
          onClick={handleClick}
          sx={{
            color: theme.palette.text.secondary,
            borderRadius: '10px',
            textTransform: 'none',
            fontSize: '0.85rem',
            '&:hover': {
              backgroundColor: theme.palette.mode === 'dark' 
                ? alpha(theme.palette.primary.main, 0.1)
                : alpha(theme.palette.primary.main, 0.05),
            }
          }}
        >
          Sample Questions
        </Button>
      </Tooltip>
      
      <Menu
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        PaperProps={{
          elevation: 0,
          sx: {
            overflow: 'visible',
            filter: 'drop-shadow(0px 2px 8px rgba(0,0,0,0.15))',
            mt: 1.5,
            borderRadius: '16px',
            width: 380,
            padding: '8px',
            backdropFilter: 'blur(10px)',
            backgroundColor: theme => theme.palette.mode === 'dark' 
              ? alpha(theme.palette.background.paper, 0.9)
              : alpha(theme.palette.background.paper, 0.9),
            '& .MuiMenuItem-root': {
              borderRadius: '10px',
              mb: 0.5,
              px: 2,
              py: 1.5,
              whiteSpace: 'normal',
              wordWrap: 'break-word',
              '&:last-child': {
                mb: 0
              }
            }
          },
        }}
        transformOrigin={{ horizontal: 'left', vertical: 'top' }}
        anchorOrigin={{ horizontal: 'left', vertical: 'bottom' }}
      >
        <Box sx={{ px: 2, pb: 1 }}>
          <Typography variant="subtitle2" color="text.secondary" sx={{ fontWeight: 600, fontSize: '0.75rem' }}>
            SAMPLE QUESTIONS
          </Typography>
        </Box>
        
        {currentExamples.map((question, index) => (
          <MenuItem key={index} onClick={() => handleSelectQuestion(question)}>
            <Typography variant="body2" sx={{ lineHeight: 1.4, wordBreak: 'break-word', overflowWrap: 'break-word', whiteSpace: 'normal' }}>
              {typeof question === 'string' ? question : question.question}
            </Typography>
          </MenuItem>
        ))}
      </Menu>
    </Box>
  );
}

export default SampleQuestions;