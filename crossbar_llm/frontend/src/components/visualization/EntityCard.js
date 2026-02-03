import React from 'react';
import {
  Box,
  Typography,
  Chip,
  IconButton,
  Tooltip,
  ListItemButton,
  ListItemText,
  Link,
  alpha,
  useTheme,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { generateExternalLink, formatEntityName } from '../../utils/helpers';
import { getDbPrefixColors } from './entityUtils';

/**
 * Individual entity card component.
 */
function EntityCard({
  entity,
  entityType,
  isExpanded,
  onToggleExpand,
}) {
  const theme = useTheme();

  const getDisplayName = () => {
    if (entityType === 'proteins') {
      return entity.name || entity.displayName || formatEntityName(entity.id, null);
    }
    return (
      entity.displayName ||
      entity.name ||
      (entity.genes && entity.genes.length > 0 ? entity.genes[0] : null) ||
      formatEntityName(entity.id, null)
    );
  };

  const dbPrefix = entity.id ? entity.id.split(':')[0] : '';
  const prefixColors = getDbPrefixColors(dbPrefix, theme);

  return (
    <ListItemButton
      onClick={() => onToggleExpand(entity.id)}
      sx={{
        py: 2,
        px: 3,
        pl: 4,
        '&:hover': {
          backgroundColor: theme.palette.mode === 'dark'
            ? alpha(theme.palette.primary.main, 0.1)
            : alpha(theme.palette.primary.main, 0.05),
        }
      }}
    >
      <ListItemText
        disableTypography
        primary={
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Typography variant="body2" sx={{ fontWeight: 500 }}>
              {getDisplayName()}
            </Typography>
            {entity.id && (
              <Chip
                label={dbPrefix}
                size="small"
                sx={{
                  ml: 1,
                  height: '18px',
                  fontSize: '0.65rem',
                  backgroundColor: alpha(prefixColors.bg, prefixColors.bgAlpha),
                  color: prefixColors.bg,
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
                  backgroundColor: alpha(theme.palette.success.light, 0.1),
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
                  backgroundColor: alpha(theme.palette.background.default, 0.8)
                }}
              />
            )}
          </Box>
        }
      />
      <Box sx={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
        {entity.id && (
          <Tooltip title="View in External Database">
            <IconButton
              size="small"
              component={Link}
              href={generateExternalLink(entity.id)}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              sx={{
                mr: 0.5,
                color: 'primary.main',
                border: `1px solid ${alpha(theme.palette.primary.main, 0.3)}`,
                borderRadius: '6px',
                p: 0.5,
                '&:hover': {
                  backgroundColor: alpha(theme.palette.primary.main, 0.08),
                  borderColor: 'primary.main',
                }
              }}
            >
              <OpenInNewIcon sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        )}
        <IconButton
          size="small"
          sx={{ 
            transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)', 
            transition: 'transform 0.3s',
            p: 0.5,
          }}
        >
          <ExpandMoreIcon sx={{ fontSize: 18 }} />
        </IconButton>
      </Box>
    </ListItemButton>
  );
}

export default EntityCard;
