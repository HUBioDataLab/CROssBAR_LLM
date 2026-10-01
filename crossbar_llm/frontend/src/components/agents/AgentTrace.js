import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Alert, Box, Button, Chip, Collapse, Paper, Typography, alpha, useTheme } from '@mui/material';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import AgentAvatar from './AgentAvatar';
import { AGENT_ORDER, agentMeta, agentName } from './agentMeta';
import { formatSeconds, statusColor, statusMeta } from './agentStatus';
import { markdownSx } from '../../utils/markdownStyles';

const citationLabel = (citation) => citation.title || citation.pmid || citation.doc_id || 'Publication';

function Citations({ agentId, citations }) {
  if (!citations?.length) return null;
  return (
    <Box sx={{ mt: 1.5 }}>
      <Typography variant="caption" sx={{ fontWeight: 700, color: 'text.secondary', textTransform: 'uppercase', letterSpacing: 0.4 }}>
        Sources
      </Typography>
      <Box component="ol" sx={{ m: 0, mt: 0.5, pl: 2.5 }}>
        {citations.map((citation, index) => (
          <Typography component="li" variant="caption" key={`${agentId}-${index}`} sx={{ display: 'list-item', lineHeight: 1.6 }}>
            {citation.url ? (
              <a href={citation.url} target="_blank" rel="noreferrer">{citationLabel(citation)}</a>
            ) : (
              citationLabel(citation)
            )}
            {citation.pmid && citation.title ? ` · PMID ${citation.pmid}` : ''}
          </Typography>
        ))}
      </Box>
    </Box>
  );
}

function AgentReport({ agentId, result, reason, catalog }) {
  const theme = useTheme();
  const status = statusMeta(result.status);
  return (
    <Box
      id={`agent-report-${agentId}`}
      sx={{
        p: 2,
        borderRadius: '12px',
        border: `1px solid ${theme.palette.divider}`,
        borderLeft: `3px solid ${agentMeta(agentId).color}`,
        backgroundColor: alpha(theme.palette.background.paper, 0.5),
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, mb: result.answer || reason ? 1 : 0 }}>
        <AgentAvatar agentId={agentId} size={24} />
        <Typography variant="subtitle2" sx={{ fontWeight: 700, flex: 1 }}>{agentName(agentId, catalog)}</Typography>
        {result.duration_seconds ? (
          <Typography variant="caption" color="text.secondary">{formatSeconds(result.duration_seconds)}</Typography>
        ) : null}
        <Typography variant="caption" sx={{ fontWeight: 600, color: statusColor(theme, result.status) }}>{status.label}</Typography>
      </Box>
      {reason && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, fontStyle: 'italic' }}>
          Asked because: {reason}
        </Typography>
      )}
      {result.answer && (
        <Box sx={{ ...markdownSx(theme), fontSize: '0.9rem' }}>
          <ReactMarkdown>{result.answer}</ReactMarkdown>
        </Box>
      )}
      {result.warnings?.length > 0 && (
        <Alert severity={result.status === 'completed' ? 'info' : 'warning'} sx={{ mt: 1, py: 0, borderRadius: '8px' }}>
          {result.warnings.join(' ')}
        </Alert>
      )}
      <Citations agentId={agentId} citations={result.citations} />
    </Box>
  );
}

function Contradictions({ contradictions, catalog }) {
  const theme = useTheme();
  if (!contradictions?.length) return null;
  return (
    <Box
      sx={{
        mt: 1.5,
        p: 1.5,
        borderRadius: '12px',
        border: `1px solid ${alpha(theme.palette.warning.main, 0.35)}`,
        backgroundColor: alpha(theme.palette.warning.main, theme.palette.mode === 'dark' ? 0.1 : 0.05),
      }}
    >
      <Typography variant="caption" sx={{ display: 'flex', alignItems: 'center', gap: 0.75, fontWeight: 700, mb: 1 }}>
        <CompareArrowsIcon sx={{ fontSize: 16, color: theme.palette.warning.main }} />
        {contradictions.length === 1 ? '1 conflict between agents, resolved' : `${contradictions.length} conflicts between agents, resolved`}
      </Typography>
      {contradictions.map((item, index) => (
        <Box key={index} sx={{ mt: index ? 1.25 : 0 }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {item.topic}
            {item.agents?.length > 0 && (
              <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                {item.agents.map((id) => agentName(id, catalog)).join(' vs ')}
              </Typography>
            )}
          </Typography>
          <Typography variant="body2" color="text.secondary">{item.resolution}</Typography>
        </Box>
      ))}
    </Box>
  );
}

/**
 * How an answer was produced: which agents the orchestrator asked, how each
 * did, the conflicts it resolved between them, and every agent's own report.
 *
 * @param {{ orchestration: Object|null, catalog: Array<Object>, question: string }} props
 */
function AgentTrace({ orchestration, catalog, question }) {
  const theme = useTheme();
  const [expanded, setExpanded] = useState(false);
  if (!orchestration?.routing) return null;

  const { routing, agents = {}, contradictions = [], warnings = [], synthesized } = orchestration;
  const asked = AGENT_ORDER.filter((id) => routing.selected?.includes(id));
  const reported = asked.filter((id) => agents[id]);
  const standalone = routing.standalone_question?.trim();
  const rewrite = standalone && standalone !== question?.trim() ? standalone : null;

  const openReport = (id) => {
    setExpanded(true);
    setTimeout(() => document.getElementById(`agent-report-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 250);
  };

  return (
    <Box sx={{ mt: 1.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 0.75 }}>
        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, mr: 0.25 }}>
          {synthesized ? 'Merged from' : asked.length === 1 ? 'Answered by' : 'Agents asked'}
        </Typography>
        {asked.map((id) => {
          const result = agents[id];
          const status = statusMeta(result?.status || 'pending');
          const color = agentMeta(id).color;
          return (
            <Chip
              key={id}
              size="small"
              onClick={result ? () => openReport(id) : undefined}
              avatar={<AgentAvatar agentId={id} size={18} />}
              label={
                <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
                  {agentName(id, catalog)}
                  {status.Icon && <status.Icon sx={{ fontSize: 13, color: statusColor(theme, result?.status) }} />}
                </Box>
              }
              aria-label={`${agentName(id, catalog)}: ${status.label}`}
              sx={{
                height: 24,
                fontSize: '0.72rem',
                fontWeight: 600,
                border: `1px solid ${alpha(color, 0.4)}`,
                backgroundColor: alpha(color, theme.palette.mode === 'dark' ? 0.14 : 0.07),
                '& .MuiChip-avatar': { width: 18, height: 18, ml: '3px' },
              }}
            />
          );
        })}
        {reported.length > 0 && (
          <Button
            size="small"
            onClick={() => setExpanded((open) => !open)}
            endIcon={expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            aria-expanded={expanded}
            sx={{ textTransform: 'none', fontSize: '0.72rem', ml: 'auto', py: 0 }}
          >
            {expanded ? 'Hide agent reports' : `Agent reports (${reported.length})`}
          </Button>
        )}
      </Box>

      <Contradictions contradictions={contradictions} catalog={catalog} />

      {warnings.length > 0 && (
        <Alert severity="warning" sx={{ mt: 1.5, borderRadius: '10px' }}>{warnings.join(' ')}</Alert>
      )}

      <Collapse in={expanded} unmountOnExit>
        <Paper elevation={0} sx={{ mt: 1.5, display: 'flex', flexDirection: 'column', gap: 1.25, backgroundColor: 'transparent' }}>
          {(routing.rationale || rewrite) && (
            <Box sx={{ px: 0.5 }}>
              {routing.rationale && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                  <strong>Routing:</strong> {routing.rationale}
                </Typography>
              )}
              {rewrite && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                  <strong>Question sent to literature agents:</strong> {rewrite}
                </Typography>
              )}
            </Box>
          )}
          {reported.map((id) => (
            <AgentReport key={id} agentId={id} result={agents[id]} reason={routing.reasons?.[id]} catalog={catalog} />
          ))}
          {Object.keys(routing.skipped || {}).length > 0 && (
            <Typography variant="caption" color="text.secondary" sx={{ px: 0.5 }}>
              <strong>Not asked:</strong>{' '}
              {AGENT_ORDER.filter((id) => routing.skipped[id])
                .map((id) => `${agentName(id, catalog)} (${routing.skipped[id]})`)
                .join(' · ')}
            </Typography>
          )}
        </Paper>
      </Collapse>
    </Box>
  );
}

export default AgentTrace;
