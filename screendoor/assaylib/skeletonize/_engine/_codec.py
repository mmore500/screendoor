"""Compact, readable genotype encoding: sorted site ranges like "0-5,9"."""


def encode_sites(sites) -> str:
    runs: list = []
    for i in sorted(sites):
        if runs and i == runs[-1][1] + 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    return ",".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs)


def decode_sites(text: str) -> frozenset:
    sites: set = set()
    for part in filter(None, text.split(",")):
        a, _, b = part.partition("-")
        sites.update(range(int(a), int(b or a) + 1))
    return frozenset(sites)
