import type { ProgramProcess } from "../models/process";
import { GENERATOR_SIZE_TEMPLATE, GENERATOR_TASKS_PY_TEMPLATE } from "../models/codeTemplates";
import TasksCodeEditor from "./TasksCodeEditor";

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}

// The configuration dialog of the generator mode: the code that gives the
// number of tasks.
export default function GeneratorConfigEditor({ process, onClose }: Props) {
  return (
    <TasksCodeEditor
      process={process}
      onClose={onClose}
      mode="generator"
      title="Generator Configuration"
      templates={{ bash: GENERATOR_SIZE_TEMPLATE, python: GENERATOR_TASKS_PY_TEMPLATE }}
      pythonHelp={<>
        A Python file that defines <code>tasks(run)</code>, which returns
        the number of tasks, an integer. <code>run.value("-opt")</code>{" "}
        reads an option of the command line, <code>run.process</code> and{" "}
        <code>run.outdir</code> are the name and the output directory of
        the process. Option values can then reference{" "}
        <code>{"${task_idx}"}</code>, the index of the task.
      </>}
      bashHelp={<>
        Bash code returning the number of tasks on stdout. The simplest
        implementation is just a fixed number, e.g. <code>echo 5</code>,
        or a computed one, e.g. <code>echo $n</code>.
      </>}
    />
  );
}
