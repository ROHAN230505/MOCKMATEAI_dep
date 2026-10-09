/**
 * The decision behind Section 9.9's `code_panel_update`: given what the server is
 * currently holding and what the panel now looks like, what -- if anything --
 * should go up.
 *
 * Split out of the panel component because this is the part that can be wrong in
 * ways the eye does not catch: a clear re-sent on every keystroke, a snapshot
 * resent unchanged, or the interviewer left holding code the candidate has since
 * un-shared. Section 12.1A gives the socket a budget for low-cost events, so a
 * redundant send is not free.
 */

export interface ShareServerState {
  /** What the candidate's last toggle told the server, as far as this client knows. */
  shared: boolean;
  /** The snapshot the server is holding, or null when it is holding nothing. */
  sent: string | null;
}

export interface SharePanelState {
  shared: boolean;
  code: string;
}

export type ShareAction =
  | { kind: "none" }
  /** Send `{ shared: false }` now -- the server should stop holding the snapshot. */
  | { kind: "clear" }
  /** Send this snapshot once the candidate has been idle for the debounce window. */
  | { kind: "send"; code: string };

export const NONE: ShareAction = { kind: "none" };

export function nextShareAction(server: ShareServerState, panel: SharePanelState): ShareAction {
  if (!panel.shared) {
    // Only on the falling edge. While the toggle stays off the server already
    // holds nothing, so repeating the clear says nothing it does not know.
    return server.shared ? { kind: "clear" } : NONE;
  }
  // Sharing was off and is now on: whatever was typed in the meantime has never
  // been seen, so it goes up even though the text itself may not have changed.
  if (server.shared && panel.code === server.sent) return NONE;
  // An empty panel the server has never been told about is not news. Emptying a
  // panel it *has* been told about is, so that case still sends.
  if (panel.code === "" && server.sent === null) return NONE;
  return { kind: "send", code: panel.code };
}

/** The state the server is in once `action` has been delivered. */
export function applyShareAction(server: ShareServerState, action: ShareAction): ShareServerState {
  switch (action.kind) {
    case "clear":
      return { shared: false, sent: null };
    case "send":
      return { shared: true, sent: action.code };
    default:
      return server;
  }
}
