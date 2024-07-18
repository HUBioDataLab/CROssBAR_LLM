from pathlib import Path
from typing import Optional

import streamlit.components.v1 as components
import os

# Path to the build directory
frontend_dir = (Path(__file__).parent / "frontend").absolute()
_component_func = components.declare_component(
    "autocomplete", path=str(frontend_dir)
)

def get_suggestions_from_files(directory):
    suggestions = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".txt"):
                with open(os.path.join(root, file), "r") as f:
                    suggestions.extend(f.read().splitlines())
    return suggestions

# Create the python function that will be called
def st_keyup(name, default="", key=""):
    suggestions = get_suggestions_from_files("./crossbar_llm/query_db")
    component_value = _component_func(name=name, default=default, suggestions=suggestions, key=key)
    return component_value