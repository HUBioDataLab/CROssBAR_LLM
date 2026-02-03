import React, { useState, useEffect, useCallback } from 'react';
import {
  Typography,
  Box,
  Paper,
  Chip,
  IconButton,
  Tooltip,
  Collapse,
  List,
  CircularProgress,
  alpha,
  useTheme,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import FilterAltIcon from '@mui/icons-material/FilterAlt';
import AccountTreeIcon from '@mui/icons-material/AccountTree';

import EntityList from './EntityList';
import { 
  getEntityTypeFromId, 
  createEmptyEntityContainer 
} from './entityUtils';
import { formatEntityName } from '../../utils/helpers';
import {
  fetchGeneSummary,
  fetchProteinData,
  fetchPathwayData,
  fetchDrugData,
  fetchDiseaseData,
  fetchDomainData,
  fetchGOTermData,
  fetchPhenotypeData,
  fetchOrganismData,
  fetchSideEffectData
} from '../../utils/BiologicalDataFetcher';

/**
 * Main component for visualizing biological entities from query results.
 */
function NodeVisualization({ executionResult }) {
  const theme = useTheme();
  const [expanded, setExpanded] = useState(true);
  const [entities, setEntities] = useState(createEmptyEntityContainer());
  const [expandedEntities, setExpandedEntities] = useState({});
  const [loading, setLoading] = useState(false);
  const [entitySummaries, setEntitySummaries] = useState({});

  // Toggle expanded state for the whole component
  const toggleExpanded = () => {
    setExpanded(!expanded);
  };

  // Toggle expanded state for an individual entity
  const toggleEntityExpanded = useCallback((id) => {
    setExpandedEntities(prev => ({
      ...prev,
      [id]: !prev[id]
    }));

    // If we're expanding and don't have a summary yet, fetch it
    if (!expandedEntities[id] && !entitySummaries[id]) {
      fetchEntitySummary(id);
    }
  }, [expandedEntities, entitySummaries]);

  // Fetch a summary for an entity from appropriate biological databases
  const fetchEntitySummary = async (id) => {
    if (!id) return;

    setEntitySummaries(prev => ({
      ...prev,
      [id]: { loading: true }
    }));

    try {
      const [type] = id.split(':');
      let summaryData = null;

      switch (type.toLowerCase()) {
        case 'ncbigene':
          summaryData = await fetchGeneSummary(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { loading: false, text: summaryData.description || '', data: summaryData }
            }));
          }
          break;
        case 'uniprot':
          summaryData = await fetchProteinData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { loading: false, text: summaryData.function, data: summaryData }
            }));
          }
          break;
        case 'kegg.pathway':
        case 'reactome':
          summaryData = await fetchPathwayData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { loading: false, text: summaryData.description, data: summaryData }
            }));
          }
          break;
        case 'interpro':
        case 'pfam':
          summaryData = await fetchDomainData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { loading: false, text: summaryData.description, data: summaryData }
            }));
          }
          break;
        case 'mondo':
        case 'mesh':
        case 'omim':
          summaryData = await fetchDiseaseData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { loading: false, text: summaryData.description, data: summaryData }
            }));
          }
          break;
        case 'drugbank':
        case 'chembl':
        case 'pubchem.compound':
        case 'chebi':
          summaryData = await fetchDrugData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { loading: false, text: summaryData.description, data: summaryData }
            }));
          }
          break;
        case 'go':
          summaryData = await fetchGOTermData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { loading: false, text: summaryData.description, data: summaryData }
            }));
          }
          break;
        case 'hp':
          summaryData = await fetchPhenotypeData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { loading: false, text: summaryData.description, data: summaryData }
            }));
          }
          break;
        case 'ncbitaxon':
          summaryData = await fetchOrganismData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { loading: false, text: summaryData.description, data: summaryData }
            }));
          }
          break;
        case 'meddra':
          summaryData = await fetchSideEffectData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { loading: false, text: summaryData.description, data: summaryData }
            }));
          }
          break;
        case 'eccode':
          setTimeout(() => {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { loading: false, text: `Enzyme classified with EC number ${id.split(':')[1]}.`, data: { id } }
            }));
          }, 500);
          break;
        default:
          setTimeout(() => {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { loading: false, text: `View detailed information about this ${type.toUpperCase()} entity by clicking the external link.`, data: { id } }
            }));
          }, 500);
      }
    } catch (error) {
      console.error(`Error fetching summary for ${id}:`, error);
      setEntitySummaries(prev => ({
        ...prev,
        [id]: { loading: false, error: true, text: 'Error fetching entity information.' }
      }));
    }
  };

  // Parse result to extract entities
  useEffect(() => {
    if (!executionResult?.result) return;

    setLoading(true);
    const extractedEntities = createEmptyEntityContainer();

    const addEntityToCollection = async (entity, entityTypeHint = null) => {
      if (!entity || !entity.id) return;

      let entityType = getEntityTypeFromId(entity.id);

      if (!entityType && entityTypeHint) {
        entityType = entityTypeHint;
      }

      if (!entityType) {
        if (entity.ensembl || entity.ensembl_gene_ids) entityType = 'genes';
        else if (entity.sequences) entityType = 'proteins';
        else if (entity.id.includes('drug') || entity.id.includes('DB')) entityType = 'drugs';
        else if (entity.id.includes('pathway') || entity.name?.toLowerCase().includes('pathway')) entityType = 'pathways';
        else if (entity.id.includes('IPR') || entity.id.includes('pfam')) entityType = 'domains';
        else if (entity.id.includes('HP:') || entity.name?.toLowerCase().includes('phenotype')) entityType = 'phenotypes';
        else if (entity.id.includes('GO:')) entityType = 'goterms';
        else if (entity.id.includes('taxon')) entityType = 'organisms';
        else if (entity.id.includes('disease') || entity.name?.toLowerCase().includes('disease')) entityType = 'diseases';
      }

      if (!entityType || !extractedEntities[entityType]) {
        if (entity.sequences) entityType = 'proteins';
        else if (entity.synonyms && (entity.id.includes('chem') || entity.id.includes('drug'))) entityType = 'compounds';
        else entityType = 'genes';
      }

      if (!extractedEntities[entityType].some(e => e.id === entity.id)) {
        let displayName = 'Unknown';

        if (entity.name) displayName = entity.name;
        else if (entity.symbol) displayName = entity.symbol;
        else if (entity.genes && entity.genes.length > 0) displayName = entity.genes[0];
        else if (entity.all_names && entity.all_names.length > 0) displayName = entity.all_names[0];
        else if (entity.proteinDescription?.recommendedName) displayName = entity.proteinDescription.recommendedName.fullName.value;
        else if (entity.synonyms && entity.synonyms.length > 0) {
          const firstSynonym = entity.synonyms[0];
          if (firstSynonym && !/^[0-9.]+$/.test(firstSynonym) && firstSynonym.length > 1) {
            displayName = firstSynonym;
          }
        }

        if (displayName === 'Unknown' || !displayName || displayName === entity.id) {
          displayName = formatEntityName(entity.id, null);
        }

        const newEntity = {
          id: entity.id,
          name: displayName,
          ...entity,
          displayName: displayName
        };

        extractedEntities[entityType].push(newEntity);

        // Fetch protein name in background for proteins
        if (entityType === 'proteins' && (!entity.name || entity.name === displayName)) {
          fetchProteinData(entity.id).then(proteinData => {
            if (proteinData && proteinData.name) {
              const entityIndex = extractedEntities.proteins.findIndex(e => e.id === entity.id);
              if (entityIndex !== -1) {
                extractedEntities.proteins[entityIndex] = {
                  ...extractedEntities.proteins[entityIndex],
                  name: proteinData.name,
                  displayName: proteinData.name,
                  ...proteinData
                };
                setEntities(prev => ({ ...prev, proteins: [...extractedEntities.proteins] }));
              }
            }
          }).catch(error => {
            console.error(`Error fetching protein name for ${entity.id}:`, error);
          });
        }
      }
    };

    try {
      const result = executionResult.result;

      if (Array.isArray(result)) {
        const entityPromises = [];

        result.forEach(item => {
          if (item.g) entityPromises.push(addEntityToCollection(item.g, 'genes'));

          if (item.p && typeof item.p === 'object') {
            const entityType = getEntityTypeFromId(item.p.id);
            if (entityType === 'pathways') entityPromises.push(addEntityToCollection(item.p, 'pathways'));
            else if (entityType === 'phenotypes') entityPromises.push(addEntityToCollection(item.p, 'phenotypes'));
            else entityPromises.push(addEntityToCollection(item.p, 'proteins'));
          } else if (item['p.id']) {
            const entity = { id: item['p.id'], name: item['p.name'] || item['p.id'].split(':')[1] };
            const entityType = getEntityTypeFromId(entity.id);
            if (entityType === 'pathways') entityPromises.push(addEntityToCollection(entity, 'pathways'));
            else if (entityType === 'phenotypes') entityPromises.push(addEntityToCollection(entity, 'phenotypes'));
            else entityPromises.push(addEntityToCollection(entity, 'proteins'));
          }

          if (item.d && item.d.id) {
            const entityType = getEntityTypeFromId(item.d.id);
            if (entityType) entityPromises.push(addEntityToCollection(item.d, entityType));
            else if (item.d.id.includes('drug') || item.d.id.includes('chembl') || item.d.id.includes('pubchem') || item.d.id.includes('chebi')) {
              entityPromises.push(addEntityToCollection(item.d, 'drugs'));
            } else {
              entityPromises.push(addEntityToCollection(item.d, 'diseases'));
            }
          }

          if (item.id && typeof item.id === 'string') {
            entityPromises.push(addEntityToCollection({ id: item.id, ...(item.score && { score: item.score }), ...item }));
          }

          Object.entries(item).forEach(([key, value]) => {
            if (!value || typeof value !== 'object' || key.includes('.')) return;
            if (value.id) entityPromises.push(addEntityToCollection(value));
          });
        });

        Promise.all(entityPromises).then(() => {
          setEntities(extractedEntities);
          setLoading(false);
        });
      } else {
        setEntities(extractedEntities);
        setLoading(false);
      }
    } catch (error) {
      console.error("Error parsing query results:", error);
      setLoading(false);
    }
  }, [executionResult]);

  const hasEntities = Object.values(entities).some(arr => arr.length > 0);
  if (!hasEntities && !loading) return null;

  const totalEntityCount = Object.values(entities).reduce((total, arr) => total + arr.length, 0);
  const entityTypeCount = Object.values(entities).filter(arr => arr.length > 0).length;

  return (
    <Paper
      elevation={0}
      sx={{
        mb: 4,
        borderRadius: '20px',
        border: `1px solid ${theme.palette.divider}`,
        overflow: 'hidden',
        backdropFilter: 'blur(10px)',
        backgroundColor: theme.palette.mode === 'dark'
          ? alpha(theme.palette.background.paper, 0.8)
          : alpha(theme.palette.background.paper, 0.8),
        transition: 'all 0.3s ease',
        '&:hover': {
          boxShadow: `0 4px 20px ${alpha(theme.palette.primary.main, 0.1)}`
        }
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
          borderBottom: expanded ? `1px solid ${theme.palette.divider}` : 'none',
          cursor: 'pointer',
          '&:hover': {
            backgroundColor: theme.palette.mode === 'dark'
              ? alpha(theme.palette.primary.main, 0.05)
              : alpha(theme.palette.primary.main, 0.03),
          }
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <AccountTreeIcon sx={{ mr: 1.5, color: theme.palette.mode === 'dark' ? theme.palette.info.light : theme.palette.info.main }} />
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            Node Information
          </Typography>
          <Chip
            label={`${totalEntityCount} entities`}
            size="small"
            color="info"
            sx={{
              ml: 1.5,
              height: '20px',
              fontSize: '0.7rem',
              fontWeight: 600,
              backgroundColor: theme.palette.mode === 'dark'
                ? alpha(theme.palette.info.main, 0.2)
                : alpha(theme.palette.info.main, 0.1),
              color: theme.palette.mode === 'dark' ? theme.palette.info.light : theme.palette.info.main,
            }}
          />
          <Chip
            label={`${entityTypeCount} categories`}
            size="small"
            sx={{
              ml: 0.5,
              height: '20px',
              fontSize: '0.7rem',
              backgroundColor: alpha(theme.palette.background.default, 0.4),
              color: 'text.secondary',
            }}
          />
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <Tooltip title="Filter results">
            <IconButton
              size="small"
              onClick={(e) => e.stopPropagation()}
              sx={{ mr: 1, borderRadius: '10px' }}
            >
              <FilterAltIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <IconButton
            size="small"
            onClick={(e) => { e.stopPropagation(); toggleExpanded(); }}
            sx={{ borderRadius: '10px' }}
          >
            {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          </IconButton>
        </Box>
      </Box>

      <Collapse in={expanded}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
            <CircularProgress size={30} />
            <Typography variant="body2" sx={{ ml: 2, color: 'text.secondary' }}>
              Processing entities...
            </Typography>
          </Box>
        ) : (
          <List sx={{ py: 0 }}>
            {Object.entries(entities).map(([type, items]) => (
              <EntityList
                key={type}
                entityType={type}
                entities={items}
                expandedEntities={expandedEntities}
                onToggleEntityExpand={toggleEntityExpanded}
                entitySummaries={entitySummaries}
              />
            ))}
          </List>
        )}
      </Collapse>
    </Paper>
  );
}

export default NodeVisualization;
