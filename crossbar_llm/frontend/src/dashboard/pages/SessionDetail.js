import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  IconButton,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import {
  ArrowBack as BackIcon,
  ContentCopy as CopyIcon,
  CheckCircle as CompletedIcon,
  Error as ErrorIcon,
  ExpandMore as ExpandMoreIcon,
  OpenInNew as OpenIcon,
} from '@mui/icons-material';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { getSessionDetail } from '../services/api';
import { format, parseISO } from 'date-fns';
import { tz } from '@date-fns/tz';

const DASHBOARD_TZ = tz('Europe/Istanbul');

function formatDuration(ms) {
  if (ms == null || ms === 0) return '-';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <Tooltip title={copied ? 'Copied!' : 'Copy'}>
      <IconButton
        size="small"
        onClick={() => {
          navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        <CopyIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
}

function StatusChip({ status }) {
  const map = {
    completed: { color: 'success', icon: <CompletedIcon sx={{ fontSize: 14 }} /> },
    failed: { color: 'error', icon: <ErrorIcon sx={{ fontSize: 14 }} /> },
    in_progress: { color: 'warning', icon: null },
    pending: { color: 'default', icon: null },
  };
  const cfg = map[status] || map.pending;
  return (
    <Chip label={status || 'unknown'} size="small" color={cfg.color} icon={cfg.icon} sx={{ fontWeight: 600 }} />
  );
}

function CodeBlock({ code, language = 'cypher' }) {
  const theme = useTheme();
  const style = theme.palette.mode === 'dark' ? oneDark : oneLight;
  if (!code) return <Typography variant="body2" color="text.secondary">-</Typography>;
  return (
    <Box sx={{ position: 'relative' }}>
      <Box sx={{ position: 'absolute', top: 4, right: 4, zIndex: 1 }}>
        <CopyButton text={code} />
      </Box>
      <SyntaxHighlighter
        language={language}
        style={style}
        customStyle={{
          margin: 0,
          borderRadius: '8px',
          fontSize: '0.8125rem',
          padding: '16px',
        }}
        wrapLines
        wrapLongLines
      >
        {code}
      </SyntaxHighlighter>
    </Box>
  );
}

function CollapsibleResponse({ text }) {
  const [expanded, setExpanded] = useState(false);
  if (!text) return null;
  const isLong = text.length > 300;
  return (
    <Box>
      <Box
        sx={{
          p: 1.5,
          borderRadius: '8px',
          bgcolor: 'background.subtle',
          fontSize: '0.8125rem',
          lineHeight: 1.6,
          whiteSpace: 'pre-wrap',
          maxHeight: expanded ? 'none' : '6em',
          overflow: 'hidden',
          position: 'relative',
          '&::after': !expanded && isLong
            ? {
                content: '""',
                position: 'absolute',
                bottom: 0,
                left: 0,
                right: 0,
                height: '2em',
                background: (t) =>
                  `linear-gradient(transparent, ${t.palette.background.subtle})`,
              }
            : undefined,
        }}
      >
        {text}
      </Box>
      {isLong && (
        <Button
          size="small"
          onClick={() => setExpanded(!expanded)}
          endIcon={<ExpandMoreIcon sx={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />}
          sx={{ mt: 0.5 }}
        >
          {expanded ? 'Show less' : 'Show more'}
        </Button>
      )}
    </Box>
  );
}

function TurnCard({ entry, index, navigate, isFollowUp }) {
  const followUps = entry.follow_up_questions || [];
  return (
    <Card>
      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5, flexWrap: 'wrap' }}>
          <Typography variant="caption" color="text.secondary" sx={{ mb: 0 }}>
            #{index + 1}
          </Typography>
          {entry.timestamp && (
            <Typography variant="caption" color="text.secondary" sx={{ mb: 0 }}>
              {format(parseISO(entry.timestamp), 'MMM d, HH:mm:ss', { in: DASHBOARD_TZ })}
            </Typography>
          )}
          <Box sx={{ flex: 1 }} />
          {isFollowUp && (
            <Chip label="Follow-up" size="small" color="info" variant="filled" sx={{ fontSize: '0.65rem', height: 20, fontWeight: 600 }} />
          )}
          {entry.used_internal_knowledge && (
            <Chip label="Internal Knowledge" size="small" color="warning" variant="filled" sx={{ fontSize: '0.65rem', height: 20, fontWeight: 600 }} />
          )}
          <StatusChip status={entry.status} />
          {entry.model_name && (
            <Chip label={entry.model_name} size="small" variant="outlined" sx={{ fontSize: '0.7rem' }} />
          )}
          {entry.provider && (
            <Chip label={entry.provider} size="small" variant="outlined" sx={{ fontSize: '0.7rem' }} />
          )}
          <Tooltip title="View full log">
            <IconButton
              size="small"
              onClick={() => navigate(`/dashboard/logs/${entry.request_id}`)}
            >
              <OpenIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>

        {entry.question && (
          <Typography variant="body2" sx={{ fontWeight: 500, mb: 1.5 }}>
            {entry.question}
          </Typography>
        )}

        {(entry.generated_query || entry.final_query) && (
          <Box sx={{ mb: 1.5 }}>
            <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
              {entry.final_query ? 'Final Query' : 'Generated Query'}
            </Typography>
            <CodeBlock code={entry.final_query || entry.generated_query} />
          </Box>
        )}

        {entry.natural_language_response && (
          <Box sx={{ mb: 1 }}>
            <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
              Response
            </Typography>
            <CollapsibleResponse text={entry.natural_language_response} />
          </Box>
        )}

        {followUps.length > 0 && (
          <Box sx={{ mt: 1.5 }}>
            <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
              Suggested Follow-ups
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
              {followUps.map((q, i) => (
                <Typography key={i} variant="caption" sx={{ pl: 1, borderLeft: '2px solid', borderColor: 'divider', color: 'text.secondary', mb: 0 }}>
                  {q}
                </Typography>
              ))}
            </Box>
          </Box>
        )}

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mt: 1 }}>
          <Typography variant="caption" color="text.secondary" sx={{ fontFamily: '"JetBrains Mono", monospace', mb: 0 }}>
            {formatDuration(entry.total_duration_ms)}
          </Typography>
          {entry.error && (
            <Alert severity="error" sx={{ py: 0, borderRadius: '6px', flex: 1 }}>
              <Typography variant="caption" sx={{ mb: 0 }}>{entry.error}</Typography>
            </Alert>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}

export default function SessionDetail() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getSessionDetail(sessionId)
      .then(setSession)
      .catch((err) => setError(err.response?.data?.detail || 'Failed to load session'))
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ py: 4 }}>
        <Alert severity="error" sx={{ borderRadius: '8px', mb: 2 }}>{error}</Alert>
        <Button startIcon={<BackIcon />} onClick={() => navigate('/dashboard/sessions')}>
          Back to Sessions
        </Button>
      </Box>
    );
  }

  if (!session) return null;

  const queries = session.queries || [];
  const timeRange =
    session.first_activity && session.last_activity
      ? `${format(parseISO(session.first_activity), 'MMM d, HH:mm', { in: DASHBOARD_TZ })} — ${format(parseISO(session.last_activity), 'MMM d, HH:mm', { in: DASHBOARD_TZ })}`
      : '-';

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
        <IconButton onClick={() => navigate('/dashboard/sessions')} size="small">
          <BackIcon />
        </IconButton>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Typography
              variant="body2"
              sx={{ fontFamily: '"JetBrains Mono", monospace', color: 'text.secondary', mb: 0 }}
            >
              {sessionId}
            </Typography>
            <CopyButton text={sessionId} />
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ mb: 0 }}>
            {timeRange}
          </Typography>
        </Box>
      </Box>

      {/* Summary cards */}
      <Grid container spacing={1.5} sx={{ mb: 3 }}>
        <Grid item xs={6} sm={3} md={2.4}>
          <Card>
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 }, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0, display: 'block' }}>
                Turns
              </Typography>
              <Typography variant="h4" sx={{ mb: 0 }}>{session.turn_count ?? queries.length}</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={3} md={2.4}>
          <Card>
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 }, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0, display: 'block' }}>
                Duration
              </Typography>
              <Typography variant="h4" sx={{ mb: 0, fontFamily: '"JetBrains Mono", monospace' }}>
                {formatDuration(session.total_duration_ms)}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={3} md={2.4}>
          <Card>
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 }, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0, display: 'block' }}>
                Internal Knowledge
              </Typography>
              <Typography variant="h4" sx={{ mb: 0, color: session.internal_knowledge_count ? 'warning.dark' : 'text.primary' }}>
                {session.internal_knowledge_count || 0}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={3} md={2.4}>
          <Card>
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 }, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0, display: 'block' }}>
                Models
              </Typography>
              <Box sx={{ display: 'flex', gap: 0.5, justifyContent: 'center', flexWrap: 'wrap', mt: 0.5 }}>
                {(session.models_used || []).map((m) => (
                  <Chip key={m} label={m} size="small" variant="outlined" sx={{ fontSize: '0.7rem' }} />
                ))}
                {(!session.models_used || session.models_used.length === 0) && <Typography variant="body2">-</Typography>}
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={3} md={2.4}>
          <Card>
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 }, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0, display: 'block' }}>
                Client
              </Typography>
              <Typography variant="body2" sx={{ fontFamily: '"JetBrains Mono", monospace', mb: 0 }}>
                {session.client_id || '-'}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Conversation timeline */}
      <Typography variant="h5" sx={{ mb: 1.5 }}>Conversation Timeline</Typography>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
        {queries.map((entry, i) => {
          const prevFollowUps = i > 0 ? (queries[i - 1].follow_up_questions || []) : [];
          const isFollowUp = prevFollowUps.some(
            (q) => q.trim().toLowerCase() === (entry.question || '').trim().toLowerCase()
          );
          return (
            <Box
              key={entry.request_id || i}
              sx={{
                display: 'flex',
                gap: 2,
                position: 'relative',
              }}
            >
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 24, flexShrink: 0 }}>
                <Box
                  sx={{
                    width: 12,
                    height: 12,
                    borderRadius: '50%',
                    bgcolor: entry.status === 'completed' ? 'success.main'
                      : entry.status === 'failed' ? 'error.main'
                      : 'grey.400',
                    mt: '18px',
                    flexShrink: 0,
                  }}
                />
                {i < queries.length - 1 && (
                  <Box sx={{ flex: 1, width: 2, bgcolor: 'divider', minHeight: 20 }} />
                )}
              </Box>
              {/* Content */}
              <Box sx={{ flex: 1, pb: 2 }}>
                <TurnCard entry={entry} index={i} navigate={navigate} isFollowUp={isFollowUp} />
              </Box>
            </Box>
          );
        })}
      </Box>

      {queries.length === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
          No queries in this session.
        </Typography>
      )}

      {/* Link to filtered logs */}
      {queries.length > 0 && (
        <Box sx={{ mt: 2, textAlign: 'center' }}>
          <Button
            variant="outlined"
            startIcon={<OpenIcon />}
            onClick={() => navigate(`/dashboard/logs`, { state: { sessionId } })}
          >
            View All Logs for This Session
          </Button>
        </Box>
      )}
    </Box>
  );
}
