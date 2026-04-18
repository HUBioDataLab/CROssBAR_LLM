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
  Collapse,
  Divider,
  Grid,
  IconButton,
  Step,
  StepContent,
  StepLabel,
  Stepper,
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

function TurnCard({ entry, index, navigate }) {
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
  const theme = useTheme();
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

  const { queries = [], summary = {} } = session;
  const timeRange =
    summary.first_activity && summary.last_activity
      ? `${format(parseISO(summary.first_activity), 'MMM d, HH:mm', { in: DASHBOARD_TZ })} — ${format(parseISO(summary.last_activity), 'MMM d, HH:mm', { in: DASHBOARD_TZ })}`
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
        <Grid item xs={6} sm={3}>
          <Card>
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 }, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0, display: 'block' }}>
                Turns
              </Typography>
              <Typography variant="h4" sx={{ mb: 0 }}>{summary.turn_count ?? queries.length}</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={3}>
          <Card>
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 }, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0, display: 'block' }}>
                Duration
              </Typography>
              <Typography variant="h4" sx={{ mb: 0, fontFamily: '"JetBrains Mono", monospace' }}>
                {formatDuration(summary.total_duration_ms)}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={3}>
          <Card>
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 }, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0, display: 'block' }}>
                Models
              </Typography>
              <Box sx={{ display: 'flex', gap: 0.5, justifyContent: 'center', flexWrap: 'wrap', mt: 0.5 }}>
                {(summary.models_used || []).map((m) => (
                  <Chip key={m} label={m} size="small" variant="outlined" sx={{ fontSize: '0.7rem' }} />
                ))}
                {(!summary.models_used || summary.models_used.length === 0) && <Typography variant="body2">-</Typography>}
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={3}>
          <Card>
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 }, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0, display: 'block' }}>
                Client
              </Typography>
              <Typography variant="body2" sx={{ fontFamily: '"JetBrains Mono", monospace', mb: 0 }}>
                {summary.client_id || '-'}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Query timeline */}
      <Typography variant="h5" sx={{ mb: 1.5 }}>Conversation Timeline</Typography>
      <Stepper orientation="vertical" activeStep={-1}>
        {queries.map((entry, i) => (
          <Step key={entry.request_id || i} completed={entry.status === 'completed'}>
            <StepLabel
              error={entry.status === 'failed'}
              optional={
                <Typography variant="caption" color="text.secondary">
                  {formatDuration(entry.total_duration_ms)}
                </Typography>
              }
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="body2" noWrap sx={{ maxWidth: 400, mb: 0 }}>
                  {entry.question || entry.request_id || `Turn ${i + 1}`}
                </Typography>
                <StatusChip status={entry.status} />
              </Box>
            </StepLabel>
            <StepContent>
              <TurnCard entry={entry} index={i} navigate={navigate} />
            </StepContent>
          </Step>
        ))}
      </Stepper>

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
            onClick={() => navigate(`/dashboard/logs?session_id=${sessionId}`)}
          >
            View All Logs for This Session
          </Button>
        </Box>
      )}
    </Box>
  );
}
