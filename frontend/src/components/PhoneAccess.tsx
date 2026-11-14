import { useMemo } from 'react';
import { QUIET, qrMatrix, qrPath } from '../qr';
import type { Settings } from '../types';

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

export function PhoneAccess({ phone }: { phone: Settings['phone'] | null }) {
  if (!phone) return <p className="muted">Checking…</p>;
  if (phone.address) {
    return (
      <div>
        <p>On your iPhone, with Tailscale connected, point the camera at this code, or open the address below in Safari. Then choose Share › Add to Home Screen:</p>
        <AddressCode address={phone.address} />
        <p className="address"><a href={phone.address} target="_blank" rel="noreferrer">{phone.address}</a></p>
        {phone.stop_command && (
          <p className="muted small">
            To stop sharing Closet (anything else you share stays as it is): <code>{phone.stop_command}</code>
          </p>
        )}
      </div>
    );
  }
  return (
    <div>
      {phone.tailscale_installed && phone.running && <p>Closet is not shared with your phone yet.</p>}
      <p>
        {phone.tailscale_installed
          ? 'To reach Closet from your phone, run this once on this computer:'
          : 'Phone access uses Tailscale. Once it is installed on this computer and your iPhone, run this once on this computer:'}
      </p>
      <p className="address"><code>{phone.command}</code></p>
      {phone.others_share && (
        <p className="muted small">
          Another app on this computer already uses Tailscale's usual address, so this gives Closet its own, ending in a
          port number such as :8443.
        </p>
      )}
      <p className="muted small">The README has the steps.</p>
    </div>
  );
}
