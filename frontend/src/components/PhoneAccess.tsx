import { useMemo } from 'react';
import { QUIET, qrMatrix, qrPath } from '../qr';
import type { PhoneInfo } from '../types';

/** The address as a QR code for the iPhone's camera: always black on white, whatever the theme. */
function AddressCode({ address }: { address: string }) {
  const matrix = useMemo(() => qrMatrix(address), [address]);
  const side = matrix.length + 2 * QUIET;
  return (
    <svg className="phone-qr" role="img" aria-label={`QR code of ${address}`} data-payload={address}
      viewBox={`0 0 ${side} ${side}`} shapeRendering="crispEdges">
      <rect width={side} height={side} fill="#fff" />
      <path d={qrPath(matrix)} fill="#000" />
    </svg>
  );
}

/** How to reach Nines from the phone or another computer, on the computer; `phone` is null while it is still being looked up. Once a
 * share reaches Nines it is one line, with the code folded under it; until then, the command to run once. */
export function PhoneAccess({ phone }: { phone: PhoneInfo | null }) {
  if (!phone) return <p className="state-line state-waiting" aria-busy="true"><span className="state-dot" aria-hidden="true" /><span>Looking for Tailscale…</span></p>;
  if (phone.address) {
    return (
      <>
        <p className="state-line state-ready">
          <span className="state-dot" aria-hidden="true" />
          <span>Your phone or another computer can open Nines at <strong className="path" data-testid="phone-address">{phone.address}</strong></span>
        </p>
        <details className="more phone-code" data-testid="phone-code">
          <summary>Show the QR code</summary>
          <p>On your iPhone, with Tailscale connected, point the camera at this code. Then choose Share › Add to Home Screen.</p>
          <AddressCode address={phone.address} />
          <p className="address"><a href={phone.address} target="_blank" rel="noreferrer">{phone.address}</a></p>
          {phone.stop_command && (
            <p className="muted small">
              To stop sharing Nines (anything else you share stays as it is): <code>{phone.stop_command}</code>
            </p>
          )}
        </details>
      </>
    );
  }
  return (
    <>
      {phone.tailscale_installed && phone.running && <p>Nines is not shared with your other devices yet.</p>}
      <p>
        {phone.tailscale_installed
          ? 'To reach Nines from your phone or another computer, run this once on this computer:'
          : 'Your phone or another computer reaches Nines through Tailscale. Once Tailscale is on both, run this once on this computer:'}
      </p>
      <p className="address"><code>{phone.command}</code></p>
      {phone.others_share && (
        <p className="muted small">
          Another app on this computer already uses Tailscale's usual address, so this gives Nines its own, ending in a
          port number such as :8443.
        </p>
      )}
      <p className="muted small">The README has the steps.</p>
    </>
  );
}
