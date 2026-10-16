class DefinitionError(ValueError):
    """A program that the SDK cannot write: what it says is contradictory,
    incomplete, or something the engine would refuse. The message says
    what, and names the process or the option concerned."""
