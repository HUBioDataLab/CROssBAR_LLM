import React, { useEffect, useState } from 'react';
import { Box, CircularProgress, Typography, alpha, useTheme } from '@mui/material';
import CheckIcon from '@mui/icons-material/Check';
import AgentAvatar from './AgentAvatar';
import { AGENT_ORDER, agentMeta, agentName } from './agentMeta';
import { formatSeconds, statusColor, statusMeta } from './agentStatus';
import { progressHeadline } from '../../utils/orchestrationProgress';

const STAGES = [
  { key: 'plan', label: 'Plan', phases: ['planning'] },
  { key: 'agents', label: 'Agents', phases: ['running', 'review'] },
  { key: 'merge', label: 'Merge', phases: ['synthesizing'] },
];

const stageState = (stageIndex, phase) => {
  const current = STAGES.findIndex((stage) => stage.phases.includes(phase));
  if (stageIndex < current) return 'done';
  return stageIndex === current ? 'active' : 'upcoming';
};

/** The current time, refreshed every second so elapsed timers tick. */
function useNow() {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

function StageRail({ phase }) {
  const theme = useTheme();
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }} aria-hidden>
      {STAGES.map((stage, index) => {
        const state = stageState(index, phase);
        const color = state === 'upcoming' ? theme.palette.text.disabled : theme.palette.primary.main;
        return (
          <React.Fragment key={stage.key}>
            {index > 0 && (
              <Box sx={{ flex: 1, height: 2, borderRadius: 1, backgroundColor: state === 'upcoming' ? theme.palette.divider : alpha(color, 0.5) }} />
            )}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              <Box
                sx={{
                  width: 18,
                  height: 18,
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: `2px solid ${color}`,
                  backgroundColor: state === 'done' ? color : 'transparent',
                }}
              >
                {state === 'done' && <CheckIcon sx={{ fontSize: 12, color: theme.palette.background.paper }} />}
                {state === 'active' && <Box sx={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: color }} />}
              </Box>
              <Typography variant="caption" sx={{ fontWeight: state === 'active' ? 700 : 500, color: state === 'upcoming' ? 'text.disabled' : 'text.primary' }}>
                {stage.label}
              </Typography>
            </Box>
          </React.Fragment>
        );
      })}
    </Box>
  );
}

const detailLine = (agentId, agent, phase) => {
  if (agent.status === 'running') {
    const { working } = agentMeta(agentId);
    return agent.steps.length ? `${working.replace(/…$/, '')} · ${agent.steps[agent.steps.length - 1].label}` : working;
  }
  if (agent.status === 'queued' && phase === 'review') return 'Runs after you approve the Cypher query';
  if (agent.status === 'awaiting_review') return 'Your review is needed before it runs the query';
  if (agent.status === 'failed') return agent.warnings[0] || 'This agent could not answer.';
  if (agent.status === 'skipped') return agent.reason || 'Not asked for this question.';
  if (agent.status === 'completed') return agent.steps.length ? agent.steps[agent.steps.length - 1].label : 'Answer ready';
  return agent.reason || '';
};

function AgentRow({ agentId, agent, phase, catalog, now }) {
  const theme = useTheme();
  const status = statusMeta(agent.status);
  const color = statusColor(theme, agent.status);
  const isRunning = agent.status === 'running';
  const elapsed = isRunning && agent.startedAt ? (now - agent.startedAt) / 1000 : agent.durationSeconds;

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        py: 1,
        px: 1.25,
        borderRadius: '10px',
        backgroundColor: isRunning ? alpha(agentMeta(agentId).color, theme.palette.mode === 'dark' ? 0.12 : 0.05) : 'transparent',
        opacity: agent.status === 'skipped' ? 0.6 : 1,
        transition: 'background-color 0.3s ease, opacity 0.3s ease',
      }}
    >
      <AgentAvatar agentId={agentId} size={28} muted={agent.status === 'skipped'} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>{agentName(agentId, catalog)}</Typography>
        <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
          {detailLine(agentId, agent, phase)}
        </Typography>
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, color, flexShrink: 0 }}>
        {elapsed ? (
          <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums', color: 'text.secondary' }}>
            {formatSeconds(elapsed)}
          </Typography>
        ) : null}
        {isRunning ? (
          <CircularProgress size={16} thickness={5} sx={{ color: agentMeta(agentId).color }} />
        ) : (
          status.Icon && <status.Icon sx={{ fontSize: 18 }} />
        )}
        <Typography variant="caption" sx={{ fontWeight: 600, minWidth: 64, textAlign: 'right' }}>
          {status.label}
        </Typography>
      </Box>
    </Box>
  );
}

/**
 * The orchestrator at work: which stage it is in, and what each agent is doing.
 *
 * @param {{ progress: import('../../utils/orchestrationProgress').OrchestrationProgress, catalog: Array<Object> }} props
 */
function OrchestrationProgress({ progress, catalog }) {
  const theme = useTheme();
  const now = useNow();
  const agentIds = AGENT_ORDER.filter((id) => progress?.agents?.[id]);
  const elapsed = progress ? (now - progress.startedAt) / 1000 : 0;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
        <CircularProgress size={22} thickness={4} sx={{ color: theme.palette.primary.main }} />
        <Typography variant="body1" sx={{ fontWeight: 600, flex: 1 }} aria-live="polite">
          {progressHeadline(progress)}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
          {formatSeconds(elapsed)}
        </Typography>
      </Box>

      <StageRail phase={progress?.phase || 'planning'} />

      {progress?.routing?.rationale && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, fontStyle: 'italic' }}>
          {progress.routing.rationale}
        </Typography>
      )}

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25 }}>
        {agentIds.map((id) => (
          <AgentRow key={id} agentId={id} agent={progress.agents[id]} phase={progress.phase} catalog={catalog} now={now} />
        ))}
      </Box>
    </Box>
  );
}

export default OrchestrationProgress;
