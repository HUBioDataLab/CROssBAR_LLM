import React from 'react';
import { Box, Link, Switch, TextField, Tooltip, Typography, alpha, useTheme } from '@mui/material';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import { AGENT_ORDER, agentMeta, enabledCount, effectiveAgents } from './agentMeta';
import AgentAvatar from './AgentAvatar';

/**
 * Why a switch cannot be flipped right now, or null when it can.
 * Order matters: an unavailable agent says so even while a run is in progress.
 */
const KEY_SIGNUP_URLS = { paperclip: 'https://paperclip.gxl.ai' };

const lockReason = ({ info, isOn, isLockedOn, isLockedOff, isLastOn }) => {
  if (!info.available) return info.unavailable_reason || 'Not available on this server.';
  if (isLockedOn) return 'Vector search runs on the Knowledge Graph agent, so it stays on.';
  if (isLockedOff) return 'Vector search supports only the Knowledge Graph agent.';
  if (isOn && isLastOn) return 'At least one agent must stay enabled.';
  return null;
};

/**
 * One switch per agent. Every enabled and available agent runs.
 *
 * @param {{
 *   catalog: Array<{ id: string, name: string, summary: string, available: boolean, unavailable_reason?: string }>,
 *   enabled: Record<string, boolean>,
 *   onChange: (id: string, value: boolean) => void,
 *   disabled?: boolean,
 *   lockedOn?: string[],
 *   lockedOff?: string[],
 *   userKeys?: Record<string, string>,
 *   onUserKeyChange?: (id: string, value: string) => void,
 * }} props
 *
 * An agent with `requires_user_key` runs only on the user's own API key, so it
 * gets a key field; entering a key is what makes it available.
 */
function AgentToggleList({
  catalog,
  enabled,
  onChange,
  disabled = false,
  lockedOn = [],
  lockedOff = [],
  userKeys = {},
  onUserKeyChange,
}) {
  const theme = useTheme();
  const effective = {
    ...effectiveAgents(enabled, catalog),
    ...Object.fromEntries(lockedOff.map((id) => [id, false])),
    ...Object.fromEntries(lockedOn.map((id) => [id, true])),
  };
  const onCount = enabledCount(effective);
  const agents = AGENT_ORDER.map((id) => catalog.find((agent) => agent.id === id)).filter(Boolean);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
        Every selected agent runs. Multiple agents run in parallel, and their answers are merged.
      </Typography>

      {agents.map((info) => {
        const meta = agentMeta(info.id);
        const isLockedOn = lockedOn.includes(info.id);
        const isLockedOff = lockedOff.includes(info.id);
        const isOn = Boolean(effective[info.id]);
        const reason = lockReason({ info, isOn, isLockedOn, isLockedOff, isLastOn: onCount <= 1 });
        const canToggle = !disabled && !reason;
        const toggle = () => canToggle && onChange(info.id, !isOn);

        const keyField = info.requires_user_key && onUserKeyChange && (
          <Box sx={{ mt: -0.5, mb: 0.5, px: 1.25 }}>
            <TextField
              type="password"
              size="small"
              fullWidth
              autoComplete="off"
              label={`${info.name} API key`}
              value={userKeys[info.id] || ''}
              onChange={(event) => onUserKeyChange(info.id, event.target.value)}
              disabled={disabled}
              inputProps={{ spellCheck: false }}
              helperText={(
                <>
                  Stored only in this browser and sent with your questions.
                  {KEY_SIGNUP_URLS[info.id] && (
                    <>
                      {' '}
                      <Link href={KEY_SIGNUP_URLS[info.id]} target="_blank" rel="noreferrer">Get a key</Link>
                    </>
                  )}
                </>
              )}
            />
          </Box>
        );

        return (
          <React.Fragment key={info.id}>
            <Tooltip title={reason || ''} placement="left" disableInteractive>
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
                    {(isLockedOn || isLockedOff) && <LockOutlinedIcon sx={{ fontSize: 14, color: 'text.secondary' }} />}
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.4 }}>
                    {info.available ? info.summary : info.unavailable_reason || 'Not available on this server.'}
                  </Typography>
                </Box>
                <Switch
                  checked={Boolean(isOn)}
                  disabled={!canToggle}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(event) => canToggle && onChange(info.id, event.target.checked)}
                  size="small"
                  sx={{
                    '& .MuiSwitch-switchBase.Mui-checked': { color: meta.color },
                    '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: meta.color },
                  }}
                  inputProps={{ 'aria-label': `Enable the ${info.name} agent` }}
                />
              </Box>
            </Tooltip>
            {keyField}
          </React.Fragment>
        );
      })}
    </Box>
  );
}

export default AgentToggleList;
