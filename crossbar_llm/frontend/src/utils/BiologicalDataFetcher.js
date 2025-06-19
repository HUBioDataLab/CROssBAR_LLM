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
        displayName: symbol || gene.name || `Gene ID: ${numericId}`
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
        displayName: geneSymbol || proteinName || accession,
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
      return `https://www.ebi.ac.uk/QuickGO/term/GO:${value}`;
      
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
 * Fetch protein domain information from InterPro and Pfam
 * Enhanced to include entry type information like "Domain", "Family", "Homologous_superfamily", etc.
 * Also fetches source databases, cross-references, and associated GO terms
 * @param {string} domainId - The domain ID (e.g., "interpro:IPR000001", "pfam:PF00001")
 */
export const fetchDomainData = async (domainId) => {
  if (!domainId) return null;
  
  // Extract the database type and ID
  const [dbType, id] = domainId.includes(':') ? domainId.split(':') : ['interpro', domainId];
  const dbTypeLower = dbType.toLowerCase();
  
  try {
    // Handle different domain databases
    switch(dbTypeLower) {
      case 'interpro':
        // InterPro provides a comprehensive REST API
        const interproResponse = await fetch(`https://www.ebi.ac.uk/interpro/api/entry/interpro/${id}?format=json`);
        
        if (!interproResponse.ok) {
          throw new Error(`Failed to fetch InterPro data: ${interproResponse.status}`);
        }
        
        const interproData = await interproResponse.json();
        
        if (interproData) {
          // Extract entry type and its description
          const entryType = interproData.metadata?.type || 'Unknown type';
          const entryTypeName = interproData.metadata?.type?.name || entryType;
          
          // Map InterPro entry types to more readable descriptions
          const entryTypeDescriptions = {
            'Domain': 'Protein domain - a distinct functional and/or structural unit in a protein',
            'Family': 'Protein family - a group of proteins that share common ancestry',
            'Homologous_superfamily': 'Homologous superfamily - proteins with common structural and evolutionary origin',
            'Repeat': 'Protein repeat - a short amino acid sequence that occurs multiple times',
            'Site': 'Active site - region of an enzyme where substrate molecules bind and undergo a chemical reaction',
            'Conserved_site': 'Conserved site - amino acid positions that are conserved across related proteins',
            'Binding_site': 'Binding site - region that binds to specific molecules',
            'PTM': 'Post-translational modification site - amino acid residues that undergo chemical modifications'
          };
          
          const entryTypeDescription = entryTypeDescriptions[entryType] || `${entryType} entry type`;
          
          // Extract source databases and cross-references
          const sourceDatabases = [];
          const crossReferences = [];
          
          if (interproData.metadata?.source_database) {
            sourceDatabases.push(interproData.metadata.source_database);
          }
          
          // Get member database entries (Pfam, PRINTS, etc.)
          if (interproData.metadata?.member_databases) {
            Object.entries(interproData.metadata.member_databases).forEach(([db, entries]) => {
              if (Array.isArray(entries)) {
                entries.forEach(entry => {
                  sourceDatabases.push(`${db}: ${entry}`);
                  crossReferences.push(`${db}:${entry}`);
                });
              }
            });
          }
          
          // Extract GO terms if available
          const goTerms = [];
          if (interproData.metadata?.go_terms && Array.isArray(interproData.metadata.go_terms)) {
            interproData.metadata.go_terms.forEach(go => {
              if (go.identifier && go.name) {
                goTerms.push({
                  id: go.identifier,
                  name: go.name,
                  category: go.category || 'Unknown'
                });
              }
            });
          }
          
          return {
            id: domainId,
            name: interproData.metadata?.name || 'Unknown',
            entryType: entryType,
            entryTypeName: entryTypeName,
            entryTypeDescription: entryTypeDescription,
            description: interproData.metadata?.description?.[0]?.text || 'No description available',
            sourceDatabases: sourceDatabases,
            crossReferences: crossReferences,
            goTerms: goTerms,
            database: 'InterPro',
            displayName: interproData.metadata?.name || `InterPro ${id}`,
            url: `https://www.ebi.ac.uk/interpro/entry/InterPro/${id}/`
          };
        }
        break;
        
      case 'pfam':
        // For Pfam entries, we can also use InterPro API since Pfam is integrated
        const pfamResponse = await fetch(`https://www.ebi.ac.uk/interpro/api/entry/pfam/${id}?format=json`);
        
        if (!pfamResponse.ok) {
          throw new Error(`Failed to fetch Pfam data: ${pfamResponse.status}`);
        }
        
        const pfamData = await pfamResponse.json();
        
        if (pfamData) {
          // Pfam entries are typically protein families
          const entryType = pfamData.metadata?.type || 'Family';
          const entryTypeName = 'Protein Family';
          const entryTypeDescription = 'Protein family - a group of proteins that share sequence homology and often similar function';
          
          // Extract clan information if available (Pfam clans are superfamilies)
          const clanInfo = pfamData.metadata?.clan || null;
          
          return {
            id: domainId,
            name: pfamData.metadata?.name || 'Unknown',
            entryType: entryType,
            entryTypeName: entryTypeName,
            entryTypeDescription: entryTypeDescription,
            description: pfamData.metadata?.description?.[0]?.text || 'No description available',
            clan: clanInfo,
            database: 'Pfam',
            displayName: pfamData.metadata?.name || `Pfam ${id}`,
            url: `https://pfam.xfam.org/family/${id}`
          };
        }
        break;
        
      default:
        // Generic domain entry
        return {
          id: domainId,
          name: `Domain ${id}`,
          entryType: 'Unknown',
          entryTypeName: 'Unknown type',
          entryTypeDescription: 'Protein domain or functional region',
          description: `Protein domain with ID ${domainId}`,
          database: dbType.toUpperCase(),
          displayName: `Domain ${id}`,
          url: generateEntityUrl(domainId) || '#'
        };
    }
    
    return null;
  } catch (error) {
    console.error(`Error fetching domain data for ${domainId}:`, error);
    
    // Return fallback data with error indication
    const cleanId = domainId.includes(':') ? domainId.split(':')[1] : domainId;
    
    return {
      id: domainId,
      name: `Domain ${cleanId}`,
      entryType: 'Unknown',
      entryTypeName: 'Unknown type',
      entryTypeDescription: 'Unable to fetch entry type information',
      description: `Error retrieving domain information: ${error.message}`,
      database: dbType.toUpperCase(),
      error: true,
      displayName: `Domain ${cleanId}`,
      url: generateEntityUrl(domainId) || '#'
    };
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
 * Fetch GO term information from QuickGO API
 * @param {string} goId - The Gene Ontology term ID (e.g., "go:0008150" or "GO:0008150")
 */
export const fetchGOTermData = async (goId) => {
  if (!goId) return null;
  
  // Extract the numeric part of the GO ID and ensure proper format
  let cleanId = goId.includes(':') ? goId.split(':')[1] : goId;
  
  // Ensure GO ID has proper format (GO:0000000)
  if (!cleanId.startsWith('GO:')) {
    // Pad with zeros if needed to make it 7 digits after GO:
    const numericPart = cleanId.replace(/^GO:?/, '');
    cleanId = `GO:${numericPart.padStart(7, '0')}`;
  }
  
  try {
    // QuickGO API endpoint for GO term information
    const response = await fetch(`https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/${cleanId}`, {
      headers: {
        'Accept': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error(`Failed to fetch GO term data: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (data && data.results && data.results.length > 0) {
      const goTerm = data.results[0];
      
      // Extract relevant information
      const name = goTerm.name || 'Unknown GO term';
      const definition = goTerm.definition?.text || 'No definition available';
      const namespace = goTerm.aspect || 'Unknown';
      const isObsolete = goTerm.isObsolete || false;
      
      // Map aspect to readable namespace
      const namespaceMap = {
        'biological_process': 'Biological Process',
        'molecular_function': 'Molecular Function', 
        'cellular_component': 'Cellular Component',
        'F': 'Molecular Function',
        'P': 'Biological Process',
        'C': 'Cellular Component'
      };
      
      const readableNamespace = namespaceMap[namespace] || namespace;
      
      // Extract synonyms if available
      const synonyms = [];
      if (goTerm.synonyms) {
        goTerm.synonyms.forEach(syn => {
          if (syn.name && syn.name !== name) {
            synonyms.push(syn.name);
          }
        });
      }
      
      // Extract cross-references if available
      const xrefs = [];
      if (goTerm.xrefs) {
        goTerm.xrefs.forEach(xref => {
          if (xref.db && xref.id) {
            xrefs.push(`${xref.db}:${xref.id}`);
          }
        });
      }
      
      return {
        id: goId,
        goId: cleanId,
        name: name,
        description: `${name}. ${definition}`,
        definition: definition,
        namespace: readableNamespace,
        aspect: namespace,
        isObsolete: isObsolete,
        synonyms: synonyms,
        crossReferences: xrefs.slice(0, 10), // Limit to first 10 xrefs
        displayName: name,
        url: `https://www.ebi.ac.uk/QuickGO/term/${cleanId}`
      };
    }
    
    return null;
  } catch (error) {
    console.error(`Error fetching GO term data for ${goId}:`, error);
    
    // Return fallback data with error indication
    const cleanId = goId.includes(':') ? goId.split(':')[1] : goId;
    const formattedId = cleanId.startsWith('GO:') ? cleanId : `GO:${cleanId.padStart(7, '0')}`;
    
    return {
      id: goId,
      goId: formattedId,
      name: `GO Term ${cleanId}`,
      description: `Gene Ontology term with ID ${formattedId}. Unable to fetch detailed information from QuickGO.`,
      definition: 'Unable to fetch definition from QuickGO API.',
      namespace: 'Unknown',
      error: true,
      displayName: `GO Term ${cleanId}`,
      url: `https://www.ebi.ac.uk/QuickGO/term/${formattedId}`
    };
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
 * Fetch organism information from UniProt Taxonomy API
 * @param {string} taxonId - The NCBI Taxonomy ID (e.g., "ncbitaxon:9606")
 */
export const fetchOrganismData = async (taxonId) => {
  if (!taxonId) return null;
  
  // Extract just the numeric part if it's in the format "ncbitaxon:9606"
  const numericId = taxonId.includes(':') ? taxonId.split(':')[1] : taxonId;
  
  try {
    // UniProt Taxonomy API
    const response = await fetch(`https://rest.uniprot.org/taxonomy/${numericId}.json`);
    
    if (!response.ok) {
      throw new Error(`Failed to fetch taxonomy data: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (data) {
      // Extract taxonomic information
      const scientificName = data.scientificName || 'Unknown organism';
      const commonName = data.commonName || null;
      const rank = data.rank || 'Unknown rank';
      
      // Extract lineage information
      const lineage = [];
      if (data.lineage && Array.isArray(data.lineage)) {
        data.lineage.forEach(ancestor => {
          if (ancestor.scientificName) {
            lineage.push({
              name: ancestor.scientificName,
              rank: ancestor.rank || 'Unknown',
              taxonId: ancestor.taxonId || null
            });
          }
        });
      }
      
      // Extract synonyms/other names
      const synonyms = [];
      if (data.otherNames && Array.isArray(data.otherNames)) {
        data.otherNames.forEach(name => {
          if (name.name && name.name !== scientificName && name.name !== commonName) {
            synonyms.push(name.name);
          }
        });
      }
      
      // Create a comprehensive description
      let description = `${scientificName}`;
      if (commonName && commonName !== scientificName) {
        description += ` (${commonName})`;
      }
      description += ` is a ${rank.toLowerCase()} organism`;
      
      if (lineage.length > 0) {
        // Get some key taxonomic levels for the description
        const domain = lineage.find(l => l.rank === 'superkingdom' || l.rank === 'domain');
        const kingdom = lineage.find(l => l.rank === 'kingdom');
        const phylum = lineage.find(l => l.rank === 'phylum');
        const order = lineage.find(l => l.rank === 'order');
        const family = lineage.find(l => l.rank === 'family');
        
        const taxonomicInfo = [];
        if (domain) taxonomicInfo.push(domain.name);
        if (kingdom && kingdom.name !== domain?.name) taxonomicInfo.push(kingdom.name);
        if (phylum) taxonomicInfo.push(phylum.name);
        if (order) taxonomicInfo.push(order.name);
        if (family) taxonomicInfo.push(family.name);
        
        if (taxonomicInfo.length > 0) {
          description += ` belonging to the taxonomic lineage: ${taxonomicInfo.join(' > ')}.`;
        }
      }
      
      // Extract additional properties
      const mnemonic = data.mnemonic || null; // UniProt organism mnemonic code
      const taxonNode = data.taxonNode || null; // Additional node information
      
      return {
        id: taxonId,
        taxonId: numericId,
        name: commonName || scientificName,
        scientificName: scientificName,
        commonName: commonName,
        displayName: commonName || scientificName,
        description: description,
        rank: rank,
        lineage: lineage,
        synonyms: synonyms.slice(0, 10), // Limit synonyms for display
        mnemonic: mnemonic,
        database: 'UniProt Taxonomy',
        url: `https://www.uniprot.org/taxonomy/${numericId}`,
        // Additional properties for detailed view
        fullLineage: lineage,
        parentTaxonId: data.parent?.taxonId || null,
        parentName: data.parent?.scientificName || null
      };
    }
    
    return null;
  } catch (error) {
    console.error(`Error fetching taxonomy data for ${taxonId}:`, error);
    
    // Return fallback data with error indication
    return {
      id: taxonId,
      taxonId: numericId,
      name: numericId === '9606' ? 'Homo sapiens' : `Organism ${numericId}`,
      scientificName: numericId === '9606' ? 'Homo sapiens' : `Unknown organism`,
      commonName: numericId === '9606' ? 'Human' : null,
      displayName: numericId === '9606' ? 'Human' : `Organism ${numericId}`,
      description: numericId === '9606' 
        ? 'Homo sapiens (Human) - error fetching detailed taxonomy information from UniProt' 
        : `Organism with taxonomy ID ${numericId} - error fetching information from UniProt: ${error.message}`,
      rank: 'Unknown',
      lineage: [],
      synonyms: [],
      database: 'UniProt Taxonomy',
      error: true,
      url: `https://www.uniprot.org/taxonomy/${numericId}`
    };
  }
};

/**
 * Fetch side effect information from BioPortal MedDRA ontology
 * @param {string} sideEffectId - The side effect ID (e.g., "meddra:10063296")
 */
export const fetchSideEffectData = async (sideEffectId) => {
  if (!sideEffectId) return null;
  
  // Extract the numeric ID from formats like "meddra:10063296"
  const numericId = sideEffectId.includes(':') ? sideEffectId.split(':')[1] : sideEffectId;
  
  try {
    // BioPortal API endpoint for MedDRA terms
    // The URL needs to be encoded for the API call
    const medDRAUrl = `http://purl.bioontology.org/ontology/MEDDRA/${numericId}`;
    const encodedUrl = encodeURIComponent(medDRAUrl);
    
    // BioPortal REST API call
    const response = await fetch(`https://data.bioontology.org/ontologies/MEDDRA/classes/${encodedUrl}`, {
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error(`Failed to fetch MedDRA data: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (data) {
      // Extract relevant information from BioPortal response
      const prefLabel = data.prefLabel || `MedDRA Term ${numericId}`;
      const definition = data.definition && data.definition.length > 0 ? data.definition[0] : null;
      const synonyms = data.synonym || [];
      
      // Extract additional properties if available
      const properties = data.properties || {};
      const notation = properties['http://www.w3.org/2004/02/skos/core#notation'] || [];
      const broader = data.parents || [];
      const narrower = data.children || [];
      
      // Get hierarchy information
      const hierarchyInfo = [];
      if (broader && broader.length > 0) {
        hierarchyInfo.push(`Parent terms: ${broader.length}`);
      }
      if (narrower && narrower.length > 0) {
        hierarchyInfo.push(`Child terms: ${narrower.length}`);
      }
      
      // Create a comprehensive description
      let description = definition || 
        `${prefLabel} is a standardized medical terminology for regulatory activities from the Medical Dictionary for Regulatory Activities (MedDRA).`;
      
      if (hierarchyInfo.length > 0) {
        description += ` This term has ${hierarchyInfo.join(' and ')}.`;
      }
      
      return {
        id: sideEffectId,
        name: prefLabel,
        description: description,
        definition: definition,
        synonyms: synonyms.slice(0, 10), // Limit synonyms for display
        notation: notation.length > 0 ? notation[0] : numericId,
        hierarchy: {
          parents: broader.slice(0, 5), // Limit for performance
          children: narrower.slice(0, 5)
        },
        database: 'MedDRA',
        displayName: prefLabel,
        url: `https://bioportal.bioontology.org/ontologies/MEDDRA?p=classes&conceptid=${encodeURIComponent(medDRAUrl)}`
      };
    }
    
    return null;
  } catch (error) {
    console.error(`Error fetching MedDRA data for ${sideEffectId}:`, error);
    
    // Return fallback data with error indication
    return {
      id: sideEffectId,
      name: `MedDRA Term ${numericId}`,
      description: `Side effect or adverse reaction with MedDRA ID ${numericId}. This is a standardized medical terminology from the Medical Dictionary for Regulatory Activities used for regulatory reporting of medical products.`,
      definition: 'Unable to fetch detailed definition from BioPortal.',
      synonyms: [],
      database: 'MedDRA',
      error: true,
      displayName: `MedDRA ${numericId}`,
      url: `https://bioportal.bioontology.org/ontologies/MEDDRA?p=classes&conceptid=${encodeURIComponent(`http://purl.bioontology.org/ontology/MEDDRA/${numericId}`)}`
    };
  }
};
