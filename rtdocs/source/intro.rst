Introduction
============

Bash, born out of the Unix shell tradition, serves as the glue that
seamlessly orchestrates the execution of a set of computer programs. As
a powerful and versatile command-line interpreter, Bash excels in
automating repetitive tasks, stringing together disparate programs, and
facilitating the flow of data between them. These abilities make Bash a
particularly interesting option when implementing computer pipelines or
workflows, which typically combine programs written in different
programming languages.

When implementing pipelines in computer systems, it is necessary to
consider not only standard software engineering principles like
modularity and reusability but also specific challenges inherent to
pipeline design. One example of such challenges is the optimal use of
hardware resources. A pipeline involves the execution of a series of
steps where parallelism can be exploited depending on its data
dependencies.

..
   In spite of the fact that Bash incorporates features
