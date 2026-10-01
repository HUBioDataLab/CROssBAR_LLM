import { initialProgress, progressHeadline, reduceProgress } from './orchestrationProgress';
import { parseSseBlock } from './sse';

const run = (events, now = 1000) =>
  events.reduce((state, [event, data]) => reduceProgress(state, event, data, now), initialProgress(0));

describe('reduceProgress', () => {
  test('routing marks selected agents queued and the rest skipped with a reason', () => {
    const state = run([
      ['orchestration.started', { enabled: ['knowledge_graph', 'paperclip', 'pubtator3'] }],
      [
        'routing.completed',
        {
          selected: ['knowledge_graph', 'pubtator3'],
          reasons: { pubtator3: 'named entities' },
          skipped: { paperclip: 'Not needed for this question.' },
        },
      ],
    ]);

    expect(state.phase).toBe('running');
    expect(state.agents.knowledge_graph.status).toBe('queued');
    expect(state.agents.pubtator3.reason).toBe('named entities');
    expect(state.agents.paperclip).toMatchObject({ status: 'skipped', reason: 'Not needed for this question.' });
  });

  test('an agent moves from running through its steps to completed', () => {
    const state = run([
      ['orchestration.started', { enabled: ['knowledge_graph'] }],
      ['routing.completed', { selected: ['knowledge_graph'] }],
      ['agent.started', { agent: 'knowledge_graph' }],
      ['agent.progress', { agent: 'knowledge_graph', step: 'generate_cypher', label: 'Generated a Cypher query' }],
      ['agent.completed', { agent: 'knowledge_graph', status: 'failed', duration_seconds: 4.2, warnings: ['no rows'] }],
    ]);

    expect(state.agents.knowledge_graph).toMatchObject({
      status: 'failed',
      startedAt: 1000,
      durationSeconds: 4.2,
      warnings: ['no rows'],
      steps: [{ step: 'generate_cypher', label: 'Generated a Cypher query' }],
    });
  });

  test('a fast agent that starts before routing is reported keeps its running status', () => {
    const state = run([
      ['orchestration.started', { enabled: ['paperclip'] }],
      ['agent.started', { agent: 'paperclip' }],
      ['routing.completed', { selected: ['paperclip'] }],
    ]);

    expect(state.agents.paperclip.status).toBe('running');
  });

  test('review and synthesis phases are reflected in the headline', () => {
    const review = run([['review.required', { agent: 'knowledge_graph' }]]);
    expect(review.phase).toBe('review');
    expect(review.agents.knowledge_graph.status).toBe('awaiting_review');
    expect(progressHeadline(review)).toMatch(/review/);

    const merged = run([
      ['synthesis.started', { agents: ['knowledge_graph', 'paperclip'] }],
      ['synthesis.completed', { synthesized: true, contradictions: 2 }],
    ]);
    expect(merged.synthesis).toEqual({
      status: 'done',
      agents: ['knowledge_graph', 'paperclip'],
      synthesized: true,
      contradictions: 2,
    });
  });

  test('unknown events leave the state untouched', () => {
    const state = initialProgress(0);
    expect(reduceProgress(state, 'something.new', {})).toBe(state);
  });

  test('the reducer never mutates the previous state', () => {
    const before = run([['orchestration.started', { enabled: ['paperclip'] }]]);
    const snapshot = JSON.stringify(before);
    reduceProgress(before, 'agent.started', { agent: 'paperclip' });
    expect(JSON.stringify(before)).toBe(snapshot);
  });
});

describe('parseSseBlock', () => {
  test('reads the event name and JSON data', () => {
    expect(parseSseBlock('event: agent.started\ndata: {"agent": "paperclip"}')).toEqual({
      event: 'agent.started',
      data: { agent: 'paperclip' },
    });
  });

  test('ignores keep-alive comments', () => {
    expect(parseSseBlock(': keep-alive')).toBeNull();
  });
});
