import React from 'react';
import {
  Box,
  Typography,
  Chip,
  Divider,
  Collapse,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  alpha,
  useTheme,
} from '@mui/material';
import EntityCard from './EntityCard';
import EntityDetails from './EntityDetails';
import { getEntityIcon, getEntityTypeLabel } from './entityUtils';

/**
 * List of entities grouped by type.
 */
function EntityList({
  entityType,
  entities,
  expandedEntities,
  onToggleEntityExpand,
  entitySummaries,
}) {
  const theme = useTheme();

  if (entities.length === 0) return null;

  return (
    <React.Fragment>
      <ListItemButton
        sx={{
          py: 1.5,
          px: 3,
          backgroundColor: theme.palette.mode === 'dark'
            ? alpha(theme.palette.background.default, 0.4)
            : alpha(theme.palette.background.default, 0.4),
        }}
      >
        <ListItemIcon sx={{ minWidth: 40 }}>
          {getEntityIcon(entityType)}
        </ListItemIcon>
        <ListItemText
          primary={
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              {getEntityTypeLabel(entityType)}
            </Typography>
          }
        />
        <Chip
          label={entities.length}
          size="small"
          sx={{
            height: '20px',
            minWidth: '20px',
            fontSize: '0.7rem',
            backgroundColor: alpha(theme.palette.background.paper, 0.7),
          }}
        />
      </ListItemButton>

      <Divider />

      {entities.map((entity, index) => (
        <React.Fragment key={entity.id || index}>
          <EntityCard
            entity={entity}
            entityType={entityType}
            isExpanded={expandedEntities[entity.id]}
            onToggleExpand={onToggleEntityExpand}
          />
          <Collapse in={expandedEntities[entity.id]}>
            <EntityDetails
              entity={entity}
              entityType={entityType}
              summary={entitySummaries[entity.id]}
            />
          </Collapse>
        </React.Fragment>
      ))}
    </React.Fragment>
  );
}

export default EntityList;
