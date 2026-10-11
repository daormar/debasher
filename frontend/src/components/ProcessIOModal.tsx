import type { FanoutFamily, OptionChannel, ProgramOption } from "../models/option";

interface Props {
  processName: string;
  // Every option except fromProcessSpec ones — a resource spec (cpus,
  // mem, ...), not a process input/output (see the "Specifications"
  // inspector section for those). See ProgramCanvas's fetchProcessIO
  // for why this isn't filtered by commandLine instead.
  options: ProgramOption[];
  // {label: resolved value}, from the process's own ".opts" file (see
  // getProcessResolvedOptions) — empty when the program hasn't been
  // run yet, in which case each option falls back to its own
  // (possibly unresolved, e.g. a "[proc;opt]" connection sentinel or a
  // shared-dir/fifo name rather than its real path) model value.
  resolvedValues: Record<string, string>;
  // Fanout/fanin option families too large to expand inline (see
  // ProgramCanvas's expandFanoutOptions/MAX_FANOUT_INLINE) — shown as
  // their own "Pick index" row instead.
  families: FanoutFamily[];
  // The option channel through which the data of each option gets to the
  // process (see deliveryChannel), by option id, as ProgramCanvas's
  // fetchProcessIO found it: a connected input's own channel is "none",
  // whatever the channel of the output it reads.
  deliveryChannels: Map<string, OptionChannel>;
  isViewPending: boolean;
  onViewPath: (option: ProgramOption, resolvedValue: string) => void;
  onPickFanoutIndex: (family: FanoutFamily) => void;
  onClose: () => void;
}

// The option channel through which the data of a row arrives: that of its
// option, or, for a row of a fanout family, whose id is "<family id>:<index>"
// (see ProgramCanvas's expandFanoutOptions and
// handleFanoutIndexPickerConfirm), that of its family.
function rowChannel(option: ProgramOption, deliveryChannels: Map<string, OptionChannel>): OptionChannel {
  return deliveryChannels.get(option.id)
    ?? deliveryChannels.get(option.id.replace(/:\d+$/, ""))
    ?? option.channel;
}

// A fifo's value is only ever shown as a path (no content view, for
// now): reading a fifo isn't safe the way reading a regular file is.
// Anything else backed by a real path on disk gets a "View" button, wired
// up in ProgramCanvas to /api/execution/inspect-path: a "file" or "dir"
// option, a "shared_dir" or "process_outdir" option, which always names a
// directory, and an option written or read through a value descriptor,
// a regular file that holds the value, whatever the data type of that
// value.
function optionHasPathButton(option: ProgramOption, deliveryChannels: Map<string, OptionChannel>): boolean {
  const channel = rowChannel(option, deliveryChannels);
  if (channel === "fifo") {
    return false;
  }
  return option.dataType === "file" || option.dataType === "dir" ||
    channel === "value_desc" || channel === "shared_dir" || channel === "process_outdir";
}

// Mirrors ProgramOptionsEditor's ("Run" > "Set program options") own
// per-option layout — label above value — for a consistent look
// between the two option-inspecting modals.
function OptionRow({
  option,
  resolvedValue,
  deliveryChannels,
  isViewPending,
  onViewPath,
}: {
  option: ProgramOption;
  resolvedValue: string;
  deliveryChannels: Map<string, OptionChannel>;
  isViewPending: boolean;
  onViewPath: (option: ProgramOption, resolvedValue: string) => void;
}) {

  return (

    <div key={option.id}>

      <label style={{ fontSize: 14 }}>
        {option.label}
      </label>

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>

        <span
          style={{
            flex: 1,
            fontFamily: "ui-monospace, Consolas, monospace",
            fontSize: 13,
            overflowWrap: "anywhere",
            color: resolvedValue ? "inherit" : "#888",
          }}
        >
          {resolvedValue || "(no value)"}
        </span>

        {optionHasPathButton(option, deliveryChannels) && resolvedValue && (
          <button
            onClick={() => onViewPath(option, resolvedValue)}
            disabled={isViewPending}
          >
            View
          </button>
        )}

      </div>

      {option.description && (
        <div style={{ fontSize: 12, color: "#888" }}>
          {option.description}
        </div>
      )}

    </div>

  );

}

// A fanout/fanin family too large to expand inline — same layout as
// OptionRow, but the value slot is a count plus a "Pick index" button
// (opening a ProcessTaskPicker, see ProgramCanvas's fanoutIndexPicker)
// instead of a resolved value.
function FanoutFamilyRow({
  family,
  onPickFanoutIndex,
}: {
  family: FanoutFamily;
  onPickFanoutIndex: (family: FanoutFamily) => void;
}) {

  return (

    <div key={family.option.id}>

      <label style={{ fontSize: 14 }}>
        {family.option.label}
      </label>

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>

        <span style={{ flex: 1, fontSize: 13, color: "#888" }}>
          {family.count.toLocaleString()} options ("{family.baseLabel}0" to "{family.baseLabel}{family.count - 1}")
        </span>

        <button onClick={() => onPickFanoutIndex(family)}>
          Pick index
        </button>

      </div>

      {family.option.description && (
        <div style={{ fontSize: 12, color: "#888" }}>
          {family.option.description}
        </div>
      )}

    </div>

  );

}

function OptionSection({
  title,
  options,
  families,
  resolvedValues,
  deliveryChannels,
  isViewPending,
  onViewPath,
  onPickFanoutIndex,
}: {
  title: string;
  options: ProgramOption[];
  families: FanoutFamily[];
  resolvedValues: Record<string, string>;
  deliveryChannels: Map<string, OptionChannel>;
  isViewPending: boolean;
  onViewPath: (option: ProgramOption, resolvedValue: string) => void;
  onPickFanoutIndex: (family: FanoutFamily) => void;
}) {

  if (options.length === 0 && families.length === 0) {
    return null;
  }

  return (

    <>

      <h4 style={{ margin: "8px 0 0" }}>
        {title}
      </h4>

      {options.map(option => (
        <OptionRow
          key={option.id}
          option={option}
          resolvedValue={resolvedValues[option.label] ?? option.value}
          deliveryChannels={deliveryChannels}
          isViewPending={isViewPending}
          onViewPath={onViewPath}
        />
      ))}

      {families.map(family => (
        <FanoutFamilyRow
          key={family.option.id}
          family={family}
          onPickFanoutIndex={onPickFanoutIndex}
        />
      ))}

    </>

  );

}

export default function ProcessIOModal({
  processName,
  options,
  resolvedValues,
  families,
  deliveryChannels,
  isViewPending,
  onViewPath,
  onPickFanoutIndex,
  onClose,
}: Props) {

  const inputs = options.filter(o => o.direction === "input");
  const outputs = options.filter(o => o.direction === "output");

  const inputFamilies = families.filter(f => f.option.direction === "input");
  const outputFamilies = families.filter(f => f.option.direction === "output");

  return (

    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >

      <div
        style={{
          width: "60%",
          maxWidth: 480,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          {processName}: inputs and outputs
        </h3>

        <div
          style={{
            maxHeight: "60vh",
            overflow: "auto",
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >

          {inputs.length === 0 && outputs.length === 0 &&
           inputFamilies.length === 0 && outputFamilies.length === 0 ? (

            <p style={{ fontSize: 14, color: "#666" }}>
              No command-line options declared.
            </p>

          ) : (

            <>

              <OptionSection
                title="Input"
                options={inputs}
                families={inputFamilies}
                resolvedValues={resolvedValues}
                deliveryChannels={deliveryChannels}
                isViewPending={isViewPending}
                onViewPath={onViewPath}
                onPickFanoutIndex={onPickFanoutIndex}
              />

              <OptionSection
                title="Output"
                options={outputs}
                families={outputFamilies}
                resolvedValues={resolvedValues}
                deliveryChannels={deliveryChannels}
                isViewPending={isViewPending}
                onViewPath={onViewPath}
                onPickFanoutIndex={onPickFanoutIndex}
              />

            </>

          )}

        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onClose}>
            Close
          </button>

        </div>

      </div>

    </div>

  );

}
