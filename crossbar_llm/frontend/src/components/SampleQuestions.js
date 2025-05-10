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
  useTheme,
  keyframes
} from '@mui/material';
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import MoreHorizIcon from '@mui/icons-material/MoreHoriz';

// Define keyframes for the shine animation
const shineAnimation = keyframes`
  0% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0% 50%;
  }
`;

// Define keyframes for the pulse animation
const pulseAnimation = keyframes`
  0% {
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(0, 0, 0, 0.2);
  }
  70% {
    transform: scale(1.05);
    box-shadow: 0 0 10px 5px rgba(0, 0, 0, 0);
  }
  100% {
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(0, 0, 0, 0);
  }
`;

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
      question: "What are the drugs that target proteins associated with Alzheimer disease?"
    },
    {
      question: "Which pathways are associated with both diabetes mellitus and T-cell non-Hodgkin lymphoma? Return only signaling pathways."
    },
    {
      question: "What are the common side effects of drugs targeting the EGFR gene's protein?"
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
      <Tooltip title="Try sample questions" placement="top" arrow>
        <Button
          variant="contained"
          size="medium"
          color="secondary"
          startIcon={<AutoAwesomeIcon fontSize="small" />}
          onClick={handleClick}
          sx={{
            fontFamily: "'Poppins', sans-serif",
            fontWeight: 600,
            fontSize: '0.95rem',
            letterSpacing: '0.01em',
            textTransform: 'none',
            borderRadius: '14px',
            padding: '8px 16px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
            background: theme => theme.palette.mode === 'dark' 
              ? `linear-gradient(45deg, ${theme.palette.secondary.dark}, ${theme.palette.primary.dark})`
              : `linear-gradient(45deg, ${theme.palette.secondary.main}, ${theme.palette.primary.main})`,
            backgroundSize: '200% 200%',
            animation: `${shineAnimation} 3s ease-in-out infinite`,
            transition: 'all 0.3s ease',
            '&:hover': {
              transform: 'translateY(-2px)',
              boxShadow: '0 6px 15px rgba(0,0,0,0.15)',
              backgroundPosition: 'right center',
            },
            '&:active': {
              transform: 'translateY(1px)',
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
            }
          }}
        >
          Explore Sample Questions
        </Button>
      </Tooltip>
      
      <Menu
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        PaperProps={{
          elevation: 3,
          sx: {
            overflow: 'visible',
            filter: 'drop-shadow(0px 4px 15px rgba(0,0,0,0.2))',
            mt: 1.5,
            borderRadius: '16px',
            width: 400,
            padding: '12px',
            backdropFilter: 'blur(10px)',
            backgroundColor: theme => theme.palette.mode === 'dark' 
              ? alpha(theme.palette.background.paper, 0.95)
              : alpha(theme.palette.background.paper, 0.95),
            '& .MuiMenuItem-root': {
              borderRadius: '10px',
              mb: 1,
              px: 2,
              py: 1.5,
              whiteSpace: 'normal',
              wordWrap: 'break-word',
              '&:last-child': {
                mb: 0
              },
              '&:hover': {
                backgroundColor: theme => theme.palette.mode === 'dark'
                  ? alpha(theme.palette.primary.main, 0.15)
                  : alpha(theme.palette.primary.main, 0.08),
              }
            }
          },
        }}
        transformOrigin={{ horizontal: 'left', vertical: 'top' }}
        anchorOrigin={{ horizontal: 'left', vertical: 'bottom' }}
      >
        <Box sx={{ px: 2, pb: 2, pt: 1 }}>
          <Typography 
            variant="subtitle1" 
            color="primary" 
            sx={{ 
              fontWeight: 700, 
              fontSize: '1rem',
              display: 'flex',
              alignItems: 'center',
              gap: 1
            }}
          >
            <AutoAwesomeIcon fontSize="small" />
            EXAMPLE QUESTIONS
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Click on any question to try it out
          </Typography>
        </Box>
        
        {currentExamples.map((question, index) => (
          <MenuItem 
            key={index} 
            onClick={() => handleSelectQuestion(question)}
            sx={{
              transition: 'all 0.2s ease',
              borderLeft: '3px solid transparent',
              '&:hover': {
                borderLeft: `3px solid ${theme.palette.primary.main}`,
                paddingLeft: '13px'
              }
            }}
          >
            <Typography 
              variant="body2" 
              sx={{ 
                lineHeight: 1.5, 
                wordBreak: 'break-word', 
                overflowWrap: 'break-word', 
                whiteSpace: 'normal',
                fontWeight: 500
              }}
            >
              {typeof question === 'string' ? question : question.question}
            </Typography>
          </MenuItem>
        ))}
      </Menu>
    </Box>
  );
}

export default SampleQuestions;
