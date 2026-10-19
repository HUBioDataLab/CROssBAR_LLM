/**
 * Live progress of one orchestrated request, built from the backend's
 * server-sent events. A pure reducer: every call returns a new state object.
 *
 * @typedef {'pending'|'queued'|'running'|'completed'|'failed'|'skipped'|'awaiting_review'} AgentStatus
 *
 * @typedef {Object} AgentProgress
 * @property {AgentStatus} status
 * @property {{ step: string, label: string }[]} steps  Steps the agent finished, in order.
 * @property {number|null} startedAt                     ms timestamp, once running.
 * @property {number|null} durationSeconds
 * @property {string[]} warnings
 * @property {string|null} reason                        Why it was asked, or skipped.
 *
 * @typedef {Object} OrchestrationProgress
 * @property {'planning'|'running'|'review'|'synthesizing'|'rejected'} phase
 * @property {number} startedAt
 * @property {string[]} enabled
 * @property {Object|null} routing                       The `routing.completed` payload.
 * @property {Object<string, AgentProgress>} agents
 * @property {{ status: 'running'|'done', agents: string[], synthesized?: boolean, contradictions?: number }|null} synthesis
 * @property {string|null} rejectedReason
 */

const newAgent = (status, reason = null) => ({
  status,
  steps: [],
  startedAt: null,
  durationSeconds: null,
  warnings: [],
  reason,
});

/** @returns {OrchestrationProgress} */
export const initialProgress = (now = Date.now()) => ({
  phase: 'planning',
  startedAt: now,
  enabled: [],
  routing: null,
  agents: {},
  synthesis: null,
  rejectedReason: null,
});

const updateAgent = (state, agentId, update) => ({
  ...state,
  agents: {
    ...state.agents,
    [agentId]: { ...(state.agents[agentId] || newAgent('pending')), ...update },
  },
});

/**
 * @param {OrchestrationProgress} state
 * @param {string} event  The SSE event name.
 * @param {Object} data   Its JSON payload.
 * @returns {OrchestrationProgress}
 */
export const reduceProgress = (state, event, data = {}, now = Date.now()) => {
  switch (event) {
    case 'orchestration.started':
      return {
        ...state,
        phase: 'planning',
        enabled: data.enabled || [],
        agents: Object.fromEntries((data.enabled || []).map((id) => [id, newAgent('pending')])),
      };

    case 'routing.completed': {
      const selected = data.selected || [];
      const agents = { ...state.agents };
      selected.forEach((id) => {
        const current = agents[id];
        agents[id] = {
          ...(current || newAgent('queued')),
          status: !current || current.status === 'pending' ? 'queued' : current.status,
          reason: data.reasons?.[id] || null,
        };
      });
      state.enabled
        .filter((id) => !selected.includes(id))
        .forEach((id) => {
          agents[id] = { ...(agents[id] || newAgent('skipped')), status: 'skipped', reason: data.skipped?.[id] || null };
        });
      return { ...state, phase: 'running', routing: data, agents };
    }

    case 'relevance.rejected':
      return { ...state, phase: 'rejected', rejectedReason: data.reason || null };

    case 'agent.started':
      return updateAgent(state, data.agent, { status: 'running', startedAt: now });

    case 'agent.progress': {
      const current = state.agents[data.agent] || newAgent('running');
      return updateAgent(state, data.agent, {
        steps: [...current.steps, { step: data.step, label: data.label || data.step }],
      });
    }

    case 'agent.completed':
      return updateAgent(state, data.agent, {
        status: data.status || 'completed',
        durationSeconds: data.duration_seconds ?? null,
        warnings: data.warnings || [],
      });

    case 'review.required':
      return { ...updateAgent(state, data.agent, { status: 'awaiting_review' }), phase: 'review' };

    case 'synthesis.started':
      return { ...state, phase: 'synthesizing', synthesis: { status: 'running', agents: data.agents || [] } };

    case 'synthesis.completed':
      return {
        ...state,
        synthesis: {
          ...(state.synthesis || { agents: [] }),
          status: 'done',
          synthesized: Boolean(data.synthesized),
          contradictions: data.contradictions || 0,
        },
      };

    default:
      return state;
  }
};

/** A one-line description of what the orchestrator is doing right now. */
export const progressHeadline = (state) => {
  if (!state) return 'Starting…';
  const running = Object.values(state.agents).filter((agent) => agent.status === 'running').length;
  switch (state.phase) {
    case 'planning':
      return 'Planning which agents to ask…';
    case 'rejected':
      return 'Question is outside the biomedical domain';
    case 'review':
      return 'Cypher query ready for your review';
    case 'synthesizing':
      return 'Merging the agents’ answers…';
    default:
      return running > 0
        ? `${running} agent${running === 1 ? '' : 's'} working…`
        : 'Preparing your answer…';
  }
};
