"""Classes of signalgp-lite operations, as DISHTINY's prq49 runs them."""

GLOBAL_ANCHOR = "Global Anchor"
# signalgp-lite's `Nop<N>` steps the random number engine N times. Engine
# steps per instruction: `Random::P` takes one; RandomFill fills a 4-byte
# float register, one; Draw Random Value builds a random 64-bit tag, two.
RNG_NOPS = {
    "Generate Random Bool": "Nop-1",
    "RandomFill": "Nop-1",
    "Draw Random Value": "Nop-2",
}
# instructions with an effect outside their own core: state writes,
# message sends, global regulator sets and forks
OUTPUTS = frozenset(
    {
        "Write Own State",
        "Add To Own State",
        "Multiply Own State",
        "Send Intra-Cell Message",
        "Send Inter-Cell Message",
        "Broadcast Intra-Cell Message",
        "Set Global Regulator",
        "Adjust Global Regulator",
        "Decay Global Regulator",
        "Set Secondary Global Regulator",
        "Adjust Secondary Global Regulator",
        "Decay Secondary Global Regulator",
        "Fork If",
    }
)


def is_nop(operation: str) -> bool:
    """Tell whether an operation is a nop."""
    return operation.startswith("Nop-")
