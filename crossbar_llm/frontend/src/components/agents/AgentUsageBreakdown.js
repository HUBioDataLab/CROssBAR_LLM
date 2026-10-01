import React from 'react';
import { Box, Typography, alpha, useTheme } from '@mui/material';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import AgentAvatar from './AgentAvatar';
import { AGENT_ORDER, agentMeta, agentName } from './agentMeta';
import { formatSeconds } from './agentStatus';

const tokens = (usage) => usage?.aggregated_usage?.totals?.total_tokens || 0;

/**
 * Where the request's tokens went: each agent's share, plus the orchestrator's
 * own planning and merging. The shares are slices of the run total above them,
 * not additions to it.
 */
function AgentUsageBreakdown({ orchestration, catalog }) {
  const theme = useTheme();
  if (!orchestration) return null;

  const rows = AGENT_ORDER.filter((id) => orchestration.agents?.[id]).map((id) => ({
    key: id,
    label: agentName(id, catalog),
    icon: <AgentAvatar agentId={id} size={20} />,
    color: agentMeta(id).color,
    tokens: tokens(orchestration.agents[id].usage),
    duration: orchestration.agents[id].duration_seconds,
  }));
  rows.push({
    key: 'orchestrator',
    label: 'Orchestrator (routing & merging)',
    icon: <AccountTreeIcon sx={{ fontSize: 20, color: theme.palette.primary.main }} />,
    color: theme.palette.primary.main,
    tokens: tokens(orchestration.usage),
    duration: null,
  });

  const max = Math.max(1, ...rows.map((row) => row.tokens));

  return (
    <Box sx={{ px: 2, pb: 2 }}>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, display: 'block', mb: 1 }}>
        Tokens by agent
      </Typography>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {rows.map((row) => (
          <Box key={row.key} sx={{ display: 'grid', gridTemplateColumns: '20px 1fr auto', alignItems: 'center', columnGap: 1 }}>
            {row.icon}
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="caption" noWrap sx={{ display: 'block', fontWeight: 600 }}>{row.label}</Typography>
              <Box sx={{ height: 4, borderRadius: 2, backgroundColor: alpha(theme.palette.text.primary, 0.08), overflow: 'hidden' }}>
                <Box sx={{ width: `${(row.tokens / max) * 100}%`, height: '100%', backgroundColor: row.color, borderRadius: 2 }} />
              </Box>
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}>
              {row.tokens.toLocaleString()}
              {row.duration ? ` · ${formatSeconds(row.duration)}` : ''}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

export default AgentUsageBreakdown;
