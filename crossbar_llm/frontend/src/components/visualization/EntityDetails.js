import React from 'react';
import {
  Box,
  Typography,
  Chip,
  Card,
  CardContent,
  CircularProgress,
  Link,
  Grid,
  alpha,
  useTheme,
} from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';

/**
 * Expanded entity details component.
 */
function EntityDetails({
  entity,
  entityType,
  summary,
}) {
  const theme = useTheme();

  const renderSummaryContent = () => {
    if (summary?.loading) {
      return (
        <Box sx={{ display: 'flex', alignItems: 'center', my: 1 }}>
          <CircularProgress size={16} thickness={5} sx={{ mr: 1 }} />
          <Typography variant="body2" color="text.secondary">
            Loading information from biological databases...
          </Typography>
        </Box>
      );
    }

    if (summary?.text) {
      return (
        <Box>
          <Typography variant="body2" sx={{ mb: 2 }} component="div">
            <div dangerouslySetInnerHTML={{
              __html: summary.text
                .replace(/\(cite:.+?\)/g, '')
                .replace(/([A-Z][A-Z0-9_-]+\d*)/g, '<strong>$1</strong>')
            }} />
          </Typography>

          {summary.data && (
            <Box sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              {summary.data.symbol && entityType !== 'genes' && (
                <Chip
                  label={`Symbol: ${summary.data.symbol}`}
                  size="small"
                  sx={{ fontSize: '0.7rem' }}
                />
              )}
              {summary.data.geneName && (
                <Chip
                  label={`Gene ID: ${summary.data.geneName}`}
                  size="small"
                  sx={{ fontSize: '0.7rem' }}
                />
              )}
              {summary.data.length && (
                <Chip
                  label={`Length: ${summary.data.length} aa`}
                  size="small"
                  sx={{ fontSize: '0.7rem' }}
                />
              )}
              {summary.data.organism && (
                <Chip
                  label={summary.data.organism}
                  size="small"
                  sx={{ fontSize: '0.7rem' }}
                />
              )}
            </Box>
          )}
        </Box>
      );
    }

    return (
      <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
        Click the external link to view detailed information about this entity.
      </Typography>
    );
  };

  const renderEntityTypeDetails = () => {
    switch (entityType) {
      case 'genes':
        return (
          <Box sx={{ mt: 2 }}>
            {summary?.data?.symbol && (
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                <strong>Official Symbol:</strong> {summary.data.symbol}
              </Typography>
            )}
            {summary?.data?.summary && (
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                <strong>Summary:</strong> {summary.data.summary}
              </Typography>
            )}
            {entity.all_names && entity.all_names.length > 0 && (
              <>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                  Alternative names:
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1.5 }}>
                  {entity.all_names.map((name, i) => (
                    <Chip key={i} label={name} size="small" sx={{ height: '20px', fontSize: '0.7rem' }} />
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
        );

      case 'proteins':
        return (
          <Box sx={{ mt: 2 }}>
            {entity.synonyms && entity.synonyms.length > 0 && (
              <>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                  Synonyms:
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1.5 }}>
                  {entity.synonyms.slice(0, 5).map((name, i) => (
                    <Chip key={i} label={name} size="small" sx={{ height: '20px', fontSize: '0.7rem' }} />
                  ))}
                  {entity.synonyms.length > 5 && (
                    <Chip label={`+${entity.synonyms.length - 5} more`} size="small" sx={{ height: '20px', fontSize: '0.7rem' }} />
                  )}
                </Box>
              </>
            )}
            {entity.genes && entity.genes.length > 0 && (
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                <strong>Gene ID:</strong> {entity.genes.join(', ')}
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
        );

      case 'diseases':
        return (
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
                        backgroundColor: alpha(theme.palette.error.main, 0.1),
                        color: 'error.main'
                      }}
                    />
                  ))}
                  {entity.synonyms.length > 5 && (
                    <Chip label={`+${entity.synonyms.length - 5} more`} size="small" sx={{ height: '20px', fontSize: '0.7rem' }} />
                  )}
                </Box>
              </>
            )}
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
        );

      case 'drugs':
      case 'compounds':
        return (
          <Box sx={{ mt: 2 }}>
            {summary?.data?.smiles && (
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                <strong>SMILES:</strong> {summary.data.smiles}
              </Typography>
            )}
            {summary?.data?.summary && (
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                <strong>Summary:</strong> {summary.data.summary}
              </Typography>
            )}
            {summary?.data?.groups && summary.data.groups.length > 0 && (
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                <strong>Groups:</strong> {summary.data.groups.join(', ')}
              </Typography>
            )}
            {summary?.data?.chemicalFormula && (
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                <strong>Chemical Formula:</strong> {summary.data.chemicalFormula}
              </Typography>
            )}
            {entity.synonyms && entity.synonyms.length > 0 && (
              <>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                  Alternative names:
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {entity.synonyms.slice(0, 5).map((name, i) => (
                    <Chip key={i} label={name} size="small" sx={{ height: '20px', fontSize: '0.7rem' }} />
                  ))}
                  {entity.synonyms.length > 5 && (
                    <Chip label={`+${entity.synonyms.length - 5} more`} size="small" sx={{ height: '20px', fontSize: '0.7rem' }} />
                  )}
                </Box>
              </>
            )}
          </Box>
        );

      default:
        return null;
    }
  };

  return (
    <Box sx={{ px: 3, py: 2, backgroundColor: alpha(theme.palette.background.default, 0.3) }}>
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card variant="outlined" sx={{ borderRadius: '12px' }}>
            <CardContent>
              <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <InfoOutlinedIcon fontSize="small" sx={{ mr: 1, color: 'info.main' }} />
                Entity Information
              </Typography>

              <Box sx={{ mb: 2 }}>
                {renderSummaryContent()}
              </Box>

              {renderEntityTypeDetails()}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}

export default EntityDetails;
