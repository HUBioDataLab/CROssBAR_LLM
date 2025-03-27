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
  Link,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow
} from '@mui/material';
import SchoolIcon from '@mui/icons-material/School';
import SearchIcon from '@mui/icons-material/Search';
import TipsAndUpdatesIcon from '@mui/icons-material/TipsAndUpdates';
import LanguageIcon from '@mui/icons-material/Language';
import GitHubIcon from '@mui/icons-material/GitHub';
import ExploreIcon from '@mui/icons-material/Explore';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import KeyboardIcon from '@mui/icons-material/Keyboard';
import CodeIcon from '@mui/icons-material/Code';

function About({ onClose }) {
  const theme = useTheme();

  return (
    <Box sx={{ maxWidth: '1200px', mx: 'auto', pb: 6, px: 2 }}>
      <Box sx={{ 
        textAlign: 'center', 
        mb: 5,
        background: theme => theme.palette.mode === 'dark' 
          ? 'linear-gradient(135deg, rgba(100, 181, 246, 0.15) 0%, rgba(179, 157, 219, 0.15) 100%)' 
          : 'linear-gradient(135deg, rgba(0, 113, 227, 0.05) 0%, rgba(94, 92, 230, 0.05) 100%)',
        py: 5,
        px: 3,
        borderRadius: '16px',
        border: theme => `1px solid ${alpha(theme.palette.primary.main, 0.1)}`
      }}>
        <Typography 
          variant="h3" 
          sx={{ 
            fontWeight: 700, 
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
          maxWidth: '800px', 
          mx: 'auto',
          lineHeight: 1.6,
          fontWeight: 400
        }}>
          Welcome to the CROssBAR-LLM Interface. This system offers a natural language question-answering interface powered by large language models (LLMs) to enhance accessibility for researchers without programming expertise. It allows users to interact directly with the CROssBARv2 knowledge graph (KG) using natural language.
        </Typography>
      </Box>
      
      <Paper 
        elevation={0} 
        sx={{ 
          p: 4, 
          mb: 4,
          borderRadius: '16px',
          border: theme => `1px solid ${theme.palette.divider}`,
          backdropFilter: 'blur(10px)',
          backgroundColor: theme => theme.palette.mode === 'dark' 
            ? alpha(theme.palette.background.paper, 0.8)
            : alpha(theme.palette.background.paper, 0.8),
        }}
      >
        <Typography variant="body1" sx={{ mb: 3, lineHeight: 1.7 }}>
          At its core, the interface translates natural language questions into structured Cypher queries, which are executed on the Neo4j graph database that stores CROssBARv2 KG. The structured results are then converted back into coherent, contextual responses by LLMs.
        </Typography>
        
        <Box sx={{ mb: 4 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, display: 'flex', alignItems: 'center' }}>
            <SchoolIcon sx={{ mr: 1, color: 'primary.main' }} />
            Primary Modules
          </Typography>
          
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card elevation={0} sx={{ 
                height: '100%',
                border: theme => `1px solid ${theme.palette.divider}`,
                borderRadius: '12px',
              }}>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <ExploreIcon sx={{ 
                      mr: 1.5, 
                      color: theme.palette.primary.main
                    }} />
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      1. Graph Explorer Module
                    </Typography>
                  </Box>
                  <Typography variant="body2">
                    This module allows users to directly query and navigate the KG using natural language.
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            
            <Grid item xs={12} md={6}>
              <Card elevation={0} sx={{ 
                height: '100%',
                border: theme => `1px solid ${theme.palette.divider}`,
                borderRadius: '12px',
              }}>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <SearchIcon sx={{ 
                      mr: 1.5, 
                      color: theme.palette.secondary.main
                    }} />
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      2. Semantic Search Module
                    </Typography>
                  </Box>
                  <Typography variant="body2">
                    This module enables users to perform similarity searches within the KG using Neo4j's vector search capabilities. Users can either search for semantically similar entities within the KG or upload custom embeddings of a biological entity (provided that embeddings of the entity are available in the KG) to identify analogous entities in the KG. Users can also view all available embeddings in the KG through the Semantic Search Module before performing their search.
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Box>
        
        <Box sx={{ mb: 4 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, display: 'flex', alignItems: 'center' }}>
            <HelpOutlineIcon sx={{ mr: 1, color: 'primary.main' }} />
            How to use
          </Typography>
          
          <List sx={{ pl: 2 }}>
            {[
              "Enter your question in natural language. As you type, you can use autosuggestions by pressing `@` and entering at least three characters to quickly find relevant biological entities from the KG. You can also select from example questions for guidance.",
              "Select a provider and LLM.",
              "Enter your API key for the selected provider.",
              "Set the number of results to retrieve (default is 5).",
              "(Optional) Enable Debug Mode to display the conversion steps and intermediate results.",
              "Generate and/or Run Queries:\n• Click \"Generate Cypher Query\" to create a Cypher query without executing it. This query can be edited before running it.\n• Click \"Run Generated Query\" to execute a previously generated query.\n• Click \"Generate & Run Query\" to perform both actions in a single step."
            ].map((text, index) => (
              <ListItem key={index} sx={{ py: 1, px: 0 }}>
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
                    {index + 1}
                  </Box>
                </ListItemIcon>
                <ListItemText 
                  primary={text}
                  primaryTypographyProps={{ 
                    variant: 'body2',
                    sx: { whiteSpace: 'pre-line' }
                  }}
                />
              </ListItem>
            ))}
          </List>
        </Box>
        
        <Box sx={{ mb: 4 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, display: 'flex', alignItems: 'center' }}>
            <CodeIcon sx={{ mr: 1, color: 'primary.main' }} />
            Output Overview
          </Typography>
          
          <List>
            {[
              "Natural Language Response: This section provides a concise, human-readable answer of query result.",
              "Generated Cypher Query: This section displays the Cypher query automatically generated by the LLM based on the user's natural language input.",
              "Query Results: This section provides the structured JSON-formatted data retrieved from the database after executing the Cypher query.",
              "Debug Logs (If Debug Mode selected): This section display the conversion steps and intermediate results.",
              "Recent Queries: This section logs recent user queries, displaying key details such as question, generated query, response, and timestamp."
            ].map((item, index) => (
              <ListItem key={index} sx={{ py: 0.5 }}>
                <ListItemText 
                  primary={item}
                  primaryTypographyProps={{ variant: 'body2' }}
                />
              </ListItem>
            ))}
          </List>
        </Box>
        
        <Box sx={{ mb: 4 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, display: 'flex', alignItems: 'center' }}>
            <TipsAndUpdatesIcon sx={{ mr: 1, color: 'primary.main' }} />
            Usage Tips
          </Typography>
          
          <List>
            {[
              "Smaller models are more prone to generating hallucinated queries. For reliable results, we recommend using SOTA LLMs.",
              "The Cypher queries generated by the LLMs can also be used in the Neo4j Browser for interactive visualization and further analysis.",
              "When formulating questions, including the node type after the biological entity (e.g., ALX4 Gene or diabetes mellitus Disease) improves the LLM's ability to generate correct Cypher queries.",
              "Queries using database identifiers yield more precise results. Identifiers follow the compact resource identifier (CURIE) format (e.g., uniprot:Q9H161) from Bioregistry. Ensure your queries use this format. Below are examples for each node type.",
              "If using biological entity names instead of identifiers, we strongly recommend using the autocomplete feature. This ensures you select the exact equivalent from the KG, improving query accuracy.",
              "If you plan to use the semantic similarity search with your own embeddings, you must first generate embeddings compatible with one of the vector indexes in the KG for the relevant biological entity. The embeddings should be saved in .npy or .csv format and uploaded before performing the search. Note that each uploaded file must contain embeddings for a single entity only; similarity searches for multiple entities are not supported."
            ].map((item, index) => (
              <ListItem key={index} sx={{ py: 0.5 }}>
                <ListItemIcon sx={{ minWidth: 28, color: 'text.secondary' }}>
                  <Box sx={{ 
                    width: 6, 
                    height: 6, 
                    borderRadius: '50%',
                    bgcolor: 'primary.main',
                    mt: 1
                  }} />
                </ListItemIcon>
                <ListItemText 
                  primary={item}
                  primaryTypographyProps={{ variant: 'body2' }}
                />
              </ListItem>
            ))}
          </List>
        </Box>
        
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, display: 'flex', alignItems: 'center' }}>
            <KeyboardIcon sx={{ mr: 1, color: 'primary.main' }} />
            Node Types and CURIE Format
          </Typography>
          
          <TableContainer component={Paper} elevation={0} sx={{ 
            border: theme => `1px solid ${theme.palette.divider}`,
            borderRadius: '12px',
            mb: 3
          }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ 
                  backgroundColor: theme => theme.palette.mode === 'dark' 
                    ? alpha(theme.palette.primary.main, 0.1)
                    : alpha(theme.palette.primary.main, 0.05)
                }}>
                  <TableCell sx={{ fontWeight: 600 }}>Node Type</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>CURIE</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {[
                  { type: 'Protein', curie: 'uniprot:Q9H161' },
                  { type: 'Gene', curie: 'ncbigene:60529' },
                  { type: 'OrganismTaxon', curie: 'ncbitaxon:9606' },
                  { type: 'ProteinDomain', curie: 'interpro:IPR000001' },
                  { type: 'Drug', curie: 'drugbank:DB00821' },
                  { type: 'Compound', curie: 'chembl:CHEMBL6228' },
                  { type: 'GOTerm (BiologicalProcess, MolecularFunction, CellularComponent)', curie: 'go:0016072' },
                  { type: 'Disease', curie: 'mondo:0054666' },
                  { type: 'Phenotype', curie: 'hp:0000012' },
                  { type: 'SideEffect', curie: 'meddra:10073487' },
                  { type: 'EcNumber', curie: 'eccode:1.1.1.-' }
                ].map((row, index) => (
                  <TableRow key={index} sx={{ 
                    '&:nth-of-type(even)': { 
                      backgroundColor: theme => theme.palette.mode === 'dark' 
                        ? alpha(theme.palette.action.hover, 0.1)
                        : alpha(theme.palette.action.hover, 0.05)
                    }
                  }}>
                    <TableCell component="th" scope="row">
                      {row.type}
                    </TableCell>
                    <TableCell>
                      <code>{row.curie}</code>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      </Paper>
      
      <Box sx={{ textAlign: 'center' }}>
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