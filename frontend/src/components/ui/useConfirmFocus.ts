import { useEffect, useRef } from 'react';

/** The button that asked a question in place: focus goes back to it once the question is answered no. */
export function useConfirmFocus(confirming: boolean) {
  const button = useRef<HTMLButtonElement>(null);
  const asked = useRef(false);
  useEffect(() => {
    if (asked.current && !confirming) button.current?.focus();
    asked.current = confirming;
  }, [confirming]);
  return button;
}
