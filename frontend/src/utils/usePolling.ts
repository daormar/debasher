import { useEffect, useRef } from "react";

interface PollingOptions {
  intervalMs: number;
  // Whether to poll at all.
  enabled: boolean;
  // Polling starts over, with a poll in flight cancelled, when it changes.
  resetKey?: string;
}

/**
 * Calls `poll` every `intervalMs` while `enabled` holds and the page is
 * visible. A poll never starts while the one before is in flight, however
 * long it takes, and `isCancelled` tells a poll in flight that polling
 * stopped or started over, so that it changes nothing. The latest `poll` is
 * the one called, so a new one on every render does not restart the polling.
 * A poll that fails is left to the next one.
 */
export function usePolling(
  poll: (isCancelled: () => boolean) => Promise<void>,
  { intervalMs, enabled, resetKey = "" }: PollingOptions
) {

  const pollRef =
    useRef(poll);

  useEffect(() => {
    pollRef.current = poll;
  });

  useEffect(() => {

    if (!enabled) {
      return;
    }

    let cancelled = false;
    let inFlight = false;

    async function tick() {
      if (inFlight || document.hidden) {
        return;
      }
      inFlight = true;
      try {
        await pollRef.current(() => cancelled);
      } catch {
        // The next poll tries again.
      } finally {
        inFlight = false;
      }
    }

    const interval = window.setInterval(tick, intervalMs);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };

  }, [enabled, intervalMs, resetKey]);

}
