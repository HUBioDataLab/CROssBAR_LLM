"""LitSense agent — grounded question answering over the biomedical literature.

The public surface is the agent class::

    async with LitSenseAgent(Settings()) as agent:
        answer = await agent.answer("...")

The team's API wraps this class; `answer_question` and `run_pipeline` remain as one-shot
convenience functions over it.
"""

from crossbar_llm.litsense_tools.agent import LitSenseAgent, answer_question, run_pipeline
from crossbar_llm.litsense_tools.config import Settings
from crossbar_llm.litsense_tools.graph.state import PipelineState
from crossbar_llm.litsense_tools.models import Answer

__all__ = [
    "Answer",
    "LitSenseAgent",
    "PipelineState",
    "Settings",
    "answer_question",
    "run_pipeline",
]
__version__ = "0.1.0"
