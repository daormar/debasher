import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { hasToken, markTokenRefused, takeTokenFromAddress } from "./api/apiFetch";
import { checkToken } from "./api/webuiApi";

import "./styles/app.css";
import "@xyflow/react/dist/style.css";

// The address that debasher_webui prints brings the token of the backend in
// its fragment; a page that has none says how to get it before any request.
takeTokenFromAddress();
if (!hasToken()) {
  markTokenRefused();
}
// Opening the address with the token in a tab that is already open changes
// only the fragment, which loads nothing again: the tab takes the token as it
// is, unsaved changes included.
window.addEventListener("hashchange", () => {
  if (takeTokenFromAddress()) {
    checkToken();
  }
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
