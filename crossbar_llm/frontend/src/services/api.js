import axios from 'axios';

/**
 * API client for the CROssBAR-LLM agentic backend (FastAPI).
 *
 * The backend identifies browsers via an httpOnly `browser_id` cookie that is set
 * automatically on session creation. We only need `withCredentials: true` so the
 * browser sends that cookie on every request — the cookie is never read here.
 */

const REACT_APP_CROSSBAR_LLM_ROOT_PATH = process.env.REACT_APP_CROSSBAR_LLM_ROOT_PATH || '/llm';

const baseURL = process.env.NODE_ENV === 'development'
  ? `http://localhost:8000`
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

export default instance;
