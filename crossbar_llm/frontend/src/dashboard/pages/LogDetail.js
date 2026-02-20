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
  Step,
  StepContent,
  StepLabel,
  Stepper,
  Tab,
  Tabs,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import {
  ArrowBack as BackIcon,
  ContentCopy as CopyIcon,
  CheckCircle as CompletedIcon,
  Error as ErrorIcon,
  HourglassEmpty as PendingIcon,
  Schedule as DurationIcon,
  Link as LinkIcon,
} from '@mui/icons-material';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { getLogDetail } from '../services/api';
import { format, parseISO } from 'date-fns';

// ---------- Helpers ----------

function formatDuration(ms) {
  if (ms == null || ms === 0) return '-';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTokens(n) {
  if (n == null) return '-';
  return n.toLocaleString();
}

function searchTypeLabel(t) {
  if (t === 'generate_and_execute') return 'Generate & Execute';
  if (t === 'db_search') return 'Generate Only';
  if (t === 'query_execution') return 'Execute Only';
  if (t === 'query_execution_with_retry') return 'Execute Only';
  return t || '-';
}

function StatusChip({ status }) {
  const map = {
    completed: { color: 'success', icon: <CompletedIcon sx={{ fontSize: 14 }} /> },
    failed: { color: 'error', icon: <ErrorIcon sx={{ fontSize: 14 }} /> },
    in_progress: { color: 'warning', icon: <PendingIcon sx={{ fontSize: 14 }} /> },
    pending: { color: 'default', icon: <PendingIcon sx={{ fontSize: 14 }} /> },
  };
  const cfg = map[status] || map.pending;
  return (
    <Chip
      label={status || 'unknown'}
      size="small"
      color={cfg.color}
      icon={cfg.icon}
      sx={{ fontWeight: 600 }}
    />
  );
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

function InfoRow({ label, value, mono = false }) {
  return (
    <Box sx={{ display: 'flex', gap: 2, py: 0.75 }}>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ width: 140, flexShrink: 0, mb: 0 }}
      >
        {label}
      </Typography>
      <Typography
        variant="body2"
        sx={{
          mb: 0,
          fontFamily: mono ? '"JetBrains Mono", monospace' : 'inherit',
          wordBreak: 'break-all',
        }}
      >
        {value ?? '-'}
      </Typography>
    </Box>
  );
}

// ---------- Tab Panels ----------

function TabPanel({ value, index, children }) {
  if (value !== index) return null;
  return <Box sx={{ pt: 2 }}>{children}</Box>;
}

// Overview tab
function OverviewTab({ log }) {
  return (
    <Card>
      <CardContent>
        <Typography variant="h5" sx={{ mb: 2 }}>Request Details</Typography>
        <InfoRow label="Question" value={log.question} />
        <InfoRow label="Model" value={log.model_name} />
        <InfoRow label="Provider" value={log.provider} />
        <InfoRow label="Type" value={searchTypeLabel(log.search_type)} />
        <InfoRow label="Top K" value={log.top_k} />
        <InfoRow label="Vector Index" value={log.vector_index} />
        <InfoRow label="Client" value={log.client_ip || log.client_id} mono />
        {log.linked_request_id && (
          <InfoRow
            label="Linked Request"
            value={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <LinkIcon sx={{ fontSize: 14, color: 'primary.main' }} />
                <span>{log.linked_request_id}</span>
              </Box>
            }
          />
        )}
        <Divider sx={{ my: 2 }} />
        <Typography variant="h5" sx={{ mb: 2 }}>Timing</Typography>
        <InfoRow label="Start" value={log.start_time} mono />
        <InfoRow label="End" value={log.end_time} mono />
        <InfoRow label="Total Duration" value={formatDuration(log.total_duration_ms)} mono />
      </CardContent>
    </Card>
  );
}

// Pipeline Steps tab
function StepsTab({ steps }) {
  if (!steps?.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No pipeline steps recorded.
      </Typography>
    );
  }

  // Color code steps by type
  const stepColor = (name) => {
    if (name === 'cypher_generation') return 'primary';
    if (name === 'query_correction') return 'info';
    if (name === 'neo4j_execution') return 'warning';
    if (name === 'qa_response_generation') return 'secondary';
    if (name === 'follow_up_generation') return 'default';
    return 'default';
  };

  return (
    <Card>
      <CardContent>
        <Stepper orientation="vertical" activeStep={-1}>
          {steps.map((step, i) => (
            <Step key={i} completed={step.status === 'completed'}>
              <StepLabel
                error={step.status === 'failed'}
                optional={
                  <Typography variant="caption" color="text.secondary">
                    {formatDuration(step.duration_ms)}
                  </Typography>
                }
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip
                    label={step.step_name}
                    size="small"
                    color={stepColor(step.step_name)}
                    variant="outlined"
                    sx={{ fontWeight: 600, fontFamily: '"JetBrains Mono", monospace', fontSize: '0.75rem' }}
                  />
                  <StatusChip status={step.status} />
                </Box>
              </StepLabel>
              <StepContent>
                {step.start_time && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                    {step.start_time} → {step.end_time}
                  </Typography>
                )}
                {step.error && (
                  <Alert severity="error" sx={{ mt: 1, borderRadius: '8px' }}>
                    {step.error}
                  </Alert>
                )}
                {step.details && Object.keys(step.details).length > 0 && (
                  <Box sx={{ mt: 1 }}>
                    <CodeBlock code={JSON.stringify(step.details, null, 2)} language="json" />
                  </Box>
                )}
              </StepContent>
            </Step>
          ))}
        </Stepper>
      </CardContent>
    </Card>
  );
}

// LLM Calls tab
function LLMCallsTab({ calls }) {
  if (!calls?.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No LLM calls recorded.
      </Typography>
    );
  }
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {calls.map((call, i) => {
        const usage = call.token_usage || {};
        return (
          <Card key={i}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2, flexWrap: 'wrap' }}>
                <Chip label={call.call_type || 'unknown'} size="small" color="primary" variant="outlined" />
                <Chip label={call.model_name || '-'} size="small" variant="outlined" />
                <Chip label={call.provider || '-'} size="small" variant="outlined" />
                <Box sx={{ flex: 1 }} />
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <DurationIcon sx={{ fontSize: 14, color: 'text.secondary' }} />
                  <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace' }}>
                    {formatDuration(call.duration_ms)}
                  </Typography>
                </Box>
              </Box>

              {/* Token usage */}
              <Grid container spacing={2} sx={{ mb: 2 }}>
                <Grid item xs={4}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0 }}>
                    Input Tokens
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600, mb: 0 }}>
                    {formatTokens(usage.input_tokens)}
                  </Typography>
                </Grid>
                <Grid item xs={4}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0 }}>
                    Output Tokens
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600, mb: 0 }}>
                    {formatTokens(usage.output_tokens)}
                  </Typography>
                </Grid>
                <Grid item xs={4}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0 }}>
                    Total Tokens
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600, mb: 0 }}>
                    {formatTokens(usage.total_tokens)}
                  </Typography>
                </Grid>
              </Grid>

              {/* Response */}
              {call.raw_response && (
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                    Response
                  </Typography>
                  <CodeBlock code={call.raw_response} language={call.call_type === 'cypher_generation' ? 'cypher' : 'markdown'} />
                </Box>
              )}

              {/* Thinking content */}
              {call.thinking_content && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                    Chain of Thought
                  </Typography>
                  <Box
                    sx={{
                      p: 2,
                      borderRadius: '8px',
                      bgcolor: 'background.subtle',
                      fontSize: '0.8125rem',
                      whiteSpace: 'pre-wrap',
                      fontFamily: '"JetBrains Mono", monospace',
                    }}
                  >
                    {call.thinking_content}
                  </Box>
                </Box>
              )}

              {/* Error */}
              {call.error && (
                <Alert severity="error" sx={{ mt: 2, borderRadius: '8px' }}>
                  {call.error}
                </Alert>
              )}
            </CardContent>
          </Card>
        );
      })}
    </Box>
  );
}

// Query tab
function QueryTab({ log }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {log.generated_query && (
        <Card>
          <CardContent>
            <Typography variant="h5" sx={{ mb: 1.5 }}>Generated Query</Typography>
            <CodeBlock code={log.generated_query} />
          </CardContent>
        </Card>
      )}

      {log.query_correction && (
        <Card>
          <CardContent>
            <Typography variant="h5" sx={{ mb: 1.5 }}>Query Correction</Typography>
            <InfoRow label="Success" value={log.query_correction.success ? 'Yes' : 'No'} />
            <InfoRow label="Schemas Checked" value={log.query_correction.schemas_checked} />
            <InfoRow label="Duration" value={formatDuration(log.query_correction.duration_ms)} />
            {log.query_correction.failure_reason && (
              <InfoRow label="Failure Reason" value={log.query_correction.failure_reason} />
            )}
            {log.query_correction.corrections?.length > 0 && (
              <Box sx={{ mt: 1.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                  Corrections
                </Typography>
                <CodeBlock
                  code={JSON.stringify(log.query_correction.corrections, null, 2)}
                  language="json"
                />
              </Box>
            )}
          </CardContent>
        </Card>
      )}

      {log.final_query && (
        <Card>
          <CardContent>
            <Typography variant="h5" sx={{ mb: 1.5 }}>Final Query</Typography>
            <CodeBlock code={log.final_query} />
          </CardContent>
        </Card>
      )}
    </Box>
  );
}

// Neo4j Execution tab
function Neo4jTab({ execution }) {
  if (!execution) {
    return (
      <Typography variant="body2" color="text.secondary">
        No Neo4j execution recorded.
      </Typography>
    );
  }
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Card>
        <CardContent>
          <Typography variant="h5" sx={{ mb: 1.5 }}>Execution Details</Typography>
          <InfoRow label="Connection" value={execution.connection_status} />
          <InfoRow label="Execution Time" value={formatDuration(execution.execution_time_ms)} mono />
          <InfoRow label="Result Count" value={execution.result_count} />
          <InfoRow label="Top K" value={execution.top_k} />
          {execution.error && (
            <Alert severity="error" sx={{ mt: 1.5, borderRadius: '8px' }}>
              {execution.error}
            </Alert>
          )}
        </CardContent>
      </Card>

      {execution.query && (
        <Card>
          <CardContent>
            <Typography variant="h5" sx={{ mb: 1.5 }}>Executed Query</Typography>
            <CodeBlock code={execution.query_with_limit || execution.query} />
          </CardContent>
        </Card>
      )}

      {execution.result_sample?.length > 0 && (
        <Card>
          <CardContent>
            <Typography variant="h5" sx={{ mb: 1.5 }}>
              Result Sample ({execution.result_sample.length} rows)
            </Typography>
            <CodeBlock
              code={JSON.stringify(execution.result_sample, null, 2)}
              language="json"
            />
          </CardContent>
        </Card>
      )}
    </Box>
  );
}

// Response tab
function ResponseTab({ log }) {
  return (
    <Card>
      <CardContent>
        <Typography variant="h5" sx={{ mb: 1.5 }}>Natural Language Response</Typography>
        {log.natural_language_response ? (
          <Box
            sx={{
              p: 2,
              borderRadius: '8px',
              bgcolor: 'background.subtle',
              fontSize: '0.875rem',
              lineHeight: 1.7,
              whiteSpace: 'pre-wrap',
            }}
          >
            {log.natural_language_response}
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary">
            No response recorded.
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

// Errors tab
function ErrorsTab({ log }) {
  if (!log.error) {
    return (
      <Box sx={{ textAlign: 'center', py: 4 }}>
        <CompletedIcon sx={{ fontSize: 48, color: 'success.main', mb: 1 }} />
        <Typography variant="body1" color="text.secondary">
          No errors occurred during this request.
        </Typography>
      </Box>
    );
  }
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Alert severity="error" sx={{ borderRadius: '8px' }}>
        <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
          {log.error_type || 'Error'}
          {log.error_step && ` (step: ${log.error_step})`}
        </Typography>
        <Typography variant="body2" sx={{ mb: 0 }}>{log.error}</Typography>
      </Alert>
      {log.error_traceback && (
        <Card>
          <CardContent>
            <Typography variant="h5" sx={{ mb: 1.5 }}>Traceback</Typography>
            <CodeBlock code={log.error_traceback} language="python" />
          </CardContent>
        </Card>
      )}
    </Box>
  );
}

// ---------- Page ----------

export default function LogDetail() {
  const { requestId } = useParams();
  const navigate = useNavigate();
  const [log, setLog] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getLogDetail(requestId)
      .then(setLog)
      .catch((err) => {
        setError(err.response?.data?.detail || 'Failed to load log entry');
      })
      .finally(() => setLoading(false));
  }, [requestId]);

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
        <Button startIcon={<BackIcon />} onClick={() => navigate('/dashboard/logs')}>
          Back to Logs
        </Button>
      </Box>
    );
  }

  if (!log) return null;

  // Build tab list dynamically
  const tabs = [
    { label: 'Overview', key: 'overview' },
    { label: `Steps (${log.steps?.length || 0})`, key: 'steps' },
    { label: `LLM Calls (${log.llm_calls?.length || 0})`, key: 'llm' },
  ];
  if (log.generated_query || log.query_correction || log.final_query) {
    tabs.push({ label: 'Query', key: 'query' });
  }
  if (log.neo4j_execution) {
    tabs.push({ label: 'Neo4j', key: 'neo4j' });
  }
  if (log.natural_language_response) {
    tabs.push({ label: 'Response', key: 'response' });
  }
  if (log.error) {
    tabs.push({ label: 'Errors', key: 'errors' });
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
        <IconButton onClick={() => navigate('/dashboard/logs')} size="small">
          <BackIcon />
        </IconButton>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Typography
              variant="body2"
              sx={{
                fontFamily: '"JetBrains Mono", monospace',
                color: 'text.secondary',
                mb: 0,
              }}
            >
              {requestId}
            </Typography>
            <CopyButton text={requestId} />
            <StatusChip status={log.status} />
            <Chip
              label={searchTypeLabel(log.search_type)}
              size="small"
              color={log.search_type === 'generate_and_execute' ? 'primary' : 'default'}
              variant="outlined"
            />
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ mb: 0 }}>
            {log.timestamp
              ? format(parseISO(log.timestamp), 'MMMM d, yyyy HH:mm:ss')
              : ''}
            {' · '}
            {formatDuration(log.total_duration_ms)}
            {' · '}
            {log.model_name}
          </Typography>
        </Box>
      </Box>

      {/* Question */}
      {log.question && (
        <Card sx={{ mb: 2 }}>
          <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
            <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
              Question
            </Typography>
            <Typography variant="body1" sx={{ fontWeight: 500, mb: 0 }}>
              {log.question}
            </Typography>
          </CardContent>
        </Card>
      )}

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 0 }}>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          variant="scrollable"
          scrollButtons="auto"
        >
          {tabs.map((t) => (
            <Tab
              key={t.key}
              label={t.label}
              sx={t.key === 'errors' ? { color: 'error.main' } : undefined}
            />
          ))}
        </Tabs>
      </Box>

      {tabs.map((t, i) => {
        if (t.key === 'overview') return <TabPanel key={t.key} value={tab} index={i}><OverviewTab log={log} /></TabPanel>;
        if (t.key === 'steps') return <TabPanel key={t.key} value={tab} index={i}><StepsTab steps={log.steps} /></TabPanel>;
        if (t.key === 'llm') return <TabPanel key={t.key} value={tab} index={i}><LLMCallsTab calls={log.llm_calls} /></TabPanel>;
        if (t.key === 'query') return <TabPanel key={t.key} value={tab} index={i}><QueryTab log={log} /></TabPanel>;
        if (t.key === 'neo4j') return <TabPanel key={t.key} value={tab} index={i}><Neo4jTab execution={log.neo4j_execution} /></TabPanel>;
        if (t.key === 'response') return <TabPanel key={t.key} value={tab} index={i}><ResponseTab log={log} /></TabPanel>;
        if (t.key === 'errors') return <TabPanel key={t.key} value={tab} index={i}><ErrorsTab log={log} /></TabPanel>;
        return null;
      })}
    </Box>
  );
}
