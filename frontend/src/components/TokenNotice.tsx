import { useState, useSyncExternalStore } from "react";

import { hasToken, isTokenRefused, subscribeTokenRefused } from "../api/apiFetch";
import { checkToken } from "../api/webuiApi";

// Shown over every screen while the tab has no token that the backend takes:
// none, as when the page was opened without the address that debasher_webui
// printed, or a token that the backend no longer knows, once it restarted with
// another. It leaves the tab as it is, unsaved changes included. Opening the
// address in this tab changes only its fragment, which loads nothing again,
// and the tab takes the token (see main.tsx); "Retry" asks the backend again,
// with the token that another tab may have stored meanwhile.
export default function TokenNotice() {

  const refused =
    useSyncExternalStore(subscribeTokenRefused, isTokenRefused);

  const [pending, setPending] = useState(false);

  if (!refused) {
    return null;
  }

  async function retry() {
    setPending(true);
    try {
      await checkToken();
    } finally {
      setPending(false);
    }
  }

  const message = hasToken()
    ? "The backend no longer knows this tab: it restarted with another token. " +
      "Open the address that debasher_webui printed (the one that ends in #token=...), " +
      "in this tab, which keeps its unsaved changes, or in another one and then retry here."
    : "This page has no token of the backend. Open the address that debasher_webui " +
      "printed when it started, the one that ends in #token=...";

  return (

    <div
      role="alert"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 2000,
        padding: "8px 12px",
        background: "#fde7e9",
        borderBottom: "1px solid #d9a3a9",
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: 13,
      }}
    >

      <span style={{ flex: 1 }}>
        {message}
      </span>

      <button onClick={retry} disabled={pending}>
        Retry
      </button>

    </div>

  );

}
