import { createRoot, type Root } from "react-dom/client";
import { OverlayApp } from "../components/OverlayApp";
import { HOST_ELEMENT_ID } from "../types/messages";
import cssText from "../styles/overlay.css?inline";

type MountState = {
  host: HTMLElement;
  shadow: ShadowRoot;
  root: Root;
  mountNode: HTMLElement;
};

let state: MountState | null = null;

function ensureHost(): MountState {
  if (state) return state;

  const existing = document.getElementById(HOST_ELEMENT_ID);
  existing?.remove();

  const host = document.createElement("div");
  host.id = HOST_ELEMENT_ID;
  host.setAttribute("data-interview-integrity", "meet-overlay-v1");
  // Open Shadow DOM (approved): inspectable, still isolates page CSS.
  const shadow = host.attachShadow({ mode: "open" });

  const style = document.createElement("style");
  style.textContent = cssText;
  shadow.appendChild(style);

  const mountNode = document.createElement("div");
  mountNode.setAttribute("data-ii-react-root", "true");
  shadow.appendChild(mountNode);

  document.documentElement.appendChild(host);

  const root = createRoot(mountNode);
  state = { host, shadow, root, mountNode };
  return state;
}

export function isOverlayMounted(): boolean {
  return state != null && document.getElementById(HOST_ELEMENT_ID) != null;
}

export function mountOverlay(): void {
  const current = ensureHost();
  current.root.render(
    <OverlayApp
      onClose={() => {
        unmountOverlay();
      }}
    />,
  );
}

export function unmountOverlay(): void {
  if (!state) return;
  const { root, host } = state;
  state = null;
  root.unmount();
  host.remove();
}
