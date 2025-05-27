/**
 * Helper functions for CROssBAR UI components
 */

/**
 * Generate external URL for a biological entity based on its ID
 * @param {string} id - The entity identifier (e.g., "uniprot:P12345")
 * @returns {string} - URL to the external resource
 */
export const generateExternalLink = (id) => {
  if (!id) return '#';
  
  // Extract prefix and identifier
  const [prefix, identifier] = id.includes(':') ? id.split(':') : ['unknown', id];
  
  switch(prefix.toLowerCase()) {
    case 'ncbigene':
      return `https://www.ncbi.nlm.nih.gov/gene/${identifier}`;
    case 'uniprot':
      return `https://www.uniprot.org/uniprotkb/${identifier}`;
    case 'kegg':
    case 'kegg.pathway':
      return `https://www.genome.jp/entry/${identifier}`;
    case 'reactome':
      return `https://reactome.org/content/detail/${identifier}`;
    case 'wikipathways':
      return `https://www.wikipathways.org/pathways/${identifier}`;
    case 'interpro':
      return `https://www.ebi.ac.uk/interpro/entry/InterPro/${identifier}/`;
    case 'pfam':
      return `https://pfam.xfam.org/family/${identifier}`;
    case 'mondo':
      return `https://monarchinitiative.org/disease/MONDO:${identifier}`;
    case 'mesh':
      return `https://meshb.nlm.nih.gov/record/ui?ui=${identifier}`;
    case 'omim':
      return `https://www.omim.org/entry/${identifier}`;
    case 'chebi':
      return `https://www.ebi.ac.uk/chebi/searchId.do?chebiId=CHEBI:${identifier}`;
    case 'drugbank':
      return `https://go.drugbank.com/drugs/${identifier}`;
    case 'chembl':
      return `https://www.ebi.ac.uk/chembl/compound_report_card/${identifier}/`;
    case 'pubchem':
    case 'pubchem.compound':
      return `https://pubchem.ncbi.nlm.nih.gov/compound/${identifier}`;
    case 'go':
      return `http://amigo.geneontology.org/amigo/term/GO:${identifier}`;
    case 'hp':
      return `https://hpo.jax.org/app/browse/term/HP:${identifier}`;
    case 'taxon':
    case 'ncbitaxon':
      return `https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=${identifier}`;
    case 'ensembl':
      return `https://www.ensembl.org/id/${identifier}`;
    case 'ec':
    case 'eccode':
      return `https://enzyme.expasy.org/EC/${identifier}`;
    case 'hgnc':
      return `https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/HGNC:${identifier}`;
    case 'orphanet':
      return `https://www.orpha.net/consor/cgi-bin/OC_Exp.php?lng=EN&Expert=${identifier}`;
    case 'icd10':
      return `https://icd.who.int/browse10/2019/en#/${identifier}`;
    case 'icd9':
      return `https://icd9.chrisendres.com/index.php?action=child&recordid=${identifier}`;
    case 'meddra':
      return `https://identifiers.org/meddra:${identifier}`;
    default:
      // Try to guess based on ID format
      if (identifier && identifier.match(/^[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$/)) {
        return `https://www.uniprot.org/uniprotkb/${identifier}`;
      } else if (id.startsWith('ENSG') || id.startsWith('ENST') || id.startsWith('ENSP')) {
        return `https://www.ensembl.org/id/${id}`;
      } else if (id.match(/^\d+$/)) {
        return `https://www.ncbi.nlm.nih.gov/gene/${id}`;
      } else if (id.toLowerCase().includes('pathway')) {
        return `https://identifiers.org/${prefix}:${identifier}`;
      } else if (id.startsWith('HP:')) {
        return `https://hpo.jax.org/app/browse/term/${id}`;
      } else if (id.startsWith('GO:')) {
        return `http://amigo.geneontology.org/amigo/term/${id}`;
      }
      return '#';
  }
};

/**
 * Format an entity name for display from a raw database ID
 * @param {string} id - The entity ID (e.g., "uniprot:P12345") 
 * @param {string} displayName - The name to display (may be null) 
 * @returns {string} - A formatted display name
 */
export const formatEntityName = (id, displayName) => {
  if (displayName && displayName !== 'Unknown') {
    return displayName;
  }
  
  if (!id) return 'Unknown';
  
  // Extract the ID part without the database prefix
  const parts = id.split(':');
  const idPart = parts.length > 1 ? parts[1] : id;
  const prefix = parts.length > 1 ? parts[0].toLowerCase() : '';
  
  switch(prefix) {
    case 'ncbigene':
      return `Gene ${idPart}`;
    case 'uniprot':
      return `Protein ${idPart}`;
    case 'kegg':
    case 'kegg.pathway':
      return `Pathway ${idPart}`;
    case 'reactome':
      return `Pathway ${idPart}`;
    case 'wikipathways':
      return `Pathway ${idPart}`;
    case 'go':
      return `GO term ${idPart}`;
    case 'hp':
      return `Phenotype ${idPart}`;
    case 'mesh':
    case 'mondo':
    case 'omim':
      return `Disease ${idPart}`;
    case 'drugbank':
    case 'chembl':
    case 'pubchem.compound':
    case 'chebi':
      return `Compound ${idPart}`;
    case 'interpro':
    case 'pfam':
      return `Domain ${idPart}`;
    case 'ncbitaxon':
      return `Organism ${idPart}`;
    case 'meddra':
      return `Side Effect ${idPart}`;
    case 'eccode':
      return `Enzyme ${idPart}`;
    default:
      // Try to infer type from keys or patterns
      if (id.includes('pathway')) return `Pathway ${idPart}`;
      if (id.includes('gene')) return `Gene ${idPart}`;
      if (id.includes('protein')) return `Protein ${idPart}`;
      if (id.includes('phenotype') || id.startsWith('HP:')) return `Phenotype ${idPart}`;
      if (id.startsWith('GO:')) return `GO term ${idPart}`;
      if (id.includes('disease')) return `Disease ${idPart}`;
      return idPart;
  }
};
