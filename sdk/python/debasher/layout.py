"""
Where the processes of a program go on the canvas of the web UI when
nobody chose a position for them: the rule of the editor for an imported
program (layoutProcesses in frontend/src/models/programLayout.ts), ported
as it is so that a program written with the SDK opens as one imported
from a module would.

Processes are placed in layers by the depth of their connections, a
process that feeds another's input above it, so that the edges run down
the canvas. A layer comes from longest-path relaxation over the
connections, with the passes capped at the number of processes: DeBasher
allows cycles between processes, around which the relaxation would never
end, and that many passes reach the fixpoint of the acyclic part of the
graph and leave a cycle with some layering. A self-loop says nothing
about the order of two processes and is left out. Processes that share a
layer go side by side, left to right in their order in the program.
"""

START_X = 100.0
START_Y = 100.0
X_SPACING = 220.0
Y_SPACING = 160.0


def layout(names: list[str], connections: list[tuple[str, str]]) -> dict[str, tuple[float, float]]:
    """
    The position of each process, by name, given the names in their order
    in the program and the connections as (source process, target process)
    pairs.
    """
    layer = {name: 0 for name in names}
    for _ in range(len(names)):
        changed = False
        for source, target in connections:
            if source not in layer or target not in layer or source == target:
                continue
            if layer[source] + 1 > layer[target]:
                layer[target] = layer[source] + 1
                changed = True
        if not changed:
            break
    next_x_by_layer: dict[int, float] = {}
    positions = {}
    for name in names:
        process_layer = layer[name]
        x = next_x_by_layer.get(process_layer, START_X)
        next_x_by_layer[process_layer] = x + X_SPACING
        positions[name] = (x, START_Y + process_layer * Y_SPACING)
    return positions
