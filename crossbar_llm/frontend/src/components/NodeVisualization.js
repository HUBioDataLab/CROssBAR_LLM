import React, { useState, useEffect } from 'react';
import { 
  Typography, 
  Box, 
  Paper, 
  Chip, 
  IconButton, 
  Tooltip, 
  Collapse, 
  Divider,
  alpha,
  useTheme,
  List,
  ListItemButton,
  ListItemText,
  ListItemIcon,
  CircularProgress,
  Link,
  Grid,
  Card,
  CardContent,
  Badge
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import FilterAltIcon from '@mui/icons-material/FilterAlt';
import MedicationIcon from '@mui/icons-material/Medication';
import SourceIcon from '@mui/icons-material/Source';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import BiotechIcon from '@mui/icons-material/Biotech';
import HealthAndSafetyIcon from '@mui/icons-material/HealthAndSafety';
import SchemaIcon from '@mui/icons-material/Schema';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';

// Import data fetching utilities
import { 
  fetchGeneSummary, 
  fetchProteinData, 
  fetchPathwayData, 
  generateEntityUrl,
  fetchDrugData,
  fetchDiseaseData,
  fetchDomainData,
  fetchGOTermData,
  fetchPhenotypeData,
  fetchOrganismData
} from '../utils/BiologicalDataFetcher';

// Import helpers
import { generateExternalLink, formatEntityName } from '../utils/helpers';

// Component for visualizing biological entities from query results
function NodeVisualization({ executionResult }) {
  const theme = useTheme();
  const [expanded, setExpanded] = useState(true);
  const [entities, setEntities] = useState({
    genes: [],
    proteins: [],
    drugs: [],
    compounds: [],
    diseases: [],
    pathways: [],
    domains: [],
    organisms: [],
    goterms: [],
    phenotypes: [],
    sideeffects: [],
    ecnumbers: []
  });
  const [expandedEntities, setExpandedEntities] = useState({});
  const [loading, setLoading] = useState(false);
  const [entitySummaries, setEntitySummaries] = useState({});
  
  // Toggle expanded state for the whole component
  const toggleExpanded = () => {
    setExpanded(!expanded);
  };
  
  // Toggle expanded state for an individual entity
  const toggleEntityExpanded = (id) => {
    setExpandedEntities(prev => ({
      ...prev,
      [id]: !prev[id]
    }));
    
    // If we're expanding and don't have a summary yet, we could fetch it here
    if (!expandedEntities[id] && !entitySummaries[id]) {
      fetchEntitySummary(id);
    }
  };
  
  // Fetch a summary for an entity from appropriate biological databases
  const fetchEntitySummary = async (id) => {
    if (!id) return;
    
    setEntitySummaries(prev => ({
      ...prev,
      [id]: { loading: true }
    }));
    
    try {
      // Determine which type of entity this is and call appropriate data fetcher
      const [type] = id.split(':');
      let summaryData = null;
      
      // Call the appropriate data fetcher based on entity type
      switch (type.toLowerCase()) {
        case 'ncbigene':
          summaryData = await fetchGeneSummary(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { 
                loading: false, 
                text: summaryData.description || '',
                data: summaryData
              }
            }));
          }
          break;
          
        case 'uniprot':
          summaryData = await fetchProteinData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { 
                loading: false, 
                text: summaryData.function,
                data: summaryData
              }
            }));
          }
          break;
          
        case 'kegg.pathway':
        case 'reactome':
          summaryData = await fetchPathwayData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { 
                loading: false, 
                text: summaryData.description,
                data: summaryData
              }
            }));
          }
          break;
          
        case 'interpro':
        case 'pfam':
          summaryData = await fetchDomainData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { 
                loading: false, 
                text: summaryData.description,
                data: summaryData
              }
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
              [id]: { 
                loading: false, 
                text: summaryData.description,
                data: summaryData
              }
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
              [id]: { 
                loading: false, 
                text: summaryData.description,
                data: summaryData
              }
            }));
          }
          break;
          
        case 'go':
          summaryData = await fetchGOTermData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { 
                loading: false, 
                text: summaryData.description,
                data: summaryData
              }
            }));
          }
          break;
          
        case 'hp':
          summaryData = await fetchPhenotypeData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { 
                loading: false, 
                text: summaryData.description,
                data: summaryData
              }
            }));
          }
          break;
          
        case 'ncbitaxon':
          summaryData = await fetchOrganismData(id);
          if (summaryData) {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { 
                loading: false, 
                text: summaryData.description,
                data: summaryData
              }
            }));
          }
          break;
          
        case 'meddra':
          // MedDRA side effects
          setTimeout(() => {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { 
                loading: false, 
                text: `Side effect or adverse reaction with ID ${id.split(':')[1]} from the Medical Dictionary for Regulatory Activities.`,
                data: { id }
              }
            }));
          }, 500);
          break;
          
        case 'eccode':
          // Enzyme Commission numbers
          setTimeout(() => {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { 
                loading: false, 
                text: `Enzyme classified with EC number ${id.split(':')[1]}.`,
                data: { id }
              }
            }));
          }, 500);
          break;
          
        default:
          // For other entity types, provide a generic message
          setTimeout(() => {
            setEntitySummaries(prev => ({
              ...prev,
              [id]: { 
                loading: false, 
                text: `View detailed information about this ${type.toUpperCase()} entity by clicking the external link.`,
                data: { id }
              }
            }));
          }, 500);
      }
    } catch (error) {
      console.error(`Error fetching summary for ${id}:`, error);
      setEntitySummaries(prev => ({
        ...prev,
        [id]: { 
          loading: false, 
          error: true,
          text: 'Error fetching entity information. Please try again or click the external link to view details.'
        }
      }));
    }
  };
  
  // Generate URLs for external resources based on identifier format
  // Using our imported helper function directly
  
  // Parse result to extract entities
  useEffect(() => {
    if (!executionResult?.result) return;
    
    setLoading(true);
    
    // Extract entities from results based on structure
    try {
      const result = executionResult.result;
      
      // Initialize entity containers
      const extractedEntities = {
        genes: [],
        proteins: [],
        drugs: [],
        compounds: [],
        diseases: [],
        pathways: [],
        domains: [],
        organisms: [],
        goterms: [],
        phenotypes: [],
        sideeffects: [],
        ecnumbers: []
      };
      
      // Helper function to identify entity type from ID
      const getEntityTypeFromId = (id) => {
        if (!id || typeof id !== 'string') return null;
        
        const prefix = id.split(':')[0].toLowerCase();
        
        // Determine entity type based on ID prefix
        switch(prefix) {
          case 'ncbigene':
          case 'ensembl':
            return 'genes';
          case 'uniprot':
            return 'proteins';
          case 'drugbank':
            return 'drugs';
          case 'chembl':
          case 'pubchem.compound':
          case 'chebi':
            return 'compounds';
          case 'mondo':
          case 'mesh':
          case 'omim':
            return 'diseases';
          case 'kegg.pathway':
          case 'reactome':
          case 'kegg':
            return 'pathways';
          case 'interpro':
          case 'pfam':
            return 'domains';
          case 'ncbitaxon':
            return 'organisms';
          case 'go':
            return 'goterms';
          case 'hp':
            return 'phenotypes';
          case 'meddra':
            return 'sideeffects';
          case 'eccode':
            return 'ecnumbers';
          default:
            // Try to infer type from keys or patterns
            if (id.includes('pathway') || id.includes('path:')) return 'pathways';
            if (id.includes('gene')) return 'genes';
            if (id.includes('protein')) return 'proteins';
            if (id.includes('phenotype') || id.includes('HP:')) return 'phenotypes';
            if (id.includes('GO:')) return 'goterms';
            if (id.includes('disease') || id.includes('disorder')) return 'diseases';
            return null;
        }
      };
      
      // Helper to add an entity to the right category
      const addEntityToCollection = (entity, entityTypeHint = null) => {
        if (!entity || !entity.id) return;
        
        // Determine the entity type - FIRST check the ID to get the correct type
        let entityType = getEntityTypeFromId(entity.id);
        
        // Only use the hint if we couldn't determine from ID
        if (!entityType && entityTypeHint) {
          entityType = entityTypeHint;
        }
        
        // If we still don't know the type, try to infer from other properties
        if (!entityType) {
          if (entity.ensembl || entity.ensembl_gene_ids) {
            entityType = 'genes';
          } else if (entity.sequences) {
            entityType = 'proteins';
          } else if (entity.id.includes('drug') || entity.id.includes('DB')) {
            entityType = 'drugs';
          } else if (entity.id.includes('pathway') || entity.name?.toLowerCase().includes('pathway')) {
            entityType = 'pathways';
          } else if (entity.id.includes('IPR') || entity.id.includes('pfam')) {
            entityType = 'domains';
          } else if (entity.id.includes('HP:') || entity.name?.toLowerCase().includes('phenotype')) {
            entityType = 'phenotypes';
          } else if (entity.id.includes('GO:')) {
            entityType = 'goterms';
          } else if (entity.id.includes('taxon')) {
            entityType = 'organisms';
          } else if (entity.id.includes('disease') || entity.name?.toLowerCase().includes('disease')) {
            entityType = 'diseases';
          }
        }
        
        // If we still can't determine the type, use a fallback
        if (!entityType || !extractedEntities[entityType]) {
          // Default to most general category based on what properties we have
          if (entity.sequences) entityType = 'proteins';
          else if (entity.synonyms && (entity.id.includes('chem') || entity.id.includes('drug'))) entityType = 'compounds';
          else entityType = 'genes'; // Default fallback
        }
        
        // Check if entity already exists in its category
        if (!extractedEntities[entityType].some(e => e.id === entity.id)) {
          // Extract a meaningful display name based on entity type
          let displayName = 'Unknown';
          
          if (entity.name) {
            // If name property exists, use it
            displayName = entity.name;
          } else if (entity.symbol) {
            // Gene or protein symbol
            displayName = entity.symbol;
          } else if (entity.genes && entity.genes.length > 0) {
            // For genes, prefer the gene symbol over ID
            displayName = entity.genes[0];
          } else if (entity.all_names && entity.all_names.length > 0) {
            // Use first of any alternative names
            displayName = entity.all_names[0];
          } else if (entity.proteinDescription && entity.proteinDescription.recommendedName) {
            // For proteins with recommended names
            displayName = entity.proteinDescription.recommendedName.fullName.value;
          } else if (entity.synonyms && entity.synonyms.length > 0) {
            // Use first synonym if available 
            // But only use if it's not just a number or ID
            const firstSynonym = entity.synonyms[0];
            if (firstSynonym && !/^[0-9.]+$/.test(firstSynonym) && firstSynonym.length > 1) {
              displayName = firstSynonym;
            }
          } 
          
          // If we still don't have a good display name, use the formatEntityName helper
          if (displayName === 'Unknown' || !displayName || displayName === entity.id) {
            displayName = formatEntityName(entity.id, null);
          }
          
          extractedEntities[entityType].push({
            id: entity.id,
            name: displayName,
            // Include any additional properties the entity has
            ...entity,
            // Make sure the display name is properly set
            displayName: displayName
          });
        }
      };
      
      // Process the result array
      if (Array.isArray(result)) {
        result.forEach(item => {
          // Check for various entity formats
          
          // Gene objects (g)
          if (item.g) {
            const gene = item.g;
            addEntityToCollection(gene, 'genes');
          }
          
          // Check for entities with 'p' property - need to determine if it's protein or pathway
          if (item.p && typeof item.p === 'object') {
            // Check if this is actually a pathway based on ID
            const entityType = getEntityTypeFromId(item.p.id);
            if (entityType === 'pathways') {
              addEntityToCollection(item.p, 'pathways');
            } else if (entityType === 'phenotypes') {
              addEntityToCollection(item.p, 'phenotypes');
            } else {
              // Default to protein if no clear type detected
              addEntityToCollection(item.p, 'proteins');
            }
          } else if (item['p.id']) {
            // Protein/Pathway ID and possibly name format - check ID first
            const entity = {
              id: item['p.id'],
              name: item['p.name'] || item['p.id'].split(':')[1]
            };
            const entityType = getEntityTypeFromId(entity.id);
            if (entityType === 'pathways') {
              addEntityToCollection(entity, 'pathways');
            } else if (entityType === 'phenotypes') {
              addEntityToCollection(entity, 'phenotypes');
            } else {
              addEntityToCollection(entity, 'proteins');
            }
          }
          
          // Drug/Chemical/Disease objects
          if (item.d && item.d.id) {
            const entityType = getEntityTypeFromId(item.d.id);
            if (entityType === 'drugs' || entityType === 'compounds') {
              addEntityToCollection(item.d, entityType);
            } else if (entityType === 'diseases') {
              addEntityToCollection(item.d, 'diseases');
            } else if (entityType === 'pathways') {
              addEntityToCollection(item.d, 'pathways');
            } else {
              // Try to determine if it's a drug or disease from context
              if (item.d.id.includes('drug') || item.d.id.includes('chembl') || 
                  item.d.id.includes('pubchem') || item.d.id.includes('chebi')) {
                addEntityToCollection(item.d, 'drugs');
              } else {
                addEntityToCollection(item.d, 'diseases');
              }
            }
          }
          
          // Process direct key-value pairs for any entity type
          Object.entries(item).forEach(([key, value]) => {
            // Skip if not an object or if key contains a dot (property path)
            if (!value || typeof value !== 'object' || key.includes('.')) return;
            
            // If the value has an id property, try to classify and add it
            if (value.id) {
              addEntityToCollection(value);
            }
          });
          
          // Domain objects
          if ((item.d && item.d.id && 
               (item.d.id.includes('interpro') || item.d.id.includes('pfam'))) || 
              (item.domain && item.domain.id)) {
            const domain = item.domain || item.d;
            addEntityToCollection(domain, 'domains');
          }
          
          // GO Term objects
          if (item.go || item.goterm || 
              (item.g && item.g.id && item.g.id.includes('GO:'))) {
            const goTerm = item.go || item.goterm || item.g;
            addEntityToCollection(goTerm, 'goterms');
          }
          
          // Phenotype objects
          if (item.phenotype || (item.p && item.p.id && item.p.id.includes('HP:'))) {
            const phenotype = item.phenotype || item.p;
            addEntityToCollection(phenotype, 'phenotypes');
          }
          
          // Side effect objects
          if (item.se || item.sideeffect ||
              (item.s && item.s.id && item.s.id.includes('meddra'))) {
            const sideEffect = item.se || item.sideeffect || item.s;
            addEntityToCollection(sideEffect, 'sideeffects');
          }
          
          // EC Number objects
          if (item.ec || (item.e && item.e.id && item.e.id.includes('eccode'))) {
            const ecNumber = item.ec || item.e;
            addEntityToCollection(ecNumber, 'ecnumbers');
          }
          
          // Organism objects
          if (item.organism || (item.o && item.o.id && item.o.id.includes('taxon'))) {
            const organism = item.organism || item.o;
            addEntityToCollection(organism, 'organisms');
          }
        });
      }
      
      // Also handle flat result JSON structures (no array)
      else if (result && typeof result === 'object') {
        Object.entries(result).forEach(([key, value]) => {
          if (value && typeof value === 'object') {
            // If the value has an id property, try to classify and add it
            if (value.id) {
              addEntityToCollection(value);
            }
          }
        });
      }
      
      // Handle property-based results (like "d.name", "d.id")
      // Group properties that belong to the same entity
      const propertyGroups = {};
      
      if (Array.isArray(result)) {
        result.forEach((item) => {
          // Scan for properties that use dot notation
          Object.entries(item).forEach(([key, value]) => {
            if (key.includes('.')) {
              // Extract entity prefix and property name
              const [prefix, prop] = key.split('.');
              
              // Initialize group if not exists
              if (!propertyGroups[prefix]) {
                propertyGroups[prefix] = [];
              }
              
              // Find or create an entity for this row
              let entity = propertyGroups[prefix].find(e => 
                // Try to match based on ID if it exists
                (item[`${prefix}.id`] && e.id === item[`${prefix}.id`]) ||
                // Otherwise try to match based on name
                (item[`${prefix}.name`] && e.name === item[`${prefix}.name`])
              );
              
              // If no existing entity found, create a new one
              if (!entity) {
                entity = {};
                propertyGroups[prefix].push(entity);
              }
              
              // Add the property to the entity
              entity[prop] = value;
            }
          });
        });
        
        // Process all property groups as entities
        Object.entries(propertyGroups).forEach(([prefix, entities]) => {
          entities.forEach(entity => {
            // Only process entities with at least an ID or name
            if (entity.id || entity.name) {
              // Determine entity type based on prefix and properties
              let entityType = null;
              
              // First, try to determine entity type from the ID if available
              if (entity.id) {
                entityType = getEntityTypeFromId(entity.id);
              }
              
              // If we couldn't determine from ID, try to determine from prefix
              if (!entityType) {
                if (prefix === 'd') {
                  // Check if it's a disease by ID pattern or name
                  if (entity.id && (entity.id.toLowerCase().includes('mondo') || 
                                   entity.id.toLowerCase().includes('mesh') ||
                                   entity.id.toLowerCase().includes('omim'))) {
                    entityType = 'diseases';
                  } 
                  // If we have a name with disease-related terms
                  else if (entity.name && /disease|syndrome|disorder/i.test(entity.name)) {
                    entityType = 'diseases';
                  }
                  // Check for pathway patterns
                  else if ((entity.id && entity.id.toLowerCase().includes('pathway')) ||
                          (entity.name && entity.name.toLowerCase().includes('pathway'))) {
                    entityType = 'pathways';
                  }
                  // Otherwise could be drug or disease
                  else {
                    entityType = entity.id && (
                      entity.id.includes('drug') || 
                      entity.id.includes('chembl') || 
                      entity.id.includes('pubchem') ||
                      entity.id.includes('chebi')
                    ) ? 'drugs' : 'diseases';
                  }
                } else if (prefix === 'p') {
                  // 'p' could be protein, pathway, or phenotype - check ID/name
                  if (entity.id) {
                    const detectedType = getEntityTypeFromId(entity.id);
                    entityType = detectedType || 'proteins'; // default to proteins for 'p' prefix
                  } else if (entity.name && entity.name.toLowerCase().includes('pathway')) {
                    entityType = 'pathways';
                  } else if (entity.name && entity.name.toLowerCase().includes('phenotype')) {
                    entityType = 'phenotypes';
                  } else {
                    entityType = 'proteins';
                  }
                } else if (prefix === 'g') {
                  entityType = 'genes';
                } else if (prefix === 'pathway') {
                  entityType = 'pathways';
                } else if (prefix === 'phenotype') {
                  entityType = 'phenotypes';
                }
              }
              
              // Add to the appropriate collection
              addEntityToCollection(entity, entityType);
            }
          });
        });
      }
      
      setEntities(extractedEntities);
    } catch (error) {
      console.error("Error parsing query results:", error);
    }
    
    setLoading(false);
  }, [executionResult]);
  
  // Check if we have any entities to display
  const hasEntities = Object.values(entities).some(arr => arr.length > 0);
  
  if (!hasEntities && !loading) return null;
  
  // Get the count of all entities
  const totalEntityCount = Object.values(entities).reduce((total, arr) => total + arr.length, 0);
  
  // Get the count of populated entity types
  const entityTypeCount = Object.values(entities).filter(arr => arr.length > 0).length;
  
  // Helper to get icon for entity type
  const getEntityIcon = (type) => {
    switch (type) {
      case 'genes':
        return <BiotechIcon />;
      case 'proteins':
        return <SourceIcon />;
      case 'drugs':
        return <MedicationIcon />;
      case 'compounds':
        return <MedicationIcon />;
      case 'diseases':
        return <HealthAndSafetyIcon />;
      case 'pathways':
        return <SchemaIcon />;
      case 'domains':
        return <AccountTreeIcon />;
      case 'organisms':
        return <BiotechIcon />;
      case 'goterms':
        return <SourceIcon />;
      case 'phenotypes':
        return <HealthAndSafetyIcon />;
      case 'sideeffects':
        return <HealthAndSafetyIcon />;
      case 'ecnumbers':
        return <SchemaIcon />;
      default:
        return <AccountTreeIcon />;
    }
  };
  
  // Helper for entity type labels
  const getEntityTypeLabel = (type) => {
    switch (type) {
      case 'genes': return 'Genes';
      case 'proteins': return 'Proteins';
      case 'drugs': return 'Drugs';
      case 'compounds': return 'Chemical Compounds';
      case 'diseases': return 'Diseases';
      case 'pathways': return 'Pathways';
      case 'domains': return 'Protein Domains';
      case 'organisms': return 'Organisms';
      case 'goterms': return 'GO Terms';
      case 'phenotypes': return 'Phenotypes';
      case 'sideeffects': return 'Side Effects';
      case 'ecnumbers': return 'EC Numbers';
      default: return type.charAt(0).toUpperCase() + type.slice(1);
    }
  };
  
  return (
    <Paper 
      elevation={0} 
      sx={{ 
        mb: 4, 
        borderRadius: '20px',
        border: theme => `1px solid ${theme.palette.divider}`,
        overflow: 'hidden',
        backdropFilter: 'blur(10px)',
        backgroundColor: theme => theme.palette.mode === 'dark' 
          ? alpha(theme.palette.background.paper, 0.8)
          : alpha(theme.palette.background.paper, 0.8),
        transition: 'all 0.3s ease',
        '&:hover': {
          boxShadow: theme => `0 4px 20px ${alpha(theme.palette.primary.main, 0.1)}`
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
          borderBottom: expanded ? theme => `1px solid ${theme.palette.divider}` : 'none',
          cursor: 'pointer',
          '&:hover': {
            backgroundColor: theme => theme.palette.mode === 'dark' 
              ? alpha(theme.palette.primary.main, 0.05)
              : alpha(theme.palette.primary.main, 0.03),
          }
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <AccountTreeIcon sx={{ 
            mr: 1.5, 
            color: theme => theme.palette.mode === 'dark' ? theme.palette.info.light : theme.palette.info.main 
          }} />
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
              backgroundColor: theme => theme.palette.mode === 'dark' 
                ? alpha(theme.palette.info.main, 0.2)
                : alpha(theme.palette.info.main, 0.1),
              color: theme => theme.palette.mode === 'dark' 
                ? theme.palette.info.light
                : theme.palette.info.main,
            }} 
          />
          <Chip 
            label={`${entityTypeCount} categories`}
            size="small" 
            sx={{ 
              ml: 0.5, 
              height: '20px',
              fontSize: '0.7rem',
              backgroundColor: theme => theme.palette.mode === 'dark' 
                ? alpha(theme.palette.background.default, 0.4)
                : alpha(theme.palette.background.default, 0.4),
              color: 'text.secondary',
            }} 
          />
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <Tooltip title="Filter results">
            <IconButton 
              size="small" 
              onClick={(e) => {
                e.stopPropagation();
                // Add filter functionality if needed
              }}
              sx={{ mr: 1, borderRadius: '10px' }}
            >
              <FilterAltIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <IconButton 
            size="small" 
            onClick={(e) => {
              e.stopPropagation();
              toggleExpanded();
            }}
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
            {Object.entries(entities).map(([type, items]) => {
              if (items.length === 0) return null;
              
              return (
                <React.Fragment key={type}>
                  <ListItemButton 
                    sx={{ 
                      py: 1.5,
                      px: 3,
                      backgroundColor: theme => theme.palette.mode === 'dark' 
                        ? alpha(theme.palette.background.default, 0.4)
                        : alpha(theme.palette.background.default, 0.4),
                    }}
                  >
                    <ListItemIcon sx={{ minWidth: 40 }}>
                      {getEntityIcon(type)}
                    </ListItemIcon>
                    <ListItemText 
                      primary={
                        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                          {getEntityTypeLabel(type)}
                        </Typography>
                      } 
                    />
                    <Chip 
                      label={items.length} 
                      size="small" 
                      sx={{ 
                        height: '20px', 
                        minWidth: '20px',
                        fontSize: '0.7rem',
                        backgroundColor: theme => alpha(theme.palette.background.paper, 0.7),
                      }} 
                    />
                  </ListItemButton>
                  
                  <Divider />
                  
                  {items.map((entity, index) => (
                    <React.Fragment key={entity.id || index}>
                      <ListItemButton 
                        onClick={() => toggleEntityExpanded(entity.id)}
                        sx={{ 
                          py: 2,
                          px: 3,
                          pl: 4,
                          '&:hover': {
                            backgroundColor: theme => theme.palette.mode === 'dark' 
                              ? alpha(theme.palette.primary.main, 0.1)
                              : alpha(theme.palette.primary.main, 0.05),
                          }
                        }}
                      >
                        <ListItemText 
                          primary={
                            <Box sx={{ display: 'flex', alignItems: 'center' }}>
                              <Typography variant="body2" sx={{ fontWeight: 500 }}>
                                {entity.displayName || 
                                 entity.name || 
                                 (entity.genes && entity.genes.length > 0 ? entity.genes[0] : null) || 
                                 formatEntityName(entity.id, null)}
                              </Typography>
                              {entity.id && (
                                <Chip 
                                  label={entity.id.split(':')[0]} 
                                  size="small" 
                                  sx={{ 
                                    ml: 1, 
                                    height: '18px', 
                                    fontSize: '0.65rem',
                                    backgroundColor: theme => {
                                      // Color based on entity type
                                      const dbPrefix = entity.id.split(':')[0].toLowerCase();
                                      if (dbPrefix === 'ncbigene' || dbPrefix === 'ensembl') {
                                        return alpha(theme.palette.success.main, 0.1);
                                      } else if (dbPrefix === 'uniprot') {
                                        return alpha(theme.palette.info.main, 0.1);
                                      } else if (dbPrefix === 'drugbank' || dbPrefix === 'chembl') {
                                        return alpha(theme.palette.warning.main, 0.1);
                                      } else if (dbPrefix === 'mondo' || dbPrefix === 'mesh' || dbPrefix === 'omim') {
                                        return alpha(theme.palette.error.main, 0.1);
                                      }
                                      return alpha(theme.palette.info.main, 0.1);
                                    },
                                    color: theme => {
                                      // Color based on entity type
                                      const dbPrefix = entity.id.split(':')[0].toLowerCase();
                                      if (dbPrefix === 'ncbigene' || dbPrefix === 'ensembl') {
                                        return theme.palette.success.main;
                                      } else if (dbPrefix === 'uniprot') {
                                        return theme.palette.info.main;
                                      } else if (dbPrefix === 'drugbank' || dbPrefix === 'chembl') {
                                        return theme.palette.warning.main;
                                      } else if (dbPrefix === 'mondo' || dbPrefix === 'mesh' || dbPrefix === 'omim') {
                                        return theme.palette.error.main;
                                      }
                                      return theme.palette.info.main;
                                    }
                                  }} 
                                />
                              )}
                              
                              {entity.symbol && entity.symbol !== entity.displayName && (
                                <Chip 
                                  label={entity.symbol}
                                  size="small"
                                  sx={{ 
                                    ml: 1, 
                                    height: '18px', 
                                    fontSize: '0.65rem',
                                    backgroundColor: theme => alpha(theme.palette.success.light, 0.1),
                                    color: 'success.main'
                                  }}
                                />
                              )}
                            </Box>
                          }
                          secondary={
                            <Box sx={{ display: 'flex', alignItems: 'center' }}>
                              <Typography variant="caption" color="text.secondary" sx={{ mr: 1 }}>
                                {entity.id}
                              </Typography>
                              
                              {entity.organism && (
                                <Chip 
                                  label={entity.organism.includes('sapiens') ? 'Human' : entity.organism.split(' ')[0]}
                                  size="small"
                                  sx={{ 
                                    height: '16px',
                                    fontSize: '0.6rem',
                                    backgroundColor: theme => alpha(theme.palette.background.default, 0.8)
                                  }}
                                />
                              )}
                            </Box>
                          }
                        />
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          {entity.id && (
                            <Tooltip title="View in external database">
                              <IconButton 
                                size="small" 
                                component={Link}
                                href={generateExternalLink(entity.id)}
                                target="_blank"
                                rel="noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                sx={{ mr: 1, fontSize: '0.9rem' }}
                              >
                                <OpenInNewIcon fontSize="inherit" />
                              </IconButton>
                            </Tooltip>
                          )}
                          <IconButton 
                            size="small"
                            sx={{ transform: expandedEntities[entity.id] ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.3s' }}
                          >
                            <ExpandMoreIcon fontSize="small" />
                          </IconButton>
                        </Box>
                      </ListItemButton>
                      
                      <Collapse in={expandedEntities[entity.id]}>
                        <Box sx={{ px: 3, py: 2, backgroundColor: theme => alpha(theme.palette.background.default, 0.3) }}>
                          <Grid container spacing={2}>
                            <Grid item xs={12}>
                              <Card variant="outlined" sx={{ borderRadius: '12px' }}>
                                <CardContent>
                                  <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                                    <InfoOutlinedIcon fontSize="small" sx={{ mr: 1, color: 'info.main' }} />
                                    Entity Information
                                  </Typography>
                                  
                                  <Box sx={{ mb: 2 }}>
                                    {entitySummaries[entity.id]?.loading ? (
                                      <Box sx={{ display: 'flex', alignItems: 'center', my: 1 }}>
                                        <CircularProgress size={16} thickness={5} sx={{ mr: 1 }} />
                                        <Typography variant="body2" color="text.secondary">
                                          Loading information from biological databases...
                                        </Typography>
                                      </Box>
                                    ) : entitySummaries[entity.id]?.text ? (
                                      <Box>
                                        <Typography variant="body2" sx={{ mb: 2 }} component="div">
                                          <div dangerouslySetInnerHTML={{ 
                                            __html: entitySummaries[entity.id].text
                                                    .replace(/\(cite:.+?\)/g, '')
                                                    .replace(/([A-Z][A-Z0-9_-]+\d*)/g, '<strong>$1</strong>') 
                                          }} />
                                        </Typography>
                                        
                                        {/* Display entity metadata from fetched data */}
                                        {entitySummaries[entity.id].data && (
                                          <Box sx={{ 
                                            mt: 2, 
                                            display: 'flex',
                                            gap: 1,
                                            flexDirection: 'row',
                                            flexWrap: 'wrap'
                                          }}>
                                            {/* Gene-specific metadata - We've moved this to detail section */}
                                            {entitySummaries[entity.id].data.symbol && type !== 'genes' && (
                                              <Chip 
                                                label={`Symbol: ${entitySummaries[entity.id].data.symbol}`}
                                                size="small"
                                                sx={{ fontSize: '0.7rem' }}
                                              />
                                            )}
                                            
                                            {/* Protein-specific metadata */}
                                            {entitySummaries[entity.id].data.geneName && (
                                              <Chip 
                                                label={`Gene: ${entitySummaries[entity.id].data.geneName}`}
                                                size="small"
                                                sx={{ fontSize: '0.7rem' }}
                                              />
                                            )}
                                            
                                            {/* Length info (e.g. for proteins) */}
                                            {entitySummaries[entity.id].data.length && (
                                              <Chip 
                                                label={`Length: ${entitySummaries[entity.id].data.length} aa`}
                                                size="small"
                                                sx={{ fontSize: '0.7rem' }}
                                              />
                                            )}
                                            
                                            {entitySummaries[entity.id].data.organism && (
                                              <Chip 
                                                label={entitySummaries[entity.id].data.organism}
                                                size="small"
                                                sx={{ fontSize: '0.7rem' }}
                                              />
                                            )}
                                          </Box>
                                        )}
                                      </Box>
                                    ) : (
                                      <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                                        Click the external link to view detailed information about this entity.
                                      </Typography>
                                    )}
                                  </Box>
                                  
                                  {/* Display entity-specific details */}
                                  {/* Gene details */}
                                  {type === 'genes' && (
                                    <Box sx={{ mt: 2 }}>
                                      {/* Official Symbol */}
                                      {entitySummaries[entity.id]?.data?.symbol && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Official Symbol:</strong> {entitySummaries[entity.id].data.symbol}
                                        </Typography>
                                      )}
                                      
                                      {/* Summary */}
                                      {entitySummaries[entity.id]?.data?.summary && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Summary:</strong> {entitySummaries[entity.id].data.summary}
                                        </Typography>
                                      )}
                                      
                                      {entity.all_names && entity.all_names.length > 0 && (
                                        <>
                                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            Alternative names:
                                          </Typography>
                                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1.5 }}>
                                            {entity.all_names.map((name, i) => (
                                              <Chip 
                                                key={i} 
                                                label={name} 
                                                size="small" 
                                                sx={{ 
                                                  height: '20px', 
                                                  fontSize: '0.7rem' 
                                                }}
                                              />
                                            ))}
                                          </Box>
                                        </>
                                      )}
                                      
                                      {entity.chromosome && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Chromosome:</strong> {entity.chromosome}
                                        </Typography>
                                      )}
                                      
                                      {entity.ensembl && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Ensembl ID:</strong> {entity.ensembl}
                                        </Typography>
                                      )}
                                      
                                      {entity.genes && entity.genes.length > 0 && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Gene Symbol:</strong> {entity.genes.join(', ')}
                                        </Typography>
                                      )}
                                      
                                      {entity.organism && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Organism:</strong> {entity.organism}
                                        </Typography>
                                      )}
                                    </Box>
                                  )}
                                  
                                  {/* Protein details */}
                                  {type === 'proteins' && (
                                    <Box sx={{ mt: 2 }}>
                                      {entity.synonyms && entity.synonyms.length > 0 && (
                                        <>
                                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            Synonyms:
                                          </Typography>
                                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1.5 }}>
                                            {entity.synonyms.slice(0, 5).map((name, i) => (
                                              <Chip 
                                                key={i} 
                                                label={name} 
                                                size="small" 
                                                sx={{ 
                                                  height: '20px', 
                                                  fontSize: '0.7rem' 
                                                }}
                                              />
                                            ))}
                                            {entity.synonyms.length > 5 && (
                                              <Chip 
                                                label={`+${entity.synonyms.length - 5} more`}
                                                size="small"
                                                sx={{ height: '20px', fontSize: '0.7rem' }}
                                              />
                                            )}
                                          </Box>
                                        </>
                                      )}
                                      
                                      {entity.genes && entity.genes.length > 0 && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Gene:</strong> {entity.genes.join(', ')}
                                        </Typography>
                                      )}
                                      
                                      {entity.organism && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Organism:</strong> {entity.organism}
                                        </Typography>
                                      )}
                                      
                                      {entity.molecularWeight && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Molecular Weight:</strong> {entity.molecularWeight} Da
                                        </Typography>
                                      )}
                                    </Box>
                                  )}
                                  
                                  {/* Disease details */}
                                  {type === 'diseases' && (
                                    <Box sx={{ mt: 2 }}>
                                      {entity.synonyms && entity.synonyms.length > 0 && (
                                        <>
                                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            Alternative disease names:
                                          </Typography>
                                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1.5 }}>
                                            {entity.synonyms.slice(0, 5).map((name, i) => (
                                              <Chip 
                                                key={i} 
                                                label={name} 
                                                size="small" 
                                                sx={{ 
                                                  height: '20px', 
                                                  fontSize: '0.7rem',
                                                  backgroundColor: theme => alpha(theme.palette.error.main, 0.1),
                                                  color: 'error.main'
                                                }}
                                              />
                                            ))}
                                            {entity.synonyms.length > 5 && (
                                              <Chip 
                                                label={`+${entity.synonyms.length - 5} more`}
                                                size="small"
                                                sx={{ height: '20px', fontSize: '0.7rem' }}
                                              />
                                            )}
                                          </Box>
                                        </>
                                      )}
                                      
                                      {/* Disease-specific fields */}
                                      {entity.type && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Type:</strong> {entity.type}
                                        </Typography>
                                      )}
                                      
                                      {entity.category && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Category:</strong> {entity.category}
                                        </Typography>
                                      )}
                                      
                                      {/* MONDO-specific links */}
                                      {entity.id && entity.id.toLowerCase().includes('mondo') && (
                                        <Box sx={{ mt: 1 }}>
                                          <Link 
                                            href={`https://monarchinitiative.org/disease/${entity.id}`}
                                            target="_blank"
                                            rel="noopener"
                                            sx={{ display: 'flex', alignItems: 'center', fontSize: '0.8rem' }}
                                          >
                                            <OpenInNewIcon fontSize="inherit" sx={{ mr: 0.5 }} />
                                            View in Monarch Initiative
                                          </Link>
                                        </Box>
                                      )}
                                    </Box>
                                  )}
                                  
                                  {/* Drug details */}
                                  {(type === 'drugs' || type === 'compounds') && (
                                    <Box sx={{ mt: 2 }}>
                                      {/* SMILES */}
                                      {entitySummaries[entity.id]?.data?.smiles && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>SMILES:</strong> {entitySummaries[entity.id].data.smiles}
                                        </Typography>
                                      )}
                                      
                                      {/* Summary */}
                                      {entitySummaries[entity.id]?.data?.summary && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Summary:</strong> {entitySummaries[entity.id].data.summary}
                                        </Typography>
                                      )}
                                      
                                      {/* Groups */}
                                      {entitySummaries[entity.id]?.data?.groups && entitySummaries[entity.id].data.groups.length > 0 && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Groups:</strong> {entitySummaries[entity.id].data.groups.join(', ')}
                                        </Typography>
                                      )}
                                      
                                      {/* Chemical Formula */}
                                      {entitySummaries[entity.id]?.data?.chemicalFormula && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Chemical Formula:</strong> {entitySummaries[entity.id].data.chemicalFormula}
                                        </Typography>
                                      )}
                                      
                                      {/* Alternative names */}
                                      {entity.synonyms && entity.synonyms.length > 0 && (
                                        <>
                                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            Alternative names:
                                          </Typography>
                                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                                            {entity.synonyms.slice(0, 5).map((name, i) => (
                                              <Chip 
                                                key={i} 
                                                label={name} 
                                                size="small" 
                                                sx={{ 
                                                  height: '20px', 
                                                  fontSize: '0.7rem' 
                                                }}
                                              />
                                            ))}
                                            {entity.synonyms.length > 5 && (
                                              <Chip 
                                                label={`+${entity.synonyms.length - 5} more`}
                                                size="small"
                                                sx={{ height: '20px', fontSize: '0.7rem' }}
                                              />
                                            )}
                                          </Box>
                                        </>
                                      )}
                                    </Box>
                                  )}
                                  
                                  {type === 'proteins' && entity.sequences && entity.sequences.length > 0 && (
                                    <Box sx={{ mt: 2 }}>
                                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                        Sequence preview:
                                      </Typography>
                                      <Box sx={{ 
                                        p: 1, 
                                        backgroundColor: theme => alpha(theme.palette.background.default, 0.6),
                                        borderRadius: 1,
                                        overflowX: 'auto'
                                      }}>
                                        <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                                          {entity.sequences[0]?.substring(0, 50)}...
                                        </Typography>
                                      </Box>
                                    </Box>
                                  )}
                                  
                                  {(type === 'drugs' || type === 'diseases') && entity.synonyms && entity.synonyms.length > 0 && (
                                    <Box sx={{ mt: 2 }}>
                                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                        Synonyms:
                                      </Typography>
                                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                                        {entity.synonyms.map((synonym, i) => (
                                          <Chip 
                                            key={i} 
                                            label={synonym} 
                                            size="small" 
                                            sx={{ 
                                              height: '20px', 
                                              fontSize: '0.7rem' 
                                            }}
                                          />
                                        ))}
                                      </Box>
                                    </Box>
                                  )}
                                  
                                  {/* GO Term details */}
                                  {type === 'goterms' && (
                                    <Box sx={{ mt: 2 }}>
                                      {/* GO Term namespace/aspect */}
                                      {entitySummaries[entity.id]?.data?.namespace && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Namespace:</strong> {entitySummaries[entity.id].data.namespace}
                                        </Typography>
                                      )}
                                      
                                      {/* GO ID */}
                                      {entitySummaries[entity.id]?.data?.goId && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>GO ID:</strong> {entitySummaries[entity.id].data.goId}
                                        </Typography>
                                      )}
                                      
                                      {/* Definition (separate from description) */}
                                      {entitySummaries[entity.id]?.data?.definition && 
                                       entitySummaries[entity.id].data.definition !== 'No definition available' && (
                                        <Typography variant="body2" sx={{ mb: 0.5 }}>
                                          <strong>Definition:</strong> {entitySummaries[entity.id].data.definition}
                                        </Typography>
                                      )}
                                      
                                      {/* Obsolete status warning */}
                                      {entitySummaries[entity.id]?.data?.isObsolete && (
                                        <Box sx={{ mb: 1 }}>
                                          <Chip 
                                            label="Obsolete Term"
                                            size="small"
                                            color="warning"
                                            sx={{ 
                                              fontSize: '0.7rem',
                                              backgroundColor: theme => alpha(theme.palette.warning.main, 0.2),
                                              color: 'warning.main'
                                            }}
                                          />
                                        </Box>
                                      )}
                                      
                                      {/* GO Term synonyms */}
                                      {entitySummaries[entity.id]?.data?.synonyms && 
                                       entitySummaries[entity.id].data.synonyms.length > 0 && (
                                        <>
                                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            Synonyms:
                                          </Typography>
                                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1.5 }}>
                                            {entitySummaries[entity.id].data.synonyms.slice(0, 5).map((synonym, i) => (
                                              <Chip 
                                                key={i} 
                                                label={synonym} 
                                                size="small" 
                                                sx={{ 
                                                  height: '20px', 
                                                  fontSize: '0.7rem',
                                                  backgroundColor: theme => alpha(theme.palette.info.main, 0.1),
                                                  color: 'info.main'
                                                }}
                                              />
                                            ))}
                                            {entitySummaries[entity.id].data.synonyms.length > 5 && (
                                              <Chip 
                                                label={`+${entitySummaries[entity.id].data.synonyms.length - 5} more`}
                                                size="small"
                                                sx={{ height: '20px', fontSize: '0.7rem' }}
                                              />
                                            )}
                                          </Box>
                                        </>
                                      )}
                                      
                                      {/* Cross-references */}
                                      {entitySummaries[entity.id]?.data?.crossReferences && 
                                       entitySummaries[entity.id].data.crossReferences.length > 0 && (
                                        <>
                                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            Cross-references:
                                          </Typography>
                                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1.5 }}>
                                            {entitySummaries[entity.id].data.crossReferences.slice(0, 3).map((xref, i) => (
                                              <Chip 
                                                key={i} 
                                                label={xref} 
                                                size="small" 
                                                sx={{ 
                                                  height: '20px', 
                                                  fontSize: '0.7rem',
                                                  backgroundColor: theme => alpha(theme.palette.secondary.main, 0.1),
                                                  color: 'secondary.main'
                                                }}
                                              />
                                            ))}
                                            {entitySummaries[entity.id].data.crossReferences.length > 3 && (
                                              <Chip 
                                                label={`+${entitySummaries[entity.id].data.crossReferences.length - 3} more`}
                                                size="small"
                                                sx={{ height: '20px', fontSize: '0.7rem' }}
                                              />
                                            )}
                                          </Box>
                                        </>
                                      )}
                                      
                                      {/* Link to AmiGO */}
                                      {entitySummaries[entity.id]?.data?.url && (
                                        <Box sx={{ mt: 1 }}>
                                          <Link 
                                            href={entitySummaries[entity.id].data.url}
                                            target="_blank"
                                            rel="noopener"
                                            sx={{ display: 'flex', alignItems: 'center', fontSize: '0.8rem' }}
                                          >
                                            <OpenInNewIcon fontSize="inherit" sx={{ mr: 0.5 }} />
                                            View in AmiGO
                                          </Link>
                                        </Box>
                                      )}
                                    </Box>
                                  )}
                                </CardContent>
                              </Card>
                            </Grid>
                          </Grid>
                        </Box>
                      </Collapse>
                      
                      {index < items.length - 1 && (
                        <Divider sx={{ ml: 4 }} />
                      )}
                    </React.Fragment>
                  ))}
                  
                  {Object.entries(entities).findIndex(([t]) => t === type) < 
                   Object.entries(entities).filter(([_, arr]) => arr.length > 0).length - 1 && (
                    <Divider />
                  )}
                </React.Fragment>
              );
            })}
          </List>
        )}
      </Collapse>
    </Paper>
  );
}

export default NodeVisualization;
