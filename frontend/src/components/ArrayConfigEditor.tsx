import type { ProgramProcess } from "../models/process";
import { ARRAY_TASKS_PY_TEMPLATE } from "../models/codeTemplates";
import TasksCodeEditor from "./TasksCodeEditor";

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}

// The configuration dialog of the array mode: the code that builds the
// array, one element per task.
export default function ArrayConfigEditor({ process, onClose }: Props) {
  return (
    <TasksCodeEditor
      process={process}
      onClose={onClose}
      mode="array"
      title="Array Configuration"
      templates={{ bash: "", python: ARRAY_TASKS_PY_TEMPLATE }}
      pythonHelp={<>
        A Python file that defines <code>tasks(run)</code>, which returns
        the elements of the array, one per task: a list of strings,
        numbers or paths. <code>run.value("-opt")</code> reads an option
        of the command line, <code>run.process</code> and{" "}
        <code>run.outdir</code> are the name and the output directory of
        the process. Option values below can then reference{" "}
        <code>{"${array[$task_idx]}"}</code> (the current element) or{" "}
        <code>{"${task_idx}"}</code> (its index).
      </>}
      bashHelp={<>
        Add your code below. Bash code that builds an array named{" "}
        <code>array</code>, run once before the per-task loop. Option
        values below can then reference <code>{"${array[$task_idx]}"}</code>{" "}
        (the current element) or <code>{"${task_idx}"}</code> (its index).
      </>}
    />
  );
}
