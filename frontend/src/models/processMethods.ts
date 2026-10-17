import type { MethodCodeKey } from "./process";

// The additional methods of a process that the web UI edits, each a Bash
// function that script generation writes as "<process>_<name>()" around
// the body the user gives, and what the engine does with it (see the table
// of the methods of a process in doc/design_doc_engine.md). The summary is
// what the editor of the method shows; the rules are what the code prompt
// of the method says. Code spans are written between backquotes.
export interface ProcessMethod {
  key: MethodCodeKey;
  name: string;
  // Whether the engine calls it with the options of the task as its
  // arguments; the others take no arguments.
  receivesOptions: boolean;
  summary: string;
  rules: string[];
}

const READ_OPTIONS =
  "It receives the options of the task as its arguments, as the process function does: read one with `read_opt_value_from_func_args \"<label>\" \"$@\"` and test a flag with `read_flag_from_func_args \"<label>\" \"$@\"`.";

// The rules of the skip method that hold whatever its language.
const SKIP_RULES_OF_ANY_LANGUAGE = [
  "A skipped task counts as finished: the output directory of the process is left as it is, neither the process function nor `post` runs, and the processes that depend on it run with the outputs it already has. It is decided task by task.",
  "A process at either end of a FIFO must not be skipped: the two ends run at the same time, and the process at the other end would wait forever for the skipped one to open the FIFO.",
];

export const PROCESS_METHODS: ProcessMethod[] = [
  {
    key: "resetOutfilesCode",
    name: "reset_outfiles",
    receivesOptions: true,
    summary:
      "Runs instead of the engine's default reset of the output directory of the process, right before the process function, with the options of the task as its arguments, read as in the process function (`read_opt_value_from_func_args \"-opt\" \"$@\"`).",
    rules: [
      "The task runs it right before the process function, to remove what an earlier run left, such as a stale output file.",
      READ_OPTIONS,
      "It replaces the default reset, which empties the output directory of the process when the process has a single task and leaves it as it is when its tasks share it.",
      "It does not run when the task is skipped.",
    ],
  },
  {
    key: "postCode",
    name: "post",
    receivesOptions: true,
    summary:
      "Runs right after the process function returns, whether it succeeded or failed, e.g. for post-processing or cleanup, with the options of the task as its arguments, read as in the process function.",
    rules: [
      "The task runs it right after the process function returns, whether the function succeeded or failed.",
      READ_OPTIONS,
      "A `post` that fails fails the task. It does not run when the task is skipped, nor when the process function ends the whole task by calling `exit` or by being killed by a signal.",
    ],
  },
  {
    key: "outdirBasenameCode",
    name: "outdir_basename",
    receivesOptions: false,
    summary:
      "Prints the basename of the output directory of the process, instead of the default, the name of the process. Takes no arguments.",
    rules: [
      "It prints, on its standard output, the basename of the output directory of the process, instead of the name of the process.",
      "It takes no arguments. The engine calls it whenever it needs the directory, so it prints the same name every time and does nothing else.",
    ],
  },
  {
    key: "skipCode",
    name: "skip",
    receivesOptions: true,
    summary:
      "Decides whether a task is skipped: return `0` to skip it and `1` to run it; any other status fails the task. Receives the options of the task as its arguments, read as in the process function.",
    rules: [
      "The task calls it once it has its options, before it resets the output directory of the process. Returning 0 skips the task and returning 1 lets it run; any other status is an error, which fails the task.",
      "End each path of the body with `return 0` or `return 1` rather than with the status of its last command, which can be another one (`grep -q` and `cmp -s` return 2 on an error) and would fail the task.",
      READ_OPTIONS,
      ...SKIP_RULES_OF_ANY_LANGUAGE,
    ],
  },
  {
    key: "condaEnvsCode",
    name: "conda_envs",
    receivesOptions: false,
    summary:
      "Declares the conda environments of the process, e.g. `define_conda_env myenv myenv.yml`. Takes no arguments, and runs once per process whatever its number of tasks.",
    rules: [
      "It declares each conda environment that the process needs with `define_conda_env <name> <file>.yml`, which creates the environment from the file when no environment of that name exists. The file is looked for in the directories of `DEBASHER_YML_DIR` and then among the environment files that DeBasher installs.",
      "It takes no arguments. The engine calls it only for a run prepared with `--conda-support`, once for the process whatever its number of tasks, before any process runs.",
      "It only makes sure that the environments exist: the process function activates one with `conda_activate <name>`.",
    ],
  },
  {
    key: "dockerImgsCode",
    name: "docker_imgs",
    receivesOptions: false,
    summary:
      "Declares the Docker images of the process, e.g. `pull_docker_img \"library/hello-world\"`. Takes no arguments, and runs once per process whatever its number of tasks.",
    rules: [
      "It declares each Docker image that the process needs with `pull_docker_img <image>`, which pulls it when it is not present.",
      "It takes no arguments. The engine calls it only for a run prepared with `--docker-support`, once for the process whatever its number of tasks, before any process runs.",
      "It only makes sure that the images exist: the process function runs a container with `\"${DOCKER}\"`.",
    ],
  },
];

// The rules of a skip file in Python, which replace those of the skip
// method in Bash in its code prompt (see "Python function files" in
// doc/design_doc_engine.md).
export const PYTHON_SKIP_RULES = [
  "The task calls it once it has its options, before it resets the output directory of the process. It returns `True` to skip the task and `False` to run it; anything else, or an exception, is an error, which fails the task with the traceback.",
  "Return `True` or `False` on every path: `None` (a path without `return`), `0`, `1` or any other value fails the task.",
  "`task` holds the options of the task: `task.value(\"<label>\")` is the value of an option (`None` when it is not given or has no value; a second argument gives another default), read as `read_opt_value_from_func_args` reads it, so the value of an input that is a value descriptor is the value it holds; `task.given(\"<label>\")` says whether an option or a flag is given, `task.args` is the whole list, and `task.process` is the name of the process.",
  "The file runs with the Python that DeBasher was configured with, not in the Conda environment or the Docker image of the process, so it imports only what that Python has, on the nodes of the cluster under Slurm; its own directory is first on `sys.path`, so it can import files beside it. A relative path is taken from the directory where `debasher_exec` runs. What it prints goes to the standard error.",
  ...SKIP_RULES_OF_ANY_LANGUAGE,
];

export function processMethod(key: MethodCodeKey): ProcessMethod {
  const method = PROCESS_METHODS.find(m => m.key === key);
  if (!method) {
    throw new Error(`no additional method ${key}`);
  }
  return method;
}
