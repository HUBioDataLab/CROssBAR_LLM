import React from 'react';
import {
  Box,
  Typography,
  Paper,
  alpha,
  useTheme,
} from '@mui/material';

/**
 * Reusable error display component.
 */
function ErrorDisplay({ error, sx = {} }) {
  const theme = useTheme();

  if (!error) return null;

  return (
    <Box sx={{ px: 3, pb: 1, ...sx }}>
      <Paper
        elevation={0}
        sx={{
          p: 2,
          borderRadius: '12px',
          backgroundColor: alpha(theme.palette.error.main, 0.1),
          border: `1px solid ${alpha(theme.palette.error.main, 0.3)}`,
        }}
      >
        <Typography variant="body2" color="error">
          {error}
        </Typography>
      </Paper>
    </Box>
  );
}

export default ErrorDisplay;
