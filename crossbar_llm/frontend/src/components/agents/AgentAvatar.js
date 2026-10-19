import React from 'react';
import { Box, alpha, useTheme } from '@mui/material';
import { agentMeta } from './agentMeta';

/** The agent's icon on its identity colour: the one mark used for it everywhere. */
function AgentAvatar({ agentId, size = 28, muted = false }) {
  const theme = useTheme();
  const { Icon, color } = agentMeta(agentId);
  return (
    <Box
      aria-hidden
      sx={{
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: `${Math.round(size * 0.32)}px`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: muted ? alpha(theme.palette.text.primary, 0.08) : color,
        color: muted ? theme.palette.text.secondary : '#fff',
        transition: 'background-color 0.2s ease, color 0.2s ease',
      }}
    >
      <Icon sx={{ fontSize: Math.round(size * 0.58) }} />
    </Box>
  );
}

export default AgentAvatar;
