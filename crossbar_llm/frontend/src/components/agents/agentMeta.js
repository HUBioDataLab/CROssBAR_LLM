import HubIcon from '@mui/icons-material/Hub';
import ArticleOutlinedIcon from '@mui/icons-material/ArticleOutlined';
import BiotechIcon from '@mui/icons-material/Biotech';

/**
 * How each agent looks in the UI. The colour is the agent's identity across
 * the toggles, the live progress and the answer's source tags, so one agent
 * reads the same everywhere.
 *
 * `fallback` mirrors the backend's `GET /agents` entry, used only when that
 * request fails so the panel still renders.
 */
export const AGENT_META = {
  knowledge_graph: {
    tag: 'KG',
    color: '#2563eb',
    Icon: HubIcon,
    working: 'Querying the knowledge graph…',
    fallback: {
      id: 'knowledge_graph',
      name: 'Knowledge Graph',
      kind: 'knowledge_graph',
      summary: 'Generates Cypher over the CROssBARv2 biomedical knowledge graph.',
      available: true,
      supports_vector_search: true,
    },
  },
  paperclip: {
    tag: 'Paperclip',
    color: '#c2410c',
    Icon: ArticleOutlinedIcon,
    working: 'Searching the literature…',
    fallback: {
      id: 'paperclip',
      name: 'Paperclip',
      kind: 'literature',
      summary: 'Broad literature search with citable source links.',
      available: true,
      supports_vector_search: false,
    },
  },
  pubtator3: {
    tag: 'PubTator3',
    color: '#7c3aed',
    Icon: BiotechIcon,
    working: 'Searching annotated PubMed…',
    fallback: {
      id: 'pubtator3',
      name: 'PubTator3',
      kind: 'literature',
      summary: 'NCBI entity- and relation-aware publication evidence.',
      available: true,
      supports_vector_search: false,
    },
  },
};

export const AGENT_ORDER = ['knowledge_graph', 'paperclip', 'pubtator3'];

export const FALLBACK_CATALOG = AGENT_ORDER.map((id) => AGENT_META[id].fallback);

export const DEFAULT_ENABLED_AGENTS = { knowledge_graph: true, paperclip: true, pubtator3: true };

const UNKNOWN_META = { tag: 'Agent', color: '#64748b', Icon: HubIcon, working: 'Working…' };

export const agentMeta = (id) => AGENT_META[id] || UNKNOWN_META;

export const agentName = (id, catalog) =>
  catalog?.find((agent) => agent.id === id)?.name || AGENT_META[id]?.fallback.name || id;

/** Agents the user switched on that can actually run on this server. */
export const effectiveAgents = (enabled, catalog) =>
  Object.fromEntries(
    AGENT_ORDER.map((id) => {
      const info = catalog?.find((agent) => agent.id === id);
      return [id, Boolean(enabled[id]) && (info ? info.available : true)];
    }),
  );

export const enabledCount = (agents) => Object.values(agents).filter(Boolean).length;
