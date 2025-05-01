import os
import json
import re

def create_suggestions():
    folder_path = "../../public/"
    # This set will now store tuples: (term, type)
    suggestions_set = set()
    for file_name in os.listdir(folder_path):
        if file_name.endswith("_names.txt"):
            # Extract node type from file name (remove _names.txt)
            node_type = file_name.replace("_names.txt", "")
            # Format node type for display (e.g., SideEffect -> Side Effect)
            formatted_node_type = re.sub(r'([a-z])([A-Z])', r'\1 \2', node_type)

            with open(os.path.join(folder_path, file_name), "r", encoding="utf-8") as f:
                content = f.read()
                for line in content.split("\n"):
                    if line.strip():  # Skip empty lines
                        # Replace any whitespace with _
                        term = re.sub(r"\s+", "_", line.strip())
                        # Add a tuple to the set - tuples are hashable
                        suggestions_set.add((term, formatted_node_type))

    suggestions_path = folder_path + "suggestions.json"

    # Convert the tuples back to dictionaries for JSON output
    suggestions_list_for_json = [{"term": item[0], "type": item[1]} for item in suggestions_set]

    with open(suggestions_path, "w", encoding="utf-8") as out_file:
        # Dump the list of dictionaries
        json.dump(suggestions_list_for_json, out_file, indent=4) # Added indent for readability


if __name__ == "__main__":
    create_suggestions()
    print("Suggestions created successfully.")
