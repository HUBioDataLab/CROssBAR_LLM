from pathlib import Path
import json
import argparse
import random

from pydantic import BaseModel, FilePath

class BioHopRConfig(BaseModel):
    input_file: FilePath
    output_file: Path
    hop_type: str
    size: int
    seed: int = 49


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


def select_subset_by_hop_type(data: list[dict], hop_type: str, size: int, seed: int) -> list[dict]:
    """
    Select a subset of the data based on the specified hop type.

    Args:
        data (list[dict]): The input data as a list of dictionaries.
        hop_type (str): The hop type to filter by.
        size (int): The number of entries to randomly select from the filtered hop type.
        seed (int): The random seed for reproducibility.

    Returns:
        list[dict]: A subset of the data containing only entries with the specified hop type.
    """
    selected = [item for item in data if item["relation_hop2"] == hop_type]

    if not selected:
        raise ValueError(f"No entries found for hop type: {hop_type}")

    if size > len(selected):
        raise ValueError(f"Requested size ({size}) is larger than the available entries for hop type: {hop_type}")

    rng = random.Random(seed)
    return rng.sample(selected, size)

def save_json_file(data: list[dict], file_path: Path) -> None:
    """
    Save the given data to a JSON file.

    Args:
        data (list[dict]): The data to be saved.
        file_path (Path): The path to the output JSON file.
    """
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def select_subset_and_save(input_file: Path, output_file: Path, hop_type: str, size: int, seed: int) -> None:
    """
    Load data from the input JSON file, select a subset based on the specified hop type,
    and save the subset to the output JSON file.

    Args:
        input_file (Path): The path to the input JSON file.
        output_file (Path): The path to the output JSON file.
        hop_type (str): The hop type to filter by.
        size (int): The number of entries to randomly select from the filtered hop type.
        seed (int): The random seed for reproducibility.
    """
    data = load_json_file(input_file)
    subset = select_subset_by_hop_type(data, hop_type, size, seed)
    save_json_file(subset, output_file)

def main():
    parser = argparse.ArgumentParser(description="Select a subset of BioHopR benchmark data based on hop type.")
    parser.add_argument("--input_file", type=Path, required=True, help="Path to the input JSON file containing BioHopR benchmark data.")
    parser.add_argument("--output_file", type=Path, required=True, help="Path to the output JSON file to save the selected subset.")
    parser.add_argument("--hop_type", type=str, required=True, help="The hop type to filter by 'relation_hop2' field of BioHopR data (e.g., disease:gene/protein:drug).")
    parser.add_argument("--size", type=int, default=50, help="The number of entries to randomly select from the filtered hop type (default: 50).")
    parser.add_argument("--seed", type=int, default=49, help="Random seed for reproducibility (default: 49).")

    args = parser.parse_args()

    config = BioHopRConfig(
        input_file=args.input_file,
        output_file=args.output_file,
        hop_type=args.hop_type,
        size=args.size,
        seed=args.seed
    )

    select_subset_and_save(config.input_file, config.output_file, config.hop_type, config.size, config.seed)

if __name__ == "__main__":
    main()
    