import type { Settings } from '../types';

export function PhoneAccess({ phone }: { phone: Settings['phone'] | null }) {
  if (!phone) return <p className="muted">Checking…</p>;
  if (phone.address) {
    return (
      <div>
        <p>On your iPhone, with Tailscale connected, open this address in Safari, then choose Share › Add to Home Screen:</p>
        <p className="address"><a href={phone.address} target="_blank" rel="noreferrer">{phone.address}</a></p>
      </div>
    );
  }
  return (
    <div>
      <p>
        {phone.tailscale_installed
          ? 'To reach Closet from your phone, run this once on this computer:'
          : 'Phone access uses Tailscale. Once it is installed on this computer and your iPhone, run this once on this computer:'}
      </p>
      <p className="address"><code>{phone.command}</code></p>
      <p className="muted small">The README has the steps.</p>
    </div>
  );
}
