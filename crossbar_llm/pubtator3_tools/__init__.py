"""PubTator3 literature-evidence agent.

Answers a biomedical question from NCBI's PubTator3 corpus with a cited answer.
Self-contained: nothing here imports the Paperclip agent, so the two evolve
independently.

    from crossbar_llm.pubtator3_tools.agent import build_graph
    from crossbar_llm.pubtator3_tools.llm import build_chat_model

    graph = build_graph(chat_model=build_chat_model(model="gpt-4o-mini"))
    state = await graph.ainvoke({"question": "...", "warnings": []})
"""
