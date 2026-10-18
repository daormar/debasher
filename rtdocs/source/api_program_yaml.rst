.. _program-yaml:

The program.yaml Format
=======================

A program saved by the web interface or written by ``debasher_build``
lives in its home directory as a **topology file**, ``program.yaml``,
and one file per process with its code (see the :ref:`webui` Section
for the home directory and the :ref:`implem_python` Section for the
SDK). The topology file holds what the program is and how it runs:
its processes, their options, their connections and their
specifications. It holds nothing of the machine it is on, such as the
output directory, which the web interface keeps in
``.debasher/local.json``. The module of the program, ``<name>.sh``, is
built from the topology file and the files it names, by a save of the
editor or by ``debasher_build <home directory>``, and is never edited
by hand.

The file is YAML. Every key of the program but ``schema_version`` and
``name`` is optional; an absent key is empty, false or none unless a
default is given below. Inside it, an option needs ``type``, a ``group``
all four of its keys and a ``position`` both ``x`` and ``y``. A key that
the format does not have is an error, so that a misspelt key is reported
rather than ignored. Every plain value is read as a string, since most
values are Bash words; the keys that take a number or a boolean convert
it. The order of the processes and of the options of a process is kept.

The JSON Schema of the format is published with this documentation,
at ``_static/schema/program-1.json``, and ``debasher_build --schema``
prints it. The first line of every file that DeBasher writes names
it, for the editors that check a YAML file against a schema:

.. code-block:: yaml

    # yaml-language-server: $schema=https://debasher.readthedocs.io/en/latest/_static/schema/program-1.json

An example
----------

The topology file of the program ``webui_skip_py``, installed under
``<prefix>/share/debasher/webui_programs``, has two processes, whose
code is in ``value_writer.sh`` and ``value_reader.sh``, and a ``skip``
method written as a Python function in ``value_reader_skip.py``:

.. literalinclude:: ../../data/webui_programs/webui_skip_py/program.yaml
   :language: yaml

The program
-----------

``schema_version``
    The version of the format, an integer, 1 for the one described
    here. A reader reads every version up to its own and refuses a
    newer one. The version is raised when the meaning of a key changes
    or a key goes; a key added with a default does not raise it.

``name``
    The name of the program, which also names its module,
    ``<name>.sh``: letters, digits and underscores, starting with a
    letter or an underscore.

``type``
    ``resident`` for a resident program (see the :ref:`resident`
    Section); absent for a general program.

``description``
    The description of the program.

``preamble``
    Bash run before the functions of the module, such as the
    ``load_debasher_module`` lines of the modules the program uses.

``env``
    The environment variables of the program, name to value. Only
    ``DEBASHER_MOD_DIR`` is read: the directories, separated by colons,
    where the modules that the ``preamble`` loads are looked for. The
    web interface sets it for its runs; a run from the command line
    takes it from the environment.

``shared_dirs``
    The shared directories of the program, a list of names.

``execution``
    The execution options, as "Set execution options" of the editor
    holds them: ``scheduler`` (``BUILTIN``, the default, or ``SLURM``),
    ``builtin_sched_cpus``, ``builtin_sched_mem``, ``dflt_nodes``,
    ``dflt_throttle``, ``rerun_outdated_procs``, ``conda_support``,
    ``docker_support`` and, for a resident program,
    ``snapshot_every_secs``. The web interface turns them into options
    of ``debasher_exec`` when it runs the program (see the :ref:`exec`
    Section), except ``snapshot_every_secs``, which starts
    ``debasher_snapshot_resident --every``; a resident program always
    runs with the builtin scheduler and takes only
    ``builtin_sched_cpus`` and ``builtin_sched_mem``. The module does
    not hold them, so a run from the command line gives its own
    options.

``program_options``
    The options of the command line that a run from the web interface
    is given, label to value, as "Set program options" of the editor
    holds them. As with ``execution``, a run from the command line
    gives its own.

``processes``
    The processes, name to process (see "A process" below).

``seq_processes``
    The sequential processes, name to sequential process (see "A
    sequential process" below).

A process
---------

Where the code of a process is, one of the following, or none, when a
module that the ``preamble`` loads provides the code of a process of
that name:

``code``
    The path of the process file, relative to the topology file, which
    the editor shows and writes as the code of the process. A Bash file
    holds the function named as the process with its helper functions,
    a file of another language the whole script, and the file of a node
    of a resident program the whole class file.

``script``
    The path of a script that the module runs as it is, with the
    interpreter of its extension (the external alias of the
    :ref:`implem_bash` Section). The editor shows it and never writes
    it.

``alias``
    The name of another process, whose code this one runs under its own
    name and options.

The extension of a file says its language: ``.sh`` Bash, ``.py``
Python, ``.pl`` Perl, ``.r`` or ``.R`` R, ``.groovy`` Groovy. The other
keys of a process are:

``alias_opt_map``
    With ``script`` or ``alias``: the name of each option of this
    process to the one that the code expects.

``language``
    The language of the process (``bash``, ``python``, ``perl``, ``r``
    or ``groovy``), given only when the extension of its file does not
    say it.

``description``
    The description of the process.

``mode``
    The mode of the options handler: ``array``, ``generator`` or
    ``manual``; absent for a process with one task.

``tasks``
    The path of the tasks file, the code of the options handler: the
    Bash that builds the array of an ``array`` process or prints the
    number of tasks of a ``generator`` process, or a Python file
    (``.py``) that defines ``tasks(run)`` (see the
    :ref:`tasks_in_python` Section); for a ``manual`` process, the
    whole Bash function that defines its options.

``methods``
    The additional methods, the name of each (``skip``, ``post``,
    ``reset_outfiles``, ``outdir_basename``, ``conda_envs``,
    ``docker_imgs``) to the path of the file with its Bash body. The
    file of ``skip`` may instead be a Python file that defines
    ``skip(task)``.

``conda_envs``
    The Conda environments of the process given as data, the name of
    each to its YAML file. A process gives them this way or as a
    ``conda_envs`` method file, not both.

``docker_imgs``
    The Docker images of the process given as data, a list. A process
    gives them this way or as a ``docker_imgs`` method file, not both.

``specs``
    The specifications of the process in the program, by the names of
    the engine: ``cpus``, ``mem`` (megabytes), ``time``
    (``hh:mm:ss``), ``processdeps`` and ``force``, as
    ``add_debasher_process`` takes them (see the :ref:`prog-def`
    Section), and, for a node of a resident program, its limits
    (``input_log_max_mb``, ``out_backlog_max_mb``,
    ``out_backlog_fail_mb``, ``gil_switch_interval_ms``,
    ``startup_timeout_s``, ``max_concurrent_runs``, ``batch_sched``,
    ``heartbeat_timeout_s``). A process takes the default of each of
    ``cpus``, ``mem`` and ``time`` that it leaves out: 1 CPU, 256
    megabytes, ``01:00:00``, the values that the editor gives a new
    process.

``kind``
    Only in a resident program: ``FBPProcess``, ``ProgramLauncher`` or
    ``DirectoryWatcher`` for a node, after the class of the runtime
    library that it derives from, or ``Supervisor``. The
    ``Supervisor`` takes no ``code``, ``script`` or ``alias``: script
    generation writes its whole class.

``initiator``
    Only in a resident program: whether a round starts at the node.

``group``
    For a process that "Add program" of the editor brought in from
    another program, where it came from (``program``, ``id``,
    ``size``, ``dir``).

``position``
    Where the canvas draws the process, ``{x: ..., y: ...}``. No tool
    but the editor reads it, and a process without one is placed as an
    imported one is.

``options``
    The options, label to option (see "An option" below).

An option
---------

The direction of an option is not written: it comes from its label,
an output being a label that starts with ``-out`` or ``--out``. The
keys of an option are:

``type``
    The data type: ``int``, ``float``, ``string``, ``file``, ``dir``,
    or ``flag`` for an option that takes no value. It is the only key
    that every option gives.

``description``
    The description of the option.

``value``
    The value of the option, a Bash word that the engine expands when
    the option is defined, such as ``${process_outdir}/out.txt``; for a
    FIFO, the name of the FIFO; for a shared directory, its name; for
    an option taken from the specifications, the name of the
    specification.

``channel``
    How the option is delivered: ``none`` (the default), ``fifo``,
    ``value_desc``, ``shared_dir`` or ``process_outdir``.

``subpath``
    With ``channel: shared_dir`` or ``channel: process_outdir``: a
    shared subdirectory or a task subdirectory below the directory.

``mirror``
    With ``channel: fifo``: whether a copy of what is written is kept
    for ``debasher_get_fifo_mirror``.

``fifo_tag``
    ``external`` for an external input of a resident program, written
    from outside the program.

``cmdline``
    Whether the value comes from the command line of the run.

``mandatory``
    Whether a command line option has to be given. A command line
    option that is not a flag is mandatory unless it says
    ``mandatory: false``.

``shaping``
    Whether a command line option is a task shaping option, read by
    the options handler only.

``from_spec``
    Whether the value is a specification of the process (``value``
    names it, such as ``cpus``).

``count_source``
    For a family of options, a label ending in ``-ith``: the label of
    the option of the same process that counts it. Without it, the
    family is counted by the tasks of the process at the other end.

``from``
    For a connected input: what it reads, ``<process>.<label>``, or a
    list of them for a fan-in. The connections of a program are the
    ``from`` of its inputs; the file has no other list of them.

``display``
    ``label`` for an input whose connections the canvas draws as label
    edges, ``line`` (the default) for lines. No tool but the editor
    reads it.

A sequential process
--------------------

A sequential process (see the :ref:`seq_processes` Section)
takes ``description``, ``code``, ``script``, ``alias``,
``alias_opt_map``, ``language`` and ``group`` as a process does, and
``specs`` with ``cpus``, ``mem``, ``time`` and ``sched``, the
scheduler of its steps (``BUILTIN``, the default, or ``SLURM``). Its
``cpus``, ``mem`` and ``time`` are optional and have no default.
