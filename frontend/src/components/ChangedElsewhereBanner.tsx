interface BannerAction {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}

interface Props {
  message: string;
  actions: BannerAction[];
  error?: string | null;
}

// The banner that says that someone else saved what the user is editing, with
// what the user can do about it: the one of the program under the toolbar, and
// the one above a file of the program files panel.
export default function ChangedElsewhereBanner({ message, actions, error = null }: Props) {

  return (

    <div
      role="alert"
      style={{
        padding: "6px 12px",
        background: "#fff4ce",
        borderBottom: "1px solid #e0c97a",
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 8,
        fontSize: 13,
      }}
    >

      <span style={{ flex: 1 }}>
        {message}
        {error && <span style={{ color: "#b00020" }}> {error}</span>}
      </span>

      {actions.map(action => (
        <button
          key={action.label}
          onClick={action.onClick}
          disabled={action.disabled}
        >
          {action.label}
        </button>
      ))}

    </div>

  );

}
