import { useEffect } from "react";
import type { RefObject } from "react";

// Calls `onOutside` when a mouse button is pressed outside the element of
// `ref`, while `active` holds: what closes a menu that is open.
export function useClickOutside(
  ref: RefObject<HTMLElement | null>,
  active: boolean,
  onOutside: () => void,
) {

  useEffect(() => {

    if (!active) {
      return;
    }

    function handleClickOutside(event: MouseEvent) {
      if (
        ref.current &&
        !ref.current.contains(event.target as Node)
      ) {
        onOutside();
      }
    }

    document.addEventListener("mousedown", handleClickOutside, true);

    return () =>
      document.removeEventListener("mousedown", handleClickOutside, true);

  }, [ref, active, onOutside]);

}
