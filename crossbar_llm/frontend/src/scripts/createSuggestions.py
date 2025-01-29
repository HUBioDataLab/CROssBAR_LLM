import os
import json
import re

def create_suggestions():
    folder_path = "../../public/"
    suggestions_set = set()
    for file_name in os.listdir(folder_path):
        if file_name.endswith(".txt"):
            with open(os.path.join(folder_path, file_name), "r", encoding="utf-8") as f:
                content = f.read()
                for line in content.split("\n"):
                        # Replace any whitespace with _
                        word = re.sub(r"\s+", "_", line)
                        suggestions_set.add(word)
                        
    suggestions_path = folder_path + "suggestions.json"
    with open(suggestions_path, "w", encoding="utf-8") as out_file:
        json.dump(list(suggestions_set), out_file)


if __name__ == "__main__":
    create_suggestions()
