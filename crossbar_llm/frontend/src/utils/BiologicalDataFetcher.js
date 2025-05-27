/**
 * BiologicalDataFetcher.js
 * Utility functions for fetching biological entity data from public resources
 */

/**
 * Fetch gene summary from NCBI Entrez Gene
 * @param {string} geneId - The NCBI Gene ID 
 */
export const fetchGeneSummary = async (geneId) => {
  if (!geneId) return null;
  
  // Extract just the numeric part if it's in the format "ncbigene:1234"
  const numericId = geneId.includes(':') ? geneId.split(':')[1] : geneId;
  
  try {
    // NCBI provides an API for fetching gene summaries
    const response = await fetch(`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&id=${numericId}&retmode=json`);
    
    if (!response.ok) {
      throw new Error(`Failed to fetch gene data: ${response.status}`);
    }
    
    const data = await response.json();
    
    // Check if we have a valid result
    if (data.result && data.result[numericId]) {
      const gene = data.result[numericId];
      
      // Extract and process the symbol (short gene name)
      const symbol = gene.symbol || null;
      
      return {
        name: symbol || gene.name || 'Unknown',
        symbol: symbol,
        description: gene.description || 'No description available',
        summary: gene.summary || 'No summary available',
        synonyms: gene.otheraliases ? gene.otheraliases.split(',').map(s => s.trim()) : [],
        chromosome: gene.chromosome || null,
        geneType: gene.type || null,
        organism: gene.organism?.scientificname || null,
        genomicLocation: gene.mapLocation || null,
        displayName: symbol || gene.name || `Gene ${numericId}`
      };
    }
    
    return null;
  } catch (error) {
    console.error('Error fetching gene summary:', error);
    return null;
  }
};

/**
 * Fetch protein data from UniProt
 * @param {string} uniprotId - The UniProt accession number
 */
export const fetchProteinData = async (uniprotId) => {
  if (!uniprotId) return null;
  
  // Extract just the accession part if it's in the format "uniprot:P12345"
  const accession = uniprotId.includes(':') ? uniprotId.split(':')[1] : uniprotId;
  
  try {
    // UniProt API for fetching protein data
    const response = await fetch(`https://rest.uniprot.org/uniprotkb/${accession}.json`);
    
    if (!response.ok) {
      throw new Error(`Failed to fetch protein data: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (data) {
      // Extract primary gene name
      const geneSymbol = data.genes?.[0]?.geneName?.value;
      
      // Get protein name (multiple options in order of preference)
      const proteinName = 
        data.proteinDescription?.recommendedName?.fullName?.value || 
        data.proteinDescription?.submissionNames?.[0]?.fullName?.value || 
        data.proteinDescription?.alternativeNames?.[0]?.fullName?.value ||
        'Unknown protein';
      
      // Extract all alternative names for the protein
      const alternativeNames = [];
      if (data.proteinDescription?.alternativeNames) {
        data.proteinDescription.alternativeNames.forEach(alt => {
          if (alt.fullName?.value) alternativeNames.push(alt.fullName.value);
        });
      }
      
      // Get function annotation
      const functionText = data.comments?.find(c => c.commentType === 'FUNCTION')?.texts?.[0]?.value || 
                           'Function not specified';
      
      // Sometimes UniProt entries have a short/common name in the gene section
      const shortName = data.genes?.[0]?.geneName?.value;
      
      return {
        name: proteinName,
        displayName: geneSymbol || proteinName.split(' ')[0] || accession,
        function: functionText,
        geneName: geneSymbol || 'Unknown',
        geneNames: data.genes?.map(g => g.geneName?.value).filter(Boolean) || [],
        organism: data.organism?.scientificName || 'Unknown organism',
        sequence: data.sequence?.value || '',
        length: data.sequence?.length || null,
        molecularWeight: data.sequence?.molWeight ? (data.sequence.molWeight/1000).toFixed(1) : null,
        alternativeNames: alternativeNames,
        synonyms: [
          ...alternativeNames,
          ...(data.genes || []).flatMap(g => 
            [
              ...(g.geneName ? [g.geneName.value] : []),
              ...(g.synonyms || []).map(s => s.value)
            ]
          )
        ]
      };
    }
    
    return null;
  } catch (error) {
    console.error('Error fetching protein data:', error);
    return null;
  }
};

/**
 * Fetch pathway information from KEGG or Reactome
 * @param {string} pathwayId - The pathway ID (e.g., "kegg.pathway:hsa04010", "reactome:R-HSA-123")
 */
export const fetchPathwayData = async (pathwayId) => {
  if (!pathwayId) return null;
  
  // Extract the database type and ID
  const [dbType, id] = pathwayId.includes(':') ? pathwayId.split(':') : ['kegg', pathwayId];
  const dbTypeLower = dbType.toLowerCase();
  
  try {
    // Handle different pathway databases
    switch(dbTypeLower) {
      case 'kegg.pathway':
      case 'kegg':
        // KEGG pathways are often in format "kegg.pathway:hsa04010"
        return {
          id: pathwayId,
          name: `KEGG Pathway ${id}`,
          description: `Biological pathway from KEGG database with ID ${id}. KEGG pathways represent molecular interaction, reaction and relation networks for metabolism, genetic information processing, environmental information processing and cellular processes.`,
          url: `https://www.genome.jp/kegg-bin/show_pathway?${id}`,
          database: 'KEGG'
        };
        
      case 'reactome':
        // Reactome pathways
        return {
          id: pathwayId,
          name: `Reactome Pathway ${id}`,
          description: `Biological pathway from Reactome database with ID ${id}. Reactome is a free, open-source, curated and peer-reviewed pathway database providing intuitive bioinformatics tools for the visualization, interpretation and analysis of pathway knowledge.`,
          url: `https://reactome.org/content/detail/${id}`,
          database: 'Reactome'
        };
        
      case 'wikipathways':
        // WikiPathways
        return {
          id: pathwayId,
          name: `WikiPathways ${id}`,
          description: `Biological pathway from WikiPathways database with ID ${id}. WikiPathways is an open, collaborative platform dedicated to the curation of biological pathways.`,
          url: `https://www.wikipathways.org/pathways/${id}`,
          database: 'WikiPathways'
        };
        
      default:
        // Generic pathway
        return {
          id: pathwayId,
          name: `Pathway ${id}`,
          description: `Biological pathway with ID ${pathwayId}. Pathways represent series of interactions between molecules in a cell that leads to a certain product or a change in the cell.`,
          url: generateEntityUrl(pathwayId) || '#',
          database: dbType.toUpperCase()
        };
    }
  } catch (error) {
    console.error(`Error fetching pathway data for ${pathwayId}:`, error);
    return {
      id: pathwayId,
      name: `Pathway ${id}`,
      description: `Error retrieving pathway information: ${error.message}`,
      database: dbType.toUpperCase(),
      error: true
    };
  }
};

/**
 * Generate an appropriate URL for an entity based on its identifier
 * @param {string} id - The entity identifier (e.g., "uniprot:P12345")
 */
export const generateEntityUrl = (id) => {
  if (!id) return null;
  
  // Extract the type and ID value
  const parts = id.split(':');
  if (parts.length !== 2) return null;
  
  const [type, value] = parts;
  
  switch (type.toLowerCase()) {
    // Genes
    case 'ncbigene':
      return `https://www.ncbi.nlm.nih.gov/gene/${value}`;
    case 'ensembl':
      return `https://www.ensembl.org/id/${value}`;
      
    // Proteins
    case 'uniprot':
      return `https://www.uniprot.org/uniprotkb/${value}`;
    
    // Domains
    case 'interpro':
      return `https://www.ebi.ac.uk/interpro/entry/InterPro/${value}/`;
    case 'pfam':
      return `https://www.ebi.ac.uk/interpro/entry/pfam/${value}/`;
    
    // Organisms
    case 'ncbitaxon':
      return `https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=${value}`;
      
    // Drugs & Compounds
    case 'drugbank':
      return `https://go.drugbank.com/drugs/${value}`;
    case 'chembl':
      return `https://www.ebi.ac.uk/chembl/compound_report_card/${value}/`;
    case 'chebi':
      return `https://www.ebi.ac.uk/chebi/searchId.do?chebiId=${value}`;
    case 'pubchem.compound':
      return `https://pubchem.ncbi.nlm.nih.gov/compound/${value}`;
      
    // Pathways
    case 'kegg.pathway':
      return `https://www.genome.jp/kegg-bin/show_pathway?${value}`;
    case 'reactome':
      return `https://reactome.org/content/detail/${value}`;
      
    // GO Terms
    case 'go':
      return `http://amigo.geneontology.org/amigo/term/GO:${value}`;
      
    // Diseases & Phenotypes
    case 'mesh':
      return `https://meshb.nlm.nih.gov/record/ui?ui=${value}`;
    case 'mondo':
      return `https://www.ebi.ac.uk/ols/ontologies/mondo/terms?iri=http://purl.obolibrary.org/obo/MONDO_${value}`;
    case 'hp':
      return `https://hpo.jax.org/app/browse/term/HP:${value}`;
    case 'omim':
      return `https://omim.org/entry/${value}`;
      
    // Side Effects
    case 'meddra':
      return `https://identifiers.org/meddra:${value}`;
      
    // EC Numbers
    case 'eccode':
      return `https://enzyme.expasy.org/EC/${value}`;
      
    default:
      // If we don't have a specific mapping, try identifiers.org as a fallback
      return `https://identifiers.org/${type}:${value}`;
  }
};

/**
 * Fetch protein domain information from InterPro
 * @param {string} domainId - The InterPro ID
 */
export const fetchDomainData = async (domainId) => {
  if (!domainId) return null;
  
  // Extract just the ID part
  const id = domainId.includes(':') ? domainId.split(':')[1] : domainId;
  
  try {
    // InterPro provides a REST API
    const response = await fetch(`https://www.ebi.ac.uk/interpro/api/entry/interpro/${id}?format=json`);
    
    if (!response.ok) {
      throw new Error(`Failed to fetch domain data: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (data) {
      return {
        name: data.metadata?.name || 'Unknown',
        type: data.metadata?.type || 'Unknown type',
        description: data.metadata?.description?.[0]?.text || 'No description available'
      };
    }
    
    return null;
  } catch (error) {
    console.error('Error fetching protein domain data:', error);
    return null;
  }
};

/**
 * Fetch disease information from MONDO
 * @param {string} mondoId - The MONDO ID
 */
export const fetchDiseaseData = async (diseaseId) => {
  if (!diseaseId) return null;
  
  // Extract the type and ID
  const [type, id] = diseaseId.includes(':') ? diseaseId.split(':') : ['unknown', diseaseId];
  
  // Different handling based on disease database
  switch(type.toLowerCase()) {
    case 'mondo':
      // For MONDO IDs, we could use OLS API, but for this example we'll return placeholder data
      return {
        id: diseaseId,
        name: `MONDO Disease ${id}`,
        description: `Disease or disorder with ID ${id} from the Mondo Disease Ontology.`
      };
      
    case 'mesh':
      // For MeSH terms, similar placeholder
      return {
        id: diseaseId,
        name: `MeSH Term ${id}`,
        description: `Medical subject heading with ID ${id} from the Medical Subject Headings vocabulary.`
      };
      
    default:
      return {
        id: diseaseId,
        name: `Disease ${id}`,
        description: `Disease or medical condition with ID ${diseaseId}.`
      };
  }
};

/**
 * Fetch drug information from DrugBank or other sources
 * @param {string} drugId - The drug identifier
 */
export const fetchDrugData = async (drugId) => {
  if (!drugId) return null;
  
  // Extract the type and ID
  const [type, id] = drugId.includes(':') ? drugId.split(':') : ['unknown', drugId];
  let dbType = type.toLowerCase();
  
  try {
    // Different handling based on drug database
    switch(dbType) {
      case 'drugbank':
        // DrugBank requires authentication API key, using placeholder data
        return {
          id: drugId,
          name: `DrugBank ${id}`,
          description: `Pharmaceutical compound with ID ${id} from DrugBank.`,
          smiles: "No SMILES available", 
          summary: `A pharmaceutical compound from DrugBank with ID ${id}. This drug may be used for various therapeutic purposes.`,
          groups: ["Small molecule", "Approved", "Investigational"],
          chemicalFormula: "Not available" 
        };
        
      case 'chembl':
        // ChEMBL has a public REST API
        const chemblResponse = await fetch(`https://www.ebi.ac.uk/chembl/api/data/molecule/${id}.json`);
        
        if (!chemblResponse.ok) {
          throw new Error(`Failed to fetch ChEMBL data: ${chemblResponse.status}`);
        }
        
        const chemblData = await chemblResponse.json();
        
        return {
          id: drugId,
          name: chemblData.pref_name || `ChEMBL Compound ${id}`,
          description: chemblData.molecule_properties?.full_molformula ? 
            `Chemical compound ${chemblData.pref_name || id} with formula ${chemblData.molecule_properties.full_molformula}` : 
            `Chemical compound with ID ${id} from ChEMBL database.`,
          smiles: chemblData.molecule_structures?.canonical_smiles || "Not available",
          summary: chemblData.molecule_properties?.full_mwt ? 
            `${chemblData.pref_name || 'Chemical compound'} with molecular weight of ${chemblData.molecule_properties.full_mwt} from ChEMBL database.` :
            `A chemical compound from ChEMBL database with ID ${id}.`,
          groups: [
            chemblData.molecule_type || "Small molecule",
            ...(chemblData.black_box_warning ? ["Black box warning"] : []),
            ...(chemblData.chirality === 1 ? ["Chiral compound"] : []),
            ...(chemblData.oral ? ["Oral administration"] : []),
            ...(chemblData.parenteral ? ["Parenteral administration"] : []),
            ...(chemblData.topical ? ["Topical administration"] : []),
            ...(chemblData.first_approval ? [`Approved in ${chemblData.first_approval}`] : [])
          ],
          chemicalFormula: chemblData.molecule_properties?.full_molformula || "Not available"
        };
        
      case 'pubchem.compound':
        // PubChem has a public REST API
        const pubchemResponse = await fetch(`https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/${id}/property/IUPACName,MolecularFormula,MolecularWeight,CanonicalSMILES/JSON`);
        
        if (!pubchemResponse.ok) {
          throw new Error(`Failed to fetch PubChem data: ${pubchemResponse.status}`);
        }
        
        const pubchemData = await pubchemResponse.json();
        const compound = pubchemData.PropertyTable.Properties[0];
        
        // Get additional information for the summary
        const pubchemClassificationResponse = await fetch(`https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/${id}/classification/JSON`);
        let classification = [];
        
        if (pubchemClassificationResponse.ok) {
          const classData = await pubchemClassificationResponse.json();
          if (classData.Hierarchies && classData.Hierarchies.length > 0) {
            classification = classData.Hierarchies.map(h => 
              h.Node?.Information?.Name || h.Node?.Information?.Description
            ).filter(Boolean);
          }
        }
        
        return {
          id: drugId,
          name: compound.IUPACName || `PubChem Compound ${id}`,
          description: `Chemical compound with ID ${id} from PubChem with formula ${compound.MolecularFormula || 'unknown'}.`,
          smiles: compound.CanonicalSMILES || "Not available",
          summary: `${compound.IUPACName || 'Chemical compound'} with molecular weight of ${compound.MolecularWeight || 'unknown'} from PubChem.`,
          groups: classification.length > 0 ? classification : ["Chemical compound"],
          chemicalFormula: compound.MolecularFormula || "Not available"
        };
        
      case 'chebi':
        // ChEBI has a public REST API with JSON endpoint
        const chebiId = id.replace('CHEBI:', ''); // Remove CHEBI: prefix if present
        const chebiResponse = await fetch(`https://www.ebi.ac.uk/chebi/webServices/rest/getCompleteEntity?chebiId=${chebiId}&format=json`);
        
        if (!chebiResponse.ok) {
          throw new Error(`Failed to fetch ChEBI data: ${chebiResponse.status}`);
        }
        
        const chebiData = await chebiResponse.json();
        
        // Extract relevant fields from the JSON response
        const chebiEntity = chebiData?.chebiEntity || {};
        const chebiName = chebiEntity?.chebiAsciiName;
        const chebiFormula = chebiEntity?.molecularFormula;
        const chebiSmiles = chebiEntity?.smiles;
        const chebiDefinition = chebiEntity?.definition;
        
        // Extract ChEBI classes from ontology parents
        const chebiClasses = [];
        if (chebiEntity?.ontologyParents?.length > 0) {
          chebiEntity.ontologyParents.forEach(parent => {
            if (parent?.chebiName) {
              chebiClasses.push(parent.chebiName);
            }
          });
        }
        
        return {
          id: drugId,
          name: chebiName || `ChEBI ${id}`,
          description: chebiDefinition || `Chemical compound with ID ${id} from ChEBI.`,
          smiles: chebiSmiles || "Not available",
          summary: chebiDefinition || `A chemical compound from Chemical Entities of Biological Interest (ChEBI) with ID ${id}.`,
          groups: chebiClasses.length > 0 ? chebiClasses.slice(0, 5) : ["ChEBI compound"],
          chemicalFormula: chebiFormula || "Not available"
        };
        
        
      default:
        return {
          id: drugId,
          name: `Drug/Compound ${id}`,
          description: `Pharmaceutical compound or chemical with ID ${drugId}.`,
          smiles: "Not available",
          summary: `A pharmaceutical compound or chemical substance with identifier ${drugId}.`,
          groups: ["Unknown"],
          chemicalFormula: "Unknown"
        };
    }
  } catch (error) {
    console.error(`Error fetching drug data for ${drugId}:`, error);
    // Return a fallback object with error information
    return {
      id: drugId,
      name: `${dbType.toUpperCase()} ${id}`,
      description: `Error retrieving information: ${error.message}`,
      smiles: "Not available",
      summary: `Unable to fetch data for this compound from ${dbType}.`,
      groups: ["Error"],
      chemicalFormula: "Not available",
      error: true
    };
  }
};

/**
 * Fetch GO term information
 * @param {string} goId - The Gene Ontology term ID
 */
export const fetchGOTermData = async (goId) => {
  if (!goId) return null;
  
  // Extract the numeric part of the GO ID
  const id = goId.includes(':') ? goId.split(':')[1] : goId;
  
  try {
    // QuickGO API could be used here
    return {
      id: goId,
      name: `GO Term ${id}`,
      description: `Gene Ontology term with ID ${id}.`
    };
  } catch (error) {
    console.error('Error fetching GO term data:', error);
    return null;
  }
};

/**
 * Fetch phenotype information from HPO
 * @param {string} hpoId - The Human Phenotype Ontology term ID
 */
export const fetchPhenotypeData = async (phenotypeId) => {
  if (!phenotypeId) return null;
  
  // Extract the type and ID
  const [type, id] = phenotypeId.includes(':') ? phenotypeId.split(':') : ['unknown', phenotypeId];
  
  if (type.toLowerCase() === 'hp') {
    return {
      id: phenotypeId,
      name: `HPO Term ${id}`,
      description: `Human phenotype with ID ${id} from the Human Phenotype Ontology.`
    };
  }
  
  return {
    id: phenotypeId,
    name: `Phenotype ${id}`,
    description: `Phenotypic characteristic with ID ${phenotypeId}.`
  };
};

/**
 * Fetch organism information from NCBI Taxonomy
 * @param {string} taxonId - The NCBI Taxonomy ID
 */
export const fetchOrganismData = async (taxonId) => {
  if (!taxonId) return null;
  
  // Extract just the numeric part if it's in the format "ncbitaxon:9606"
  const numericId = taxonId.includes(':') ? taxonId.split(':')[1] : taxonId;
  
  try {
    // NCBI's E-utilities API could be used here
    return {
      id: taxonId,
      name: numericId === '9606' ? 'Homo sapiens' : `Organism ${numericId}`,
      description: numericId === '9606' 
        ? 'Human (Homo sapiens)' 
        : `Organism with taxonomy ID ${numericId}.`
    };
  } catch (error) {
    console.error('Error fetching organism data:', error);
    return null;
  }
};
