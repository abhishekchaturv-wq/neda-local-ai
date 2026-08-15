import json
import os
def cache_data(filename, data):
    """Cache data to a file.

    Args:
    filename (str): The filename to cache the data under.
    data (any): The data to cache.

    Returns:
    None
    """
    with open(f"cache/{filename}.json", "w") as f:
        json.dump(data, f)
def get_cached_data(filename):
    """Retrieve cached data from a file.

    Args:
    filename (str): The filename to retrieve the data from.

    Returns:
    any: The cached data or None if the file does not exist.
    """
    if os.path.exists(f"cache/{filename}.json"):
        with open(f"cache/{filename}.json", "r") as f:
            return json.load(f)
    return None
