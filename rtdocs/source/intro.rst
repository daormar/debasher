Introduction
============

Bash, born out of the Unix shell tradition, is a particularly valuable
asset as the glue that orchestrates the execution of a set of computer
programs. As a powerful and versatile command-line interpreter, Bash
excels in automating repetitive tasks, stringing together disparate
programs, and facilitating the flow of data between them. These
abilities make Bash a particularly interesting option to implement
computer pipelines or workflows, which typically combine programs
written in different programming languages.

When implementing pipelines, it is necessary to consider not only
standard software engineering principles such as modularity or code
reusability, but also specific challenges inherent to pipeline
design. One example of these challenges is the optimal use of hardware
resources. A pipeline involves the execution of a series of steps where
parallelism can be exploited depending on the data dependencies between
such steps. This observation has motivated a growing interest in the
application of data flow programming paradigms as opposed to the
traditional control flow approach.

In spite of the fact that Bash incorporates features useful to enable
parallel process execution, it is still focused on the sequence of
operations to be executed and the flow of control between the differents
parts of a program. This makes the application of Bash difficult in
scenarios where data flow programming is more appropriate.

DeBasher is a flow-based programming extension for Bash that allows to
implement general programs escaping the traditional control flow
paradigm. `Flow-based programming
<https://en.wikipedia.org/wiki/Flow-based_programming>`_ combines `data
flow programming <https://en.wikipedia.org/wiki/Dataflow_programming>`_
with `component-based software engineering
<https://en.wikipedia.org/wiki/Component-based_software_engineering>`_,
resulting in programs that naturally exploit process parallelism and at
the same time optimize modularity and code reuse.
