import React, { useState } from 'react';
import {
  Typography,
  Box,
  Paper,
  Grid,
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
  TableRow,
  Divider,
  Chip,
  Collapse,
} from '@mui/material';
import LanguageIcon from '@mui/icons-material/Language';
import GitHubIcon from '@mui/icons-material/GitHub';
import ExploreIcon from '@mui/icons-material/Explore';
import TuneIcon from '@mui/icons-material/Tune';
import EditNoteIcon from '@mui/icons-material/EditNote';
import VisibilityIcon from '@mui/icons-material/Visibility';
import ScatterPlotIcon from '@mui/icons-material/ScatterPlot';
import TipsAndUpdatesIcon from '@mui/icons-material/TipsAndUpdates';
import TableChartIcon from '@mui/icons-material/TableChart';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import MenuBookIcon from '@mui/icons-material/MenuBook';

import crossbarChatIcon from '../faq/crossbar-chat.png';
import startQueryingIcon from '../faq/start-querying-icon.png';
import modelSettingsImg from '../faq/model-settings.png';
import exampleQueriesImg from '../faq/example-queries.png';
import autocompleteImg from '../faq/autocomplete.png';
import runButtonsImg from '../faq/run-buttons.png';
import queryAnswerImg from '../faq/query-natural-language-answer.png';
import generateOnlyImg from '../faq/generate-only-button-result.png';
import generatedQueryImg from '../faq/generated-query.png';
import nodeInfoImg from '../faq/node-information.png';
import entityInfoImg from '../faq/entity-information.png';
import structuredResultsImg from '../faq/structured-query-results.png';
import followUpImg from '../faq/follow-up-questions.png';
import conversationalMemoryImg from '../faq/conversational-memory.png';
import previousQueryImg from '../faq/previous-query-details.png';
import vectorSearchImg from '../faq/vector-search.png';
import vectorSearchConfigImg from '../faq/vector-search-config.png';

const SECTIONS = [
  { id: 'overview', label: 'Overview', icon: <MenuBookIcon fontSize="small" /> },
  { id: 'crossbar-chat', label: 'CROssBAR Chat', icon: <ExploreIcon fontSize="small" /> },
  { id: 'vector-search', label: 'Vector Search', icon: <ScatterPlotIcon fontSize="small" /> },
  { id: 'tips', label: 'Usage Tips', icon: <TipsAndUpdatesIcon fontSize="small" /> },
  { id: 'node-types', label: 'Node Types & CURIE', icon: <TableChartIcon fontSize="small" /> },
];

const NODE_TYPES = [
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
  { type: 'EcNumber', curie: 'eccode:1.1.1.-' },
];

function SectionAnchor({ id }) {
  return <Box id={id} sx={{ scrollMarginTop: '80px' }} />;
}

function SectionHeader({ icon, title, color }) {
  const theme = useTheme();
  return (
    <Box sx={{
      display: 'flex',
      alignItems: 'center',
      gap: 1.5,
      mb: 3,
    }}>
      <Box sx={{
        width: 40,
        height: 40,
        borderRadius: '10px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: alpha(color || theme.palette.primary.main, 0.12),
        color: color || theme.palette.primary.main,
        flexShrink: 0,
      }}>
        {icon}
      </Box>
      <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: '-0.02em' }}>
        {title}
      </Typography>
    </Box>
  );
}

function SubSectionHeader({ icon, title }) {
  const theme = useTheme();
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2, mt: 1 }}>
      <Box sx={{ color: theme.palette.primary.main, display: 'flex', alignItems: 'center' }}>
        {icon}
      </Box>
      <Typography variant="h6" sx={{ fontWeight: 600 }}>
        {title}
      </Typography>
    </Box>
  );
}

function ScreenshotCard({ src, alt, caption }) {
  const theme = useTheme();
  return (
    <Box sx={{ my: 3, textAlign: 'center' }}>
      <Box sx={{
        display: 'inline-block',
        borderRadius: '12px',
        overflow: 'hidden',
        border: `1px solid ${alpha(theme.palette.divider, 0.8)}`,
        boxShadow: theme.palette.mode === 'dark'
          ? '0 4px 20px rgba(0,0,0,0.4)'
          : '0 4px 20px rgba(0,0,0,0.08)',
        maxWidth: '100%',
      }}>
        <img
          src={src}
          alt={alt}
          style={{ display: 'block', maxWidth: '100%', height: 'auto', maxHeight: 400 }}
        />
      </Box>
      {caption && (
        <Typography variant="caption" sx={{ display: 'block', mt: 1, color: 'text.secondary', fontStyle: 'italic' }}>
          {caption}
        </Typography>
      )}
    </Box>
  );
}

function ScopeWarning() {
  const theme = useTheme();
  return (
    <Box sx={{
      my: 3,
      p: 2.5,
      borderRadius: '12px',
      backgroundColor: theme.palette.mode === 'dark'
        ? alpha('#ff9800', 0.1)
        : alpha('#ff9800', 0.06),
      border: `1px solid ${alpha('#ff9800', 0.3)}`,
      display: 'flex',
      gap: 2,
    }}>
      <WarningAmberIcon sx={{ color: '#ff9800', mt: 0.25, flexShrink: 0 }} />
      <Box>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#ff9800', mb: 0.5 }}>
          Important Scope Note
        </Typography>
        <Typography variant="body2" sx={{ lineHeight: 1.7 }}>
          CROssBAR-LLM is <strong>not a general-purpose question answering system</strong>. It is specifically designed for question answering <strong>within the CROssBARv2 KG</strong>. Because its intelligence is grounded in this specific KG, it may not fully answer general biological questions or questions about entities and relationships that are not present in the KG.
        </Typography>
        <Typography variant="body2" sx={{ mt: 1, lineHeight: 1.7 }}>
          The system is most useful for exploring <strong>complex and multi-hop relationships</strong> between biomedical entities, investigating potential biological mechanisms and hidden associations, and discovering biologically meaningful connections that would otherwise require complex manual querying.
        </Typography>
      </Box>
    </Box>
  );
}

function VisualizationWarning() {
  const theme = useTheme();
  return (
    <Box sx={{
      my: 2.5,
      p: 2,
      borderRadius: '10px',
      backgroundColor: theme.palette.mode === 'dark'
        ? alpha('#ff9800', 0.08)
        : alpha('#ff9800', 0.05),
      border: `1px solid ${alpha('#ff9800', 0.25)}`,
      display: 'flex',
      gap: 1.5,
    }}>
      <WarningAmberIcon sx={{ color: '#ff9800', mt: 0.15, flexShrink: 0, fontSize: '1.1rem' }} />
      <Typography variant="body2" sx={{ lineHeight: 1.7 }}>
        <strong>Note on Visualization:</strong> Not all Cypher queries can be rendered as a graph structure. Cypher queries that return only node or edge properties cannot be visualized as a graph in Neo4j Browser. Only queries that return nodes or paths can be visualized.
      </Typography>
    </Box>
  );
}

function StepList({ steps }) {
  const theme = useTheme();
  return (
    <List disablePadding>
      {steps.map((step, i) => (
        <ListItem key={i} alignItems="flex-start" sx={{ px: 0, py: 0.75 }}>
          <ListItemIcon sx={{ minWidth: 36, mt: 0.25 }}>
            <Box sx={{
              width: 26,
              height: 26,
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: alpha(theme.palette.primary.main, 0.12),
              color: theme.palette.primary.main,
              fontSize: '0.8rem',
              fontWeight: 700,
              flexShrink: 0,
            }}>
              {i + 1}
            </Box>
          </ListItemIcon>
          <ListItemText
            primary={step}
            primaryTypographyProps={{ variant: 'body2', sx: { lineHeight: 1.7 } }}
          />
        </ListItem>
      ))}
    </List>
  );
}

function BulletList({ items }) {
  const theme = useTheme();
  return (
    <List disablePadding>
      {items.map((item, i) => (
        <ListItem key={i} alignItems="flex-start" sx={{ px: 0, py: 0.5 }}>
          <ListItemIcon sx={{ minWidth: 24, mt: 0.6 }}>
            <Box sx={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              bgcolor: theme.palette.primary.main,
              flexShrink: 0,
            }} />
          </ListItemIcon>
          <ListItemText
            primary={typeof item === 'string' ? item : item.text}
            secondary={item.secondary || undefined}
            primaryTypographyProps={{ variant: 'body2', sx: { lineHeight: 1.7 } }}
            secondaryTypographyProps={{ variant: 'body2', sx: { lineHeight: 1.7 } }}
          />
        </ListItem>
      ))}
    </List>
  );
}

function TipItem({ text }) {
  const theme = useTheme();
  return (
    <Box sx={{ display: 'flex', gap: 1.5, py: 0.75 }}>
      <CheckCircleOutlineIcon sx={{ color: theme.palette.success.main, flexShrink: 0, mt: 0.1, fontSize: '1.1rem' }} />
      <Typography variant="body2" sx={{ lineHeight: 1.7 }}>{text}</Typography>
    </Box>
  );
}

function CollapsibleSection({ label, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const theme = useTheme();
  return (
    <Box sx={{
      borderRadius: '12px',
      border: `1px solid ${theme.palette.divider}`,
      mb: 2,
      overflow: 'hidden',
    }}>
      <Box
        onClick={() => setOpen(o => !o)}
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          px: 2.5,
          py: 1.75,
          cursor: 'pointer',
          userSelect: 'none',
          backgroundColor: theme.palette.mode === 'dark'
            ? alpha(theme.palette.primary.main, 0.06)
            : alpha(theme.palette.primary.main, 0.03),
          '&:hover': {
            backgroundColor: theme.palette.mode === 'dark'
              ? alpha(theme.palette.primary.main, 0.1)
              : alpha(theme.palette.primary.main, 0.06),
          },
          transition: 'background-color 0.2s',
        }}
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>{label}</Typography>
        {open ? <ExpandLessIcon /> : <ExpandMoreIcon />}
      </Box>
      <Collapse in={open}>
        <Box sx={{ px: 2.5, py: 2.5 }}>
          {children}
        </Box>
      </Collapse>
    </Box>
  );
}

function TOC({ activeSection, onSectionClick }) {
  const theme = useTheme();
  return (
    <Box sx={{
      position: 'sticky',
      top: 80,
      display: { xs: 'none', lg: 'block' },
    }}>
      <Paper elevation={0} sx={{
        p: 2,
        borderRadius: '14px',
        border: `1px solid ${theme.palette.divider}`,
      }}>
        <Typography variant="caption" sx={{
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          color: 'text.secondary',
          display: 'block',
          mb: 1.5,
          px: 1,
        }}>
          On this page
        </Typography>
        {SECTIONS.map(s => (
          <Box
            key={s.id}
            onClick={() => {
              document.getElementById(s.id)?.scrollIntoView({ behavior: 'smooth' });
              onSectionClick(s.id);
            }}
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              px: 1,
              py: 0.75,
              borderRadius: '8px',
              cursor: 'pointer',
              color: activeSection === s.id ? 'primary.main' : 'text.secondary',
              fontWeight: activeSection === s.id ? 600 : 400,
              backgroundColor: activeSection === s.id
                ? alpha(theme.palette.primary.main, 0.08)
                : 'transparent',
              '&:hover': {
                backgroundColor: alpha(theme.palette.primary.main, 0.06),
                color: 'primary.main',
              },
              transition: 'all 0.15s',
            }}
          >
            {s.icon}
            <Typography variant="body2" sx={{ fontWeight: 'inherit', color: 'inherit' }}>
              {s.label}
            </Typography>
          </Box>
        ))}
      </Paper>
    </Box>
  );
}

function About() {
  const theme = useTheme();
  const [activeSection, setActiveSection] = useState('overview');

  return (
    <Box sx={{ maxWidth: '1400px', mx: 'auto', pb: 8, px: { xs: 2, md: 3 } }}>

      {/* Hero */}
      <Box sx={{
        textAlign: 'center',
        mb: 6,
        py: { xs: 5, md: 7 },
        px: 3,
        borderRadius: '20px',
        background: theme.palette.mode === 'dark'
          ? 'linear-gradient(135deg, rgba(100, 181, 246, 0.12) 0%, rgba(179, 157, 219, 0.12) 100%)'
          : 'linear-gradient(135deg, rgba(0, 113, 227, 0.06) 0%, rgba(94, 92, 230, 0.06) 100%)',
        border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
        position: 'relative',
        overflow: 'hidden',
      }}>
        <Chip
          label="Documentation"
          size="small"
          sx={{
            mb: 2,
            backgroundColor: alpha(theme.palette.primary.main, 0.1),
            color: theme.palette.primary.main,
            fontWeight: 600,
            letterSpacing: '0.04em',
          }}
        />
        <Typography
          variant="h2"
          sx={{
            fontWeight: 800,
            mb: 2,
            letterSpacing: '-0.03em',
            background: theme.palette.mode === 'dark'
              ? 'linear-gradient(90deg, #64B5F6 0%, #B39DDB 100%)'
              : 'linear-gradient(90deg, #0071e3 0%, #5e5ce6 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          How to Use
        </Typography>
        <Typography variant="h6" sx={{
          color: 'text.secondary',
          maxWidth: '720px',
          mx: 'auto',
          lineHeight: 1.7,
          fontWeight: 400,
        }}>
          CROssBAR-LLM is a natural language interface for the CROssBARv2 knowledge graph, powered by large language models — enabling biomedical discovery without programming expertise.
        </Typography>

        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2, mt: 4 }}>
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
            CROssBARv2 Website
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

      <Grid container spacing={4}>
        {/* TOC sidebar */}
        <Grid item lg={3} sx={{ display: { xs: 'none', lg: 'block' } }}>
          <TOC activeSection={activeSection} onSectionClick={setActiveSection} />
        </Grid>

        {/* Main content */}
        <Grid item xs={12} lg={9}>

          {/* ── OVERVIEW ── */}
          <SectionAnchor id="overview" />
          <Paper elevation={0} sx={{
            p: { xs: 3, md: 4 },
            mb: 4,
            borderRadius: '16px',
            border: `1px solid ${theme.palette.divider}`,
          }}>
            <SectionHeader icon={<MenuBookIcon />} title="Overview" />

            <Typography variant="body1" sx={{ lineHeight: 1.8, mb: 2 }}>
              At its core, the interface translates natural language questions into structured <strong>Cypher queries</strong>, which are executed on the Neo4j graph database that stores the CROssBARv2 knowledge graph. The structured results are then converted back into coherent, contextual responses by LLMs.
            </Typography>
            <Typography variant="body1" sx={{ lineHeight: 1.8, mb: 3 }}>
              By design, CROssBAR-LLM is a <strong>conversational system</strong> that maintains short-term memory of your current session, enabling it to remember context from previous queries. You can ask follow-up questions or request further details without restating the entire context.
            </Typography>

            <ScopeWarning />

            <Divider sx={{ my: 3 }} />

            <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>Primary Modules</Typography>
            <Grid container spacing={2.5}>
              <Grid item xs={12} sm={6}>
                <Card elevation={0} sx={{
                  height: '100%',
                  border: `1px solid ${theme.palette.divider}`,
                  borderRadius: '14px',
                  background: alpha(theme.palette.primary.main, 0.03),
                }}>
                  <CardContent sx={{ p: 2.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                      <Box sx={{
                        width: 36,
                        height: 36,
                        borderRadius: '9px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: alpha(theme.palette.primary.main, 0.12),
                        color: theme.palette.primary.main,
                      }}>
                        <ExploreIcon fontSize="small" />
                      </Box>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>CROssBAR Chat</Typography>
                    </Box>
                    <Typography variant="body2" sx={{ lineHeight: 1.7 }}>
                      Directly query and navigate the knowledge graph using natural language. Ask complex, multi-hop questions about biomedical entities and relationships.
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6}>
                <Card elevation={0} sx={{
                  height: '100%',
                  border: `1px solid ${theme.palette.divider}`,
                  borderRadius: '14px',
                  background: alpha(theme.palette.secondary.main, 0.03),
                }}>
                  <CardContent sx={{ p: 2.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                      <Box sx={{
                        width: 36,
                        height: 36,
                        borderRadius: '9px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: alpha(theme.palette.secondary.main, 0.12),
                        color: theme.palette.secondary.main,
                      }}>
                        <ScatterPlotIcon fontSize="small" />
                      </Box>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Vector Search</Typography>
                    </Box>
                    <Typography variant="body2" sx={{ lineHeight: 1.7 }}>
                      Perform semantic similarity searches using Neo4j's native vector index. Upload custom embeddings to identify analogous biological entities in the KG.
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Paper>

          {/* ── CROSSBAR CHAT ── */}
          <SectionAnchor id="crossbar-chat" />
          <Paper elevation={0} sx={{
            p: { xs: 3, md: 4 },
            mb: 4,
            borderRadius: '16px',
            border: `1px solid ${theme.palette.divider}`,
          }}>
            <SectionHeader icon={<ExploreIcon />} title="CROssBAR Chat" />

            <Typography variant="body1" sx={{ lineHeight: 1.8, mb: 3 }}>
              This module allows users to directly query and navigate the KG using natural language. You can open it by clicking the <strong>CROssBAR Chat</strong> icon in the upper-left navigation menu or the <strong>Start Querying</strong> button on the Home page.
            </Typography>

            <Grid container spacing={3} sx={{ mb: 4 }}>
              <Grid item xs={12} sm={6}>
                <Box sx={{ textAlign: 'center' }}>
                  <Box sx={{
                    display: 'inline-block',
                    borderRadius: '12px',
                    overflow: 'hidden',
                    border: `1px solid ${alpha(theme.palette.divider, 0.8)}`,
                    boxShadow: theme.palette.mode === 'dark'
                      ? '0 4px 20px rgba(0,0,0,0.4)'
                      : '0 4px 20px rgba(0,0,0,0.08)',
                  }}>
                    <img src={crossbarChatIcon} alt="CROssBAR Chat sidebar icon" style={{ display: 'block', height: 100 }} />
                  </Box>
                  <Typography variant="caption" sx={{ display: 'block', mt: 1, color: 'text.secondary', fontStyle: 'italic' }}>
                    Sidebar Navigation
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={6}>
                <Box sx={{ textAlign: 'center' }}>
                  <Box sx={{
                    display: 'inline-block',
                    borderRadius: '12px',
                    overflow: 'hidden',
                    border: `1px solid ${alpha(theme.palette.divider, 0.8)}`,
                    boxShadow: theme.palette.mode === 'dark'
                      ? '0 4px 20px rgba(0,0,0,0.4)'
                      : '0 4px 20px rgba(0,0,0,0.08)',
                  }}>
                    <img src={startQueryingIcon} alt="Start Querying button" style={{ display: 'block', height: 100 }} />
                  </Box>
                  <Typography variant="caption" sx={{ display: 'block', mt: 1, color: 'text.secondary', fontStyle: 'italic' }}>
                    Home Page Entry Point
                  </Typography>
                </Box>
              </Grid>
            </Grid>

            <Divider sx={{ mb: 3.5 }} />

            {/* Model Configuration */}
            <SubSectionHeader icon={<TuneIcon />} title="Model Configuration" />
            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              Before querying, configure your LLM preferences in the <em>Options &amp; Details</em> panel by opening the <strong>Model Settings</strong> dropdown on the right side of the interface.
            </Typography>
            <BulletList items={[
              { text: <><strong>Provider &amp; Model:</strong> Select your preferred AI provider and LLM. Free access to <strong>gpt-4o-mini (OpenAI)</strong> and <strong>gemini-2.0-flash (Google)</strong> is provided with rate limits. An API key is required for any other model.</> },
              { text: <><strong>API Key:</strong> Enter your valid API key to authenticate and enable the connection to the selected model.</> },
              { text: <><strong>Top K Results:</strong> Define the number of results the system should return (adjustable between 1 and 100).</> },
              { text: <><strong>Debug Mode:</strong> Toggle to enable detailed system logs for troubleshooting.</> },
            ]} />
            <ScreenshotCard src={modelSettingsImg} alt="Model Settings Configuration" caption="Model Settings configuration panel" />

            <Divider sx={{ mb: 3.5, mt: 1 }} />

            {/* Formulating Queries */}
            <SubSectionHeader icon={<EditNoteIcon />} title="Formulating Queries" />
            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              Use the <strong>Example Queries</strong> dropdown to get started quickly. Selecting an example will automatically populate the query input field.
            </Typography>
            <ScreenshotCard src={exampleQueriesImg} alt="Example Queries Dropdown" caption="Example Queries dropdown menu" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              Type your question in the query input field. The <strong>preferred method</strong> is to use the autocomplete feature to avoid naming ambiguity. Press <code style={{ backgroundColor: alpha(theme.palette.primary.main, 0.1), padding: '1px 6px', borderRadius: 4, fontFamily: 'monospace' }}>@</code> and enter at least three characters to trigger autosuggestions. Navigate suggestions with arrow keys and select entities to include in your query.
            </Typography>
            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              This is particularly important for resolving cases where the same name exists under different node types — for example, <em>Hodgkin lymphoma</em> exists as both a <em>Phenotype</em> and a <em>Disease</em> in the KG.
            </Typography>
            <ScreenshotCard src={autocompleteImg} alt="Entity Autocomplete Feature" caption="Entity autocomplete triggered with @ symbol" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              Once your question is ready, you have two primary execution options:
            </Typography>
            <BulletList items={[
              { text: <><strong>Generate Only (<code style={{ fontFamily: 'monospace' }}>&lt;&gt;</code>):</strong> Generates the Cypher query text for your natural language question without executing it. Useful for inspecting or manually editing the Cypher statement before execution.</> },
              { text: <><strong>Generate &amp; Run (<code style={{ fontFamily: 'monospace' }}>&gt;</code>):</strong> Generates the Cypher query and runs it directly on the graph database in a single step.</> },
            ]} />
            <ScreenshotCard src={runButtonsImg} alt="Generate and Run buttons" caption="Generate Only and Generate & Run execution buttons" />

            <Divider sx={{ mb: 3.5, mt: 1 }} />

            {/* Viewing Results */}
            <SubSectionHeader icon={<VisibilityIcon />} title="Viewing Results" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              After clicking <strong>Generate &amp; Run</strong>, the system executes the query and displays the natural language answer directly below your question.
            </Typography>
            <ScreenshotCard src={queryAnswerImg} alt="Natural language answer" caption="Natural language answer displayed below the query" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              Using <strong>Generate Only</strong> lets you inspect and edit the generated Cypher query on the right side of the interface before executing it. Click <strong>Run Query</strong> to execute the refined query.
            </Typography>
            <ScreenshotCard src={generateOnlyImg} alt="Generate Only result" caption="Inspect and edit the Cypher query before executing" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              The generated Cypher query is always visible on the right side. Use the <strong>Copy</strong> button to copy it, then paste it in the{' '}
              <Link href="https://neo4j.crossbarv2.hubiodatalab.com/browser/?preselectAuthMethod=[NO_AUTH]&dbms=bolt://neo4j.crossbarv2.hubiodatalab.com" target="_blank" rel="noopener">
                Neo4j Browser
              </Link>{' '}
              for interactive graph visualization. Alternatively, click the <strong>Neo4j Browser</strong> button directly.
            </Typography>
            <VisualizationWarning />
            <ScreenshotCard src={generatedQueryImg} alt="Generated Cypher query panel" caption="Generated Cypher query with Copy and Neo4j Browser buttons" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              When a query returns specific node identifiers, a <strong>Node Information</strong> panel appears in the right-hand sidebar, showing entity categories, counts, names, identifiers, and source databases.
            </Typography>
            <ScreenshotCard src={nodeInfoImg} alt="Node information panel" caption="Node Information panel with entity details" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              Click any entity name in the Node Information panel to open a pop-up with a description and additional metadata retrieved from the entity's source database. The <strong>external link</strong> button navigates directly to the corresponding database entry.
            </Typography>
            <ScreenshotCard src={entityInfoImg} alt="Entity information popup" caption="Detailed entity metadata popup with external link" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              The <strong>Structured Query Results</strong> panel at the bottom-right provides a direct view of the raw data retrieved from the graph database.
            </Typography>
            <ScreenshotCard src={structuredResultsImg} alt="Structured query results panel" caption="Structured Query Results showing raw database data" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              CROssBAR-LLM generates <strong>3 follow-up question recommendations</strong> based on your query and retrieved results. Click any suggestion to continue exploring related entities and relationships.
            </Typography>
            <ScreenshotCard src={followUpImg} alt="Follow-up questions" caption="Suggested follow-up questions for continued exploration" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              The conversational memory feature allows you to ask follow-up questions that naturally refer to previous queries without restating full context.
            </Typography>
            <ScreenshotCard src={conversationalMemoryImg} alt="Conversational memory" caption="Conversational memory across multiple query turns" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              During multi-turn conversations, click the <strong>&lt;&gt; Query Details</strong> button above any previous answer to revert the sidebar panels to display data for that specific turn. A blue status bar will indicate <em>"Viewing query from message #N"</em>.
            </Typography>
            <ScreenshotCard src={previousQueryImg} alt="Previous query details" caption="Accessing previous query details with status indicator" />
          </Paper>

          {/* ── VECTOR SEARCH ── */}
          <SectionAnchor id="vector-search" />
          <Paper elevation={0} sx={{
            p: { xs: 3, md: 4 },
            mb: 4,
            borderRadius: '16px',
            border: `1px solid ${theme.palette.divider}`,
          }}>
            <SectionHeader icon={<ScatterPlotIcon />} title="Vector Search" color={theme.palette.secondary.main} />

            <Typography variant="body1" sx={{ lineHeight: 1.8, mb: 2 }}>
              Beyond traditional graph exploration, CROssBAR-LLM offers vector-based similarity search to identify semantically related entities that may lack a direct connection in the KG.
            </Typography>
            <Typography variant="body1" sx={{ lineHeight: 1.8, mb: 3 }}>
              This is enabled by generating and storing embeddings for key biological entities — such as proteins, drugs, and Gene Ontology terms — as node properties in the graph. These embeddings are indexed using Neo4j's native{' '}
              <Link href="https://neo4j.com/developer/genai-ecosystem/vector-search/" target="_blank" rel="noopener">vector index</Link>,
              allowing efficient and powerful semantic similarity searches.
            </Typography>

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              Toggle the <strong>Enable vector-based similarity search</strong> switch above the query input field to activate this feature. Once activated, all previously described features continue to work the same way.
            </Typography>
            <ScreenshotCard src={vectorSearchImg} alt="Vector search toggle" caption="Vector-based similarity search toggle switch" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              The Vector Search feature provides two powerful approaches to exploring biological similarities:
            </Typography>
            <BulletList items={[
              { text: <><strong>In-graph similarity search:</strong> Select a <em>Vector Category</em> and an <em>Embedding Type</em> to search for semantically similar entities within the KG (e.g., list most similar entities to a given node, or calculate the similarity score between two entities).</> },
              { text: <><strong>Custom external embeddings:</strong> Upload your own biological entity embeddings (in <code style={{ fontFamily: 'monospace' }}>.npy</code> format) to identify analogous entities in the KG. Custom embeddings must be generated for the same entity type using one of the supported embedding methods.</> },
            ]} />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2, mt: 2 }}>
              The <strong>Vector Search Examples</strong> panel provides ready-to-use examples for both in-graph similarity search and preloaded external embeddings.
            </Typography>

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 2 }}>
              Configure vector search settings in the <strong>Vector Search Config</strong> dropdown:
            </Typography>
            <BulletList items={[
              { text: <><strong>Vector Category:</strong> Select the entity type (Drug, Phenotype, Protein, etc.) to search within using vector similarity.</> },
              { text: <><strong>Embedding Type:</strong> Choose the embedding model used to generate the vector index for the selected entity type (e.g., ESM2 or ProtT5 for proteins).</> },
              { text: <><strong>Upload Custom Vector File (Optional):</strong> Provide your own external embedding file (<code style={{ fontFamily: 'monospace' }}>.npy</code> format) for comparison against the KG.</> },
            ]} />
            <ScreenshotCard src={vectorSearchConfigImg} alt="Vector Search Configuration" caption="Vector Search Config panel with category, embedding type, and upload options" />
          </Paper>

          {/* ── USAGE TIPS ── */}
          <SectionAnchor id="tips" />
          <Paper elevation={0} sx={{
            p: { xs: 3, md: 4 },
            mb: 4,
            borderRadius: '16px',
            border: `1px solid ${theme.palette.divider}`,
          }}>
            <SectionHeader icon={<TipsAndUpdatesIcon />} title="Usage Tips" color={theme.palette.success.main} />

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <TipItem text="Smaller models are more prone to generating hallucinated queries. For reliable results, we recommend using state-of-the-art LLMs." />
              <TipItem text="The Cypher queries generated by the LLMs can also be used in the Neo4j Browser for interactive visualization and further analysis." />
              <TipItem text={<>When formulating questions, including the node type after the biological entity (e.g., <em>ALX4 &lt;Gene&gt;</em> or <em>diabetes mellitus &lt;Disease&gt;</em>) improves the LLM's ability to generate correct Cypher queries.</>} />
              <TipItem text={<>Queries using database identifiers yield more precise results. Identifiers follow the compact resource identifier (CURIE) format (e.g., <code style={{ fontFamily: 'monospace', fontSize: '0.85em', backgroundColor: alpha(theme.palette.primary.main, 0.1), padding: '1px 5px', borderRadius: 3 }}>uniprot:Q9H161</code>) from Bioregistry.</>} />
              <TipItem text="If using biological entity names instead of identifiers, the preferred method is to use the autocomplete feature. This ensures you select the exact equivalent from the KG, improving query accuracy." />
              <TipItem text="If you plan to use vector-based similarity search with your own embeddings, you must first generate embeddings compatible with one of the vector indexes in the KG for the relevant biological entity. The embeddings should be saved in .npy format. Each uploaded file must contain embeddings for a single entity only." />
            </Box>
          </Paper>

          {/* ── NODE TYPES ── */}
          <SectionAnchor id="node-types" />
          <Paper elevation={0} sx={{
            p: { xs: 3, md: 4 },
            mb: 4,
            borderRadius: '16px',
            border: `1px solid ${theme.palette.divider}`,
          }}>
            <SectionHeader icon={<TableChartIcon />} title="Node Types & CURIE Format" />

            <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 3 }}>
              Identifiers follow the compact resource identifier (CURIE) format from{' '}
              <Link href="https://bioregistry.io/" target="_blank" rel="noopener">Bioregistry</Link>.
              Using identifiers instead of names yields more precise query results.
            </Typography>

            <TableContainer component={Paper} elevation={0} sx={{
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: '12px',
              overflow: 'hidden',
            }}>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{
                    backgroundColor: theme.palette.mode === 'dark'
                      ? alpha(theme.palette.primary.main, 0.1)
                      : alpha(theme.palette.primary.main, 0.05),
                  }}>
                    <TableCell sx={{ fontWeight: 700, py: 1.5, fontSize: '0.875rem' }}>Node Type</TableCell>
                    <TableCell sx={{ fontWeight: 700, py: 1.5, fontSize: '0.875rem' }}>Example CURIE</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {NODE_TYPES.map((row, i) => (
                    <TableRow
                      key={i}
                      sx={{
                        '&:nth-of-type(even)': {
                          backgroundColor: theme.palette.mode === 'dark'
                            ? alpha(theme.palette.action.hover, 0.08)
                            : alpha(theme.palette.action.hover, 0.04),
                        },
                        '&:last-child td': { borderBottom: 'none' },
                      }}
                    >
                      <TableCell sx={{ py: 1.25 }}>{row.type}</TableCell>
                      <TableCell sx={{ py: 1.25 }}>
                        <Box component="code" sx={{
                          fontFamily: 'monospace',
                          fontSize: '0.875rem',
                          backgroundColor: alpha(theme.palette.primary.main, 0.08),
                          color: theme.palette.mode === 'dark' ? '#64B5F6' : '#0071e3',
                          px: 1,
                          py: 0.25,
                          borderRadius: '5px',
                        }}>
                          {row.curie}
                        </Box>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          {/* Footer */}
          <Box sx={{
            textAlign: 'center',
            py: 3,
            borderTop: `1px solid ${theme.palette.divider}`,
          }}>
            <Typography variant="body2" color="text.secondary">
              CROssBAR-LLM Interface · Developed by HUBIODATALAB
            </Typography>
          </Box>

        </Grid>
      </Grid>
    </Box>
  );
}

export default About;
