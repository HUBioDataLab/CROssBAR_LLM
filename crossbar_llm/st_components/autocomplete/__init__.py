from pathlib import Path
import pickle

import streamlit.components.v1 as components
import os
import streamlit as st

# Path to the build directory
frontend_dir = (Path(__file__).parent / "frontend").absolute()
_component_func = components.declare_component(
    "autocomplete", path=str(frontend_dir)
)

@st.cache_data
def get_suggestions_from_files(directory):
    pickle_file = "./suggestions.pkl"

    if os.path.exists(pickle_file):
        # If pickle file exists, load suggestions from it
        with open(pickle_file, "rb") as f:
            return pickle.load(f)
    else:
        suggestions = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith(".txt"):
                    with open(os.path.join(root, file), "r") as f:
                        suggestions.extend(f.read().splitlines())
        
        with open(pickle_file, "wb") as f:
            pickle.dump(suggestions, f)
        return suggestions


# Create the python function that will be called
def st_keyup(name, default="", key=""):
    if 'suggestions' not in st.session_state:
        st.session_state.suggestions = get_suggestions_from_files("./crossbar_llm/query_db")
    return _component_func(name=name, default=default, suggestions=st.session_state.suggestions, key=key)