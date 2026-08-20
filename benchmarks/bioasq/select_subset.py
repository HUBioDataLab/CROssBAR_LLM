from pathlib import Path
import json
import argparse
import random
import itertools

from typing import Optional, Union
from pydantic import BaseModel, FilePath, HttpUrl, model_validator, validate_call


class BioASQConfig(BaseModel):
    input_file: FilePath
    output_file: Path
    question_type: str
    size: int
    seed: int = 49


class Snippets(BaseModel):
    offsetInBeginSection: int
    offsetInEndSection: int
    text: str
    beginSection: str
    endSection: str
    document: HttpUrl

class Triples(BaseModel):
    p: HttpUrl
    s: HttpUrl
    o: HttpUrl | str
    
class BioASQBenchmarkQuestion(BaseModel):
    id: str
    body: str
    type: str
    documents: list[HttpUrl]
    ideal_answer: list[str]
    exact_answer: Optional[Union[
        str,
        list[str],
        list[list[str]]
    ]] = None
    concepts: Optional[list[HttpUrl]] = None
    snippets: list[Snippets]
    triples: Optional[list[Triples]] = None

    @model_validator(mode="after")
    def process_exact_answer(self):
        if isinstance(self.exact_answer, list) and self.exact_answer and all(
            isinstance(item, list) for item in self.exact_answer
        ):
            self.exact_answer = list(itertools.chain.from_iterable(self.exact_answer))

        return self

def load_json_file(file_path: Path) -> list[dict]:
    """
    Load a JSON file and return its content as a list of dictionaries.

    Args:
        file_path (Path): The path to the JSON file.


    Returns:
        list[dict]: The content of the JSON file as a list of dictionaries.
    """
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise FileNotFoundError(f"File not found or is empty: {file_path}")
    
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)

@validate_call
def select_subset_by_type(data: list[dict], question_type: str, size: int, seed: int) -> list[dict]:
    """
    Select a subset of the data based on the specified type.

    Args:
        data (list[dict]): The input data as a list of dictionaries.
        question_type (str): The type to filter by.
        size (int): The number of entries to randomly select from the filtered type.
        seed (int): The random seed for reproducibility.

    Returns:
        list[dict]: A subset of the data containing only entries with the specified type.
    """
    selected = [item for item in data if item["type"] == question_type]

    if not selected:
        raise ValueError(f"No entries found for type: {question_type}")

    if size > len(selected):
        raise ValueError(f"Requested size ({size}) is larger than the available entries for type: {question_type}")

    rng = random.Random(seed)
    return [BioASQBenchmarkQuestion.model_validate(sampled).model_dump(mode="json") for sampled in rng.sample(selected, size)]

def save_json_file(data: list[dict], file_path: Path) -> None:
    """
    Save the given data to a JSON file.

    Args:
        data (list[dict]): The data to be saved.
        file_path (Path): The path to the output JSON file.
    """
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@validate_call
def select_subset_and_save(input_file: Path, output_file: Path, question_type: str, size: int, seed: int) -> None:
    """
    Load data from the input JSON file, select a subset based on the specified type,
    and save the subset to the output JSON file.

    Args:
        input_file (Path): The path to the input JSON file.
        output_file (Path): The path to the output JSON file.
        question_type (str): The type to filter by.
        size (int): The number of entries to randomly select from the filtered type.
        seed (int): The random seed for reproducibility.
    """
    data = load_json_file(input_file)
    subset = select_subset_by_type(data["questions"], question_type, size, seed)
    save_json_file(subset, output_file)

def main():
    parser = argparse.ArgumentParser(description="Select a subset of BioASQ benchmark questions based on type.")
    parser.add_argument("--input_file", type=Path, help="Path to the input JSON file containing BioASQ benchmark questions.")
    parser.add_argument("--output_file", type=Path, help="Path to the output JSON file to save the selected subset.")
    parser.add_argument("--question_type", type=str, help="The type field of BioASQ benchmark questions to filter by (e.g., 'factoid', 'list', 'yesno').")
    parser.add_argument("--size", type=int, default=100, help="The number of entries to randomly select from the filtered type (default: 100).")
    parser.add_argument("--seed", type=int, default=49, help="Random seed for reproducibility (default: 49).")

    args = parser.parse_args()

    config = BioASQConfig(
        input_file=args.input_file,
        output_file=args.output_file,
        question_type=args.question_type,
        size=args.size,
        seed=args.seed
    )

    select_subset_and_save(config.input_file, config.output_file, config.question_type, config.size, config.seed)

if __name__ == "__main__":
    main()

