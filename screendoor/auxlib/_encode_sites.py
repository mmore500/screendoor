def encode_sites(sites) -> str:
    """Sorted integers as compact ranges, e.g. ``{0, 1, 2, 5, 9}`` -> "0-2,5,9"."""
    runs: list = []
    for i in sorted(sites):
        if runs and i == runs[-1][1] + 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    return ",".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs)
