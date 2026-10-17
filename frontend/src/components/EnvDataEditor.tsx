import type { CondaEnv } from "../models/process";

// The Conda environments or the Docker images of a process given as data,
// from which script generation writes one define_conda_env or
// pull_docker_img per entry: a row per entry, with a name and a YAML file
// for an environment, an image alone for Docker.
export type EnvData =
  | { kind: "conda"; rows: CondaEnv[] }
  | { kind: "docker"; rows: string[] };

interface Props {
  data: EnvData;
  onChange: (data: EnvData) => void;
}

export default function EnvDataEditor({ data, onChange }: Props) {

  const rows = data.kind === "conda"
    ? data.rows.map(env => [env.name, env.file])
    : data.rows.map(img => [img]);

  const columns = data.kind === "conda" ? ["Name", "YAML file"] : ["Image"];

  function changed(next: string[][]) {
    onChange(
      data.kind === "conda"
        ? { kind: "conda", rows: next.map(([name, file]) => ({ name, file })) }
        : { kind: "docker", rows: next.map(([img]) => img) }
    );
  }

  return (

    <div style={{ display: "flex", flexDirection: "column", gap: 4, minHeight: 200 }}>

      {rows.map((row, i) => (
        <div key={i} style={{ display: "flex", gap: 4 }}>
          {row.map((cell, j) => (
            <input
              key={j}
              value={cell}
              placeholder={data.kind === "conda" ? ["py27", "py27.yml"][j] : "ubuntu:24.04"}
              aria-label={columns[j]}
              onChange={event => changed(rows.map((r, k) => k === i ? r.map((c, l) => l === j ? event.target.value : c) : r))}
              style={{ flex: 1 }}
            />
          ))}
          <button onClick={() => changed(rows.filter((_, k) => k !== i))}>
            Remove
          </button>
        </div>
      ))}

      <div>
        <button onClick={() => changed([...rows, columns.map(() => "")])}>
          Add {data.kind === "conda" ? "environment" : "image"}
        </button>
      </div>

    </div>

  );

}

// Whether a row of `data` lacks one of its fields, which the editor does
// not save.
export function hasIncompleteRow(data: EnvData): boolean {
  return data.kind === "conda"
    ? data.rows.some(env => env.name.trim() === "" || env.file.trim() === "")
    : data.rows.some(img => img.trim() === "");
}

// The entries of `data`, trimmed.
export function trimmedRows(data: EnvData): EnvData {
  return data.kind === "conda"
    ? { kind: "conda", rows: data.rows.map(env => ({ name: env.name.trim(), file: env.file.trim() })) }
    : { kind: "docker", rows: data.rows.map(img => img.trim()) };
}
