import axios from 'axios';
import { parseSseBlock } from '../utils/sse';

/**
 * API client for the CROssBAR-LLM agentic backend (FastAPI).
 *
 * The backend identifies browsers via an httpOnly `browser_id` cookie that is set
 * automatically on session creation. We only need `withCredentials: true` so the
 * browser sends that cookie on every request — the cookie is never read here.
 */

const REACT_APP_CROSSBAR_LLM_ROOT_PATH = process.env.REACT_APP_CROSSBAR_LLM_ROOT_PATH || '/llm';

const baseURL = process.env.NODE_ENV === 'development'
  ? `http://localhost:8001`
  : `https://crossbarv2.hubiodatalab.com${REACT_APP_CROSSBAR_LLM_ROOT_PATH}/api`;

const instance = axios.create({
  baseURL,
  withCredentials: true, // send the httpOnly browser_id cookie
  headers: {
    'Content-Type': 'application/json',
  },
});

/* ----------------------------- health / config ---------------------------- */

export const healthCheck = async () => {
  const response = await instance.get('/health');
  return response.data;
};

/** GET /models — provider→models map + defaults + supported search models. */
export const getModels = async () => {
  const response = await instance.get('/models');
  return response.data;
};

/** GET /agents — the agents the orchestrator can route to, and which can run here. */
export const getAgents = async () => {
  const response = await instance.get('/agents');
  return response.data;
};

/* -------------------------------- sessions -------------------------------- */

/** POST /sessions — create a server-side chat session. Returns { session_id }. */
export const createSession = async () => {
  const response = await instance.post('/sessions');
  return response.data;
};

/** DELETE /sessions/{sessionId} — remove a session server-side. */
export const deleteSession = async (sessionId) => {
  await instance.delete(`/sessions/${encodeURIComponent(sessionId)}`);
};

/* ------------------------------- db search -------------------------------- */

/**
 * POST /sessions/{sessionId}/db-search/query
 * Returns a ChatResponse (completed/failed) or PendingResumeResponse (awaiting review).
 */
export const dbSearch = async (sessionId, body, config) => {
  const response = await instance.post(
    `/sessions/${encodeURIComponent(sessionId)}/db-search/query`,
    body,
    config,
  );
  return response.data;
};

/* ----------------------------- vector search ------------------------------ */

/**
 * POST /sessions/{sessionId}/vector-search/query
 * Text-based vector search (the agent embeds the referenced entity).
 */
export const vectorSearch = async (sessionId, body, config) => {
  const response = await instance.post(
    `/sessions/${encodeURIComponent(sessionId)}/vector-search/query`,
    body,
    config,
  );
  return response.data;
};

/**
 * POST /sessions/{sessionId}/vector-search/upload-query
 * File-based vector search. `body` holds the JSON fields (question, model config,
 * vector_category, embedding_type, ...); `embeddingFile` is appended separately.
 * Content-Type is left to the browser so the multipart boundary is set correctly.
 */
export const vectorUploadSearch = async (sessionId, body, embeddingFile, config) => {
  const formData = new FormData();
  Object.entries(body).forEach(([key, value]) => {
    formData.append(key, value === null || value === undefined ? '' : value);
  });
  formData.append('embedding_file', embeddingFile);

  const response = await instance.post(
    `/sessions/${encodeURIComponent(sessionId)}/vector-search/upload-query`,
    formData,
    { headers: { 'Content-Type': undefined }, ...(config || {}) },
  );
  return response.data;
};

/* --------------------------------- resume --------------------------------- */

/**
 * POST /sessions/{sessionId}/resume
 * Human-in-the-loop: approve or edit the generated Cypher, then run.
 * `body` = { provider, model, top_k, reasoning_enabled, reasoning_effort,
 *             search_mode, action: 'approve'|'edit', edited_cypher }.
 */
export const resumeSession = async (sessionId, body, config) => {
  const response = await instance.post(
    `/sessions/${encodeURIComponent(sessionId)}/resume`,
    body,
    config,
  );
  return response.data;
};

/* ------------------------- streamed (orchestrated) ------------------------- */

/**
 * An error shaped like an axios error, so callers handle streamed and plain
 * requests the same way (`err.response.status`, `err.response.data.detail`).
 */
const httpError = (status, detail) => {
  const error = new Error(typeof detail === 'string' ? detail : `Request failed with status ${status}`);
  error.response = { status, data: { detail } };
  return error;
};

/**
 * POST to a `/stream` endpoint and read its server-sent events.
 *
 * Every progress event is handed to `onEvent(event, data)`. Resolves with the
 * final `result` payload (the same body the JSON endpoint returns); rejects
 * with an axios-shaped error for an `error` event or a non-2xx response, and
 * with an AbortError when `signal` aborts.
 *
 * Uses `fetch` rather than axios: axios cannot stream a response body in the
 * browser. `credentials: 'include'` sends the httpOnly browser_id cookie.
 */
const postEventStream = async (path, { json, formData }, { signal, onEvent } = {}) => {
  const response = await fetch(`${baseURL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: json ? { 'Content-Type': 'application/json', Accept: 'text/event-stream' } : { Accept: 'text/event-stream' },
    body: json ? JSON.stringify(json) : formData,
    signal,
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      detail = (await response.json())?.detail ?? detail;
    } catch {
      // Not JSON (e.g. a proxy error page): keep the status message.
    }
    throw httpError(response.status, detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      // Normalise the whole buffer, not each chunk: a CRLF pair can be split
      // across two chunks by a proxy that rewrites line endings.
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n');
      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const parsed = parseSseBlock(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf('\n\n');
        if (!parsed) continue;
        if (parsed.event === 'result') return parsed.data;
        if (parsed.event === 'error') throw httpError(parsed.data?.status_code || 500, parsed.data?.detail);
        onEvent?.(parsed.event, parsed.data);
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
  throw httpError(502, 'The connection closed before the answer was ready. Please try again.');
};

const sessionPath = (sessionId, path) => `/sessions/${encodeURIComponent(sessionId)}${path}`;

const agentFormFields = (body) => {
  const { agents, ...rest } = body;
  return {
    ...rest,
    knowledge_graph: agents?.knowledge_graph ?? true,
    paperclip: agents?.paperclip ?? true,
    pubtator3: agents?.pubtator3 ?? true,
  };
};

export const streamDbSearch = (sessionId, body, options) =>
  postEventStream(sessionPath(sessionId, '/db-search/query/stream'), { json: body }, options);

export const streamVectorSearch = (sessionId, body, options) =>
  postEventStream(sessionPath(sessionId, '/vector-search/query/stream'), { json: body }, options);

/** Multipart cannot carry the nested `agents` object, so its switches travel flat. */
export const streamVectorUploadSearch = (sessionId, body, embeddingFile, options) => {
  const formData = new FormData();
  Object.entries(agentFormFields(body)).forEach(([key, value]) => {
    formData.append(key, value === null || value === undefined ? '' : value);
  });
  formData.append('embedding_file', embeddingFile);
  return postEventStream(sessionPath(sessionId, '/vector-search/upload-query/stream'), { formData }, options);
};

export const streamResume = (sessionId, body, options) =>
  postEventStream(sessionPath(sessionId, '/resume/stream'), { json: body }, options);

export default instance;
