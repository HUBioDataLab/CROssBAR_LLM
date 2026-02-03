import React from 'react';
import BiotechIcon from '@mui/icons-material/Biotech';
import SourceIcon from '@mui/icons-material/Source';
import MedicationIcon from '@mui/icons-material/Medication';
import HealthAndSafetyIcon from '@mui/icons-material/HealthAndSafety';
import SchemaIcon from '@mui/icons-material/Schema';
import AccountTreeIcon from '@mui/icons-material/AccountTree';

/**
 * Get icon component for entity type.
 */
export const getEntityIcon = (type) => {
  switch (type) {
    case 'genes':
      return <BiotechIcon />;
    case 'proteins':
      return <SourceIcon />;
    case 'drugs':
    case 'compounds':
      return <MedicationIcon />;
    case 'diseases':
    case 'phenotypes':
    case 'sideeffects':
      return <HealthAndSafetyIcon />;
    case 'pathways':
    case 'ecnumbers':
      return <SchemaIcon />;
    case 'domains':
      return <AccountTreeIcon />;
    case 'organisms':
      return <BiotechIcon />;
    case 'goterms':
      return <SourceIcon />;
    default:
      return <AccountTreeIcon />;
  }
};

/**
 * Get human-readable label for entity type.
 */
export const getEntityTypeLabel = (type) => {
  const labels = {
    genes: 'Genes',
    proteins: 'Proteins',
    drugs: 'Drugs',
    compounds: 'Chemical Compounds',
    diseases: 'Diseases',
    pathways: 'Pathways',
    domains: 'Protein Domains',
    organisms: 'Organisms',
    goterms: 'GO Terms',
    phenotypes: 'Phenotypes',
    sideeffects: 'Side Effects',
    ecnumbers: 'EC Numbers',
  };
  return labels[type] || type.charAt(0).toUpperCase() + type.slice(1);
};

/**
 * Get entity type from ID prefix.
 */
export const getEntityTypeFromId = (id) => {
  if (!id || typeof id !== 'string') return null;

  const prefix = id.split(':')[0].toLowerCase();

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
      if (id.includes('pathway') || id.includes('path:')) return 'pathways';
      if (id.includes('gene')) return 'genes';
      if (id.includes('protein')) return 'proteins';
      if (id.includes('phenotype') || id.includes('HP:')) return 'phenotypes';
      if (id.includes('GO:')) return 'goterms';
      if (id.includes('disease') || id.includes('disorder')) return 'diseases';
      return null;
  }
};

/**
 * Get color for database prefix chip.
 */
export const getDbPrefixColors = (dbPrefix, theme) => {
  const prefix = dbPrefix.toLowerCase();
  
  if (prefix === 'ncbigene' || prefix === 'ensembl') {
    return {
      bg: theme.palette.success.main,
      bgAlpha: 0.1,
    };
  } else if (prefix === 'uniprot') {
    return {
      bg: theme.palette.info.main,
      bgAlpha: 0.1,
    };
  } else if (prefix === 'drugbank' || prefix === 'chembl') {
    return {
      bg: theme.palette.warning.main,
      bgAlpha: 0.1,
    };
  } else if (prefix === 'mondo' || prefix === 'mesh' || prefix === 'omim') {
    return {
      bg: theme.palette.error.main,
      bgAlpha: 0.1,
    };
  }
  
  return {
    bg: theme.palette.info.main,
    bgAlpha: 0.1,
  };
};

/**
 * Initial entity container structure.
 */
export const createEmptyEntityContainer = () => ({
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
  ecnumbers: [],
});
