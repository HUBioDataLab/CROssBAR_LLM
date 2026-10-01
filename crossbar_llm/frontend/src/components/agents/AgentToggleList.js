import React from 'react';
import { Box, Switch, Tooltip, Typography, alpha, useTheme } from '@mui/material';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import { AGENT_ORDER, agentMeta, enabledCount, effectiveAgents } from './agentMeta';
import AgentAvatar from './AgentAvatar';

/**
 * Why a switch cannot be flipped right now, or null when it can.
 * Order matters: an unavailable agent says so even while a run is in progress.
 */
const lockReason = ({ info, isOn, isLocked, isLastOn }) => {
  if (!info.available) return info.unavailable_reason || 'Not available on this server.';
  if (isLocked) return 'Vector search runs on the Knowledge Graph agent, so it stays on.';
  if (isOn && isLastOn) return 'At least one agent must stay enabled.';
  return null;
};

/**
 * One switch per agent. Switching an agent off is a hard limit — the
 * orchestrator never routes to it; switching it on only makes it eligible.
 *
 * @param {{
 *   catalog: Array<{ id: string, name: string, summary: string, available: boolean, unavailable_reason?: string }>,
 *   enabled: Record<string, boolean>,
 *   onChange: (id: string, value: boolean) => void,
 *   disabled?: boolean,
 *   lockedOn?: string[],
 * }} props
 */
function AgentToggleList({ catalog, enabled, onChange, disabled = false, lockedOn = [] }) {
  const theme = useTheme();
  const effective = effectiveAgents(enabled, catalog);
  const onCount = enabledCount(effective);
  const agents = AGENT_ORDER.map((id) => catalog.find((agent) => agent.id === id)).filter(Boolean);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
        The orchestrator picks which enabled agents to ask for each question, runs them in parallel,
        and merges their answers. Switched-off agents are never asked.
      </Typography>

      {agents.map((info) => {
        const meta = agentMeta(info.id);
        const isLocked = lockedOn.includes(info.id);
        const isOn = isLocked || effective[info.id];
        const reason = lockReason({ info, isOn, isLocked, isLastOn: onCount <= 1 });
        const canToggle = !disabled && !reason;
        const toggle = () => canToggle && onChange(info.id, !isOn);

        return (
          <Tooltip key={info.id} title={reason || ''} placement="left" disableInteractive>
            <Box
              role="group"
              aria-label={`${info.name} agent`}
              onClick={toggle}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1.5,
                p: 1.25,
                borderRadius: '12px',
                border: `1px solid ${isOn ? alpha(meta.color, 0.45) : theme.palette.divider}`,
                backgroundColor: isOn ? alpha(meta.color, theme.palette.mode === 'dark' ? 0.12 : 0.06) : 'transparent',
                cursor: canToggle ? 'pointer' : 'default',
                opacity: info.available ? 1 : 0.55,
                transition: 'background-color 0.2s ease, border-color 0.2s ease',
                '&:hover': canToggle ? { borderColor: alpha(meta.color, 0.7) } : {},
              }}
            >
              <AgentAvatar agentId={info.id} size={34} muted={!isOn} />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>{info.name}</Typography>
                  {isLocked && <LockOutlinedIcon sx={{ fontSize: 14, color: 'text.secondary' }} />}
                </Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.4 }}>
                  {info.available ? info.summary : info.unavailable_reason || 'Not available on this server.'}
                </Typography>
              </Box>
              <Switch
                checked={Boolean(isOn)}
                disabled={!canToggle}
                onClick={(event) => event.stopPropagation()}
                onChange={(event) => onChange(info.id, event.target.checked)}
                size="small"
                sx={{
                  '& .MuiSwitch-switchBase.Mui-checked': { color: meta.color },
                  '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: meta.color },
                }}
                inputProps={{ 'aria-label': `Enable the ${info.name} agent` }}
              />
            </Box>
          </Tooltip>
        );
      })}
    </Box>
  );
}

export default AgentToggleList;
