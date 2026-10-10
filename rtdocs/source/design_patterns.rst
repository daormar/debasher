.. _design_patterns:

Design Patterns
===============

The previous section explains the pieces of a program one by one: how a
process defines the options of its tasks, how an array or an option
generator gives it several tasks, and how an option connects to an
output of another process. This section shows how those pieces combine
for the shapes that most programs take: one task per entry of an input,
a chain of steps for each entry, a pool of workers, a step that gathers
the results of every task, and tasks that stream data to each other.
Each pattern says when it applies, how it is written, and which example
of the ``data/programs`` folder shows it whole. A choice comes before
all of them: whether the entries of an input go into a single run, or
each into a run of its own.

One run for all the entries, or one run for each
------------------------------------------------

A program that processes many entries, such as the samples of a
sample sheet, can be written in two ways, which differ in what holds
the state: the run, or the entry.

* **One run for all the entries.** The program has one task for each
  entry, through an array or an option generator, as in the patterns
  below. A single output directory holds every entry, a single status
  says how the whole run goes, and the tasks share the CPUs and the
  memory given to the run. A step that combines the entries, such as a
  joint analysis of every sample or a report over all of them, is one
  more process of the program, and the engine makes it wait for the
  tasks that it reads.
* **One run for each entry.** The program processes a single entry, and
  runs once for each, each run in an output directory of its own, with
  its own status and its own reruns. A failed entry does not affect the
  others and runs again alone, and an entry that comes later is one
  more run, which changes nothing in the runs already done.

One run for all the entries suits a set of entries known in advance
and steps that combine them. One run for each entry suits entries that
are independent of each other, or that arrive over time. To launch the
runs of a batch, ``debasher_exec_batch`` takes a file with one
``debasher_exec`` command per line and runs them, no more than a given
number at the same time:

.. code-block:: bash

    debasher_exec_batch -f runs.txt -m 8

Under the Slurm scheduler the cluster shares out the resources among
the runs by itself. When the entries arrive over time, a launcher node
of a resident program launches one run for each request that it
receives (see :ref:`resident`).

With one run for each entry, a step that combines the results of every
entry is not part of any of them: it runs separately, as a program of
its own, once every run of the batch has ended.

Choosing between an array and an option generator
-------------------------------------------------

A process with several tasks builds their option lists either in its
``define_opts`` method, as an array, or with an option generator, its
``generate_opts_size`` and ``generate_opts`` methods (see
:ref:`implem`). Both give the same tasks; they differ in when the
options are computed:

* ``define_opts`` runs once, when the run is prepared, and the engine
  keeps the option list of every task until the task runs. Use an array
  when the options of a task have to be fixed at that moment, such as
  the files that a directory holds when the run starts; when a task
  depends on the tasks before it, such as batches of lines whose limits
  depend on the size of the previous batches; or when computing the
  options is costly and is best done once.
* An option generator keeps nothing: the engine calls ``generate_opts``
  again whenever it needs the options of a task, inside the task too.
  It suits a large number of tasks, whose option lists are never held
  together, and a process whose number of tasks other processes need,
  since ``generate_opts_size`` gives it at any time. It has to give the
  same option list every time for the same command line and task
  index, so the files that it reads must not change while the run
  lasts.

A rule of thumb follows from the second point: when other processes
depend on the number of tasks of a process, write that process with an
option generator.

One task per entry, and a chain of steps for each entry
-------------------------------------------------------

A typical program processes every entry of an input, such as every
sample of a sample sheet given on the command line, through several
steps, each a process whose task ``i`` reads what the task ``i`` of
the previous step produced. Only the first step reads the sample sheet:
it counts the entries and takes the one of each task, always with the
same rule (here, the lines that are not empty). The sample sheet is a
task shaping option, since no task receives it:

.. code-block:: bash

    align_explain_task_shaping_opts()
    {
        explain_task_shaping_opt "-samples" "<file>" "sample sheet, one sample per line"
    }

    align_generate_opts_size()
    {
        local cmdline=$1
        local samples=$(get_cmdline_opt "${cmdline}" "-samples")
        awk 'NF { n++ } END { print n + 0 }' "${samples}"
    }

    align_generate_opts()
    {
        local cmdline=$1
        local process_outdir=$4
        local task_idx=$5
        local optlist=""

        local samples=$(get_cmdline_opt "${cmdline}" "-samples")
        local sample=$(awk -v i="$((task_idx + 1))" 'NF && ++n == i' "${samples}")
        define_opt "-sample" "${sample}" optlist || return 1
        define_opt_from_process_outdir "-outd" optlist --subdir "${task_idx}" || return 1
        save_opt_list optlist
    }

The next steps do not count the entries again: they ask for the number
of tasks of the step before with ``get_process_num_tasks``, and connect
their task ``i`` to the task ``i`` of that step with
``define_opt_from_proc_task_out``:

.. code-block:: bash

    sort_generate_opts_size()
    {
        get_process_num_tasks "align"
    }

    sort_generate_opts()
    {
        local process_outdir=$4
        local task_idx=$5
        local optlist=""

        define_opt_from_proc_task_out "-ind" "align" "${task_idx}" "-outd" optlist || return 1
        define_opt_from_process_outdir "-outd" optlist --subdir "${task_idx}" || return 1
        save_opt_list optlist
    }

Repeating the count in every step would repeat its rule, and two copies
of a rule can drift apart, as when one skips a header that the other
counts. Each task of ``sort`` reads the directory of the task of
``align`` with the same index, so the engine makes it wait for that
task only, and gives each task a directory of its own (see
:ref:`implem`). The ``debasher_generator_example`` example connects
the tasks of two option generators by index in this way, and the
``debasher_fifo_generator_example`` example also asks for the number of
tasks of the first one.

``get_process_num_tasks`` answers for a process with an option
generator at any time. A process without one (an array, or a process
with a single task) can only ask for the number of tasks of a process
with one, while the run is prepared: this is a second reason to write
the first step with an option generator.

Fan-out to a pool of workers, and fan-in
----------------------------------------

To split a job among a number of workers that the user chooses, the
number of workers is a plain command line option, ``-w``, that every
process of the pattern reads. Since all of them read the same value,
they cannot disagree on it. The ``debasher_dynamic_fanout`` example has
three such processes:

* ``dispatch``, with a single task, splits the job into ``w`` parts.
  It writes them through the options ``-outf0`` to ``-outf<w-1>``,
  which it declares once as the fanout family ``-outf-ith``.
* ``worker``, an array of ``w`` tasks, whose task ``i`` reads
  ``-outf<i>``.
* ``aggregate``, with a single task, reads the result of every task of
  ``worker`` through the options ``-ind0`` to ``-ind<w-1>``, declared
  as the fanout family ``-ind-ith``:

.. code-block:: bash

    aggregate_define_opts()
    {
        local cmdline=$1
        local process_outdir=$4
        local optlist=""

        define_cmdline_opt "$cmdline" "-w" optlist || return 1
        local w=$(read_opt_value_from_line "${cmdline}" "-w")
        for ((i=0; i<w; i++)); do
            define_opt_from_proc_task_out "-ind${i}" "worker" "${i}" "-outd" optlist || return 1
        done
        define_opt "-outf" "${process_outdir}/result.txt" optlist || return 1
        save_opt_list optlist
    }

Each option ``-ind<i>`` holds the path of an output of a task of
``worker``, so ``aggregate`` waits for every task of ``worker`` to
finish. The ``debasher_dynamic_fanout_fifos`` and
``debasher_dynamic_fanout_fifos_gen`` examples stream the parts and the
results through FIFOs instead of files.

Gathering every task of a process
---------------------------------

A step that gathers the results of every task of a process whose number
of tasks comes from the data, such as a report over all the samples of
a sample sheet, has two ways to find them.

The first is a fanout family whose size it asks for with
``get_process_num_tasks``, which requires the process that it gathers
to have an option generator:

.. code-block:: bash

    merge_define_opts()
    {
        local process_outdir=$4
        local optlist=""
        local n i

        n=$(get_process_num_tasks "sort") || return 1
        for ((i=0; i<n; i++)); do
            define_opt_from_proc_task_out "-ind${i}" "sort" "${i}" "-outd" optlist || return 1
        done
        define_opt "-outf" "${process_outdir}/merged.txt" optlist || return 1
        save_opt_list optlist
    }

The process function finds its options ``-ind<i>`` among its
arguments, and the engine makes ``merge`` wait for every task of
``sort``, as in the previous pattern. The ``debasher_shared_subdir_example``
example gathers the tasks of an option generator through a fanout
family too, each of whose tasks writes into a subdirectory of its own
of a shared directory; it reads their number from the same command line
option as the generator.

The second is to read a whole shared directory in which every task
writes into a subdirectory of its own, without knowing how many there
are. The engine infers no dependency from a whole shared directory, so
the gathering process has to declare it in the ``program`` method:

.. code-block:: bash

    add_debasher_process "merge" "cpus=1 mem=32 time=00:01:00" "processdeps=afterok:sort"

Streaming between tasks
-----------------------

When a step can start on the data of the previous one before that step
has finished, the tasks of the two steps can be connected through FIFOs
rather than files: the task ``i`` of the producer declares a FIFO with
``define_fifo_opt``, the task ``i`` of the consumer reads it, and the
engine runs both together. The ``debasher_fifo_generator_example``
example does so with two option generators, the consumer asking for the
number of tasks of the producer.

The FIFOs that the tasks of a process declare through the same option
are read inside the program for every task or for none. A consumer with
fewer tasks than the producer would leave some producer tasks waiting
for ever for a reader, so the engine refuses it when the run is
prepared. A program with FIFOs runs under the built-in scheduler.
