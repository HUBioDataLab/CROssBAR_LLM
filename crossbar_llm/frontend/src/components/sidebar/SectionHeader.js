import React from 'react';
import {
  Box,
  Typography,
  Chip,
  alpha,
  useTheme,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';

/**
 * Reusable collapsible section header for the right panel.
 */
function SectionHeader({ title, icon, expanded, onToggle, badge }) {
  const theme = useTheme();

  return (
    <Box
      onClick={onToggle}
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        p: 1.5,
        cursor: 'pointer',
        borderRadius: '12px',
        '&:hover': { backgroundColor: alpha(theme.palette.primary.main, 0.05) },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
        {icon}
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>{title}</Typography>
        {badge && <Chip label={badge} size="small" sx={{ height: 20, fontSize: '0.7rem' }} />}
      </Box>
      {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
    </Box>
  );
}

export default SectionHeader;
