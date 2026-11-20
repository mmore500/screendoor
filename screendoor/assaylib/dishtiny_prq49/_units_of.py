from ._ops import GLOBAL_ANCHOR, OUTPUTS, is_nop

KINDS = ("modules", "outputs", "calculations", "all")


def units_of(
    kind: str, operations: list[str], knockout: frozenset[int] = frozenset()
) -> tuple[list[list[int]], list[str]]:
    """List the knockout units of one kind in a program.

    A position is live if it is not in `knockout` and not a nop. A module
    runs from a live global anchor to the next; live instructions ahead of
    the first belong to the last module, as the program wraps around.

    * `modules`: the live content of each module, less its global anchor.
    * `outputs`: each live instruction with an effect outside its core.
    * `calculations`: each other live instruction that is not a global
      anchor: arithmetic, logic, constants and random draws, and with
      them local anchors, inputs and control flow.
    * `all`: each live instruction, global anchors among them.

    Parameters
    ----------
    kind : str
        The kind of unit.
    operations : list of str
        The program's operations, in order.
    knockout : frozenset of int, default frozenset()
        Positions knocked out so far.

    Returns
    -------
    units : list of list of int
        Each unit's positions, in program order.
    labels : list of str
        A name for each unit.

    Raises
    ------
    ValueError
        If `kind` is unknown.
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    live = [
        p
        for p, o in enumerate(operations)
        if p not in knockout and not is_nop(o)
    ]
    if kind == "modules":
        anchors = [p for p in live if operations[p] == GLOBAL_ANCHOR]
        # with no anchor, the whole program is one module
        contents: dict = {a: [] for a in anchors or live[:1]}
        for p in live:
            if operations[p] != GLOBAL_ANCHOR or not anchors:
                # the last anchor at or before p, wrapping around
                before = [a for a in contents if a <= p]
                contents[max(before, default=max(contents))].append(p)
        full = {a: u for a, u in contents.items() if u}
        return (
            list(full.values()),
            [f"module@{a}({len(u)})" for a, u in full.items()],
        )
    if kind == "outputs":
        chosen = [p for p in live if operations[p] in OUTPUTS]
    elif kind == "calculations":
        chosen = [
            p for p in live if operations[p] not in OUTPUTS | {GLOBAL_ANCHOR}
        ]
    else:
        chosen = live
    return [[p] for p in chosen], [f"{operations[p]}@{p}" for p in chosen]
