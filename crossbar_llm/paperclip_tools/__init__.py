"""Paperclip literature-evidence agent.

Answers a biomedical question from Paperclip's full-text corpora with a cited
answer. Self-contained: nothing here imports the PubTator3 agent, so the two
evolve independently.

    from crossbar_llm.paperclip_tools.agent import build_graph
    from crossbar_llm.paperclip_tools.llm import build_chat_model

    graph = build_graph(chat_model=build_chat_model(model="gpt-4o-mini"))
    state = await graph.ainvoke({"question": "...", "warnings": []})
"""
