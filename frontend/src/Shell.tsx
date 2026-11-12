import { useState } from 'react';
import { ArchiveIcon, CloudOffIcon, GearIcon, HangerIcon, PlusIcon } from './components/Icons';
import { Link, parseRoute, usePath, useMediaQuery, WIDE } from './router';
import { useCloset } from './store';
import { ClosetScreen } from './screens/Closet';
import { AddScreen } from './screens/Add';
import { SettingsScreen } from './screens/Settings';
import { ItemDetail } from './screens/ItemDetail';

export function Shell({ version }: { version: string }) {
  const path = usePath();
  const route = parseRoute(path);
  const wide = useMediaQuery(WIDE);
  const { offline } = useCloset();

  let content;
  if (route.name === 'add') content = <AddScreen />;
  else if (route.name === 'settings') content = <SettingsScreen version={version} />;
  else if (route.itemId && !wide) content = <ItemDetail key={route.itemId} id={route.itemId} status={route.status} />;
  else content = <ClosetScreen status={route.status} selectedId={route.itemId} wide={wide} />;

  const section = route.name === 'closet' ? (route.status === 'archived' ? 'archived' : 'closet') : route.name;

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <Sidebar section={section} offline={offline} />
      <div className="shell-main">
        <TopBanners />
        <main id="main" className="shell-content" tabIndex={-1}>{content}</main>
      </div>
      <TabBar section={section} offline={offline} />
    </div>
  );
}

function TopBanners() {
  const { offline, profile, switchProfile, toast } = useCloset();
  const [busy, setBusy] = useState(false);
  return (
    <>
      {offline && (
        <div className="banner banner-offline" role="status">
          <CloudOffIcon />
          <div>
            <strong>Offline: showing your saved closet.</strong>
            <span> Closet on your computer can't be reached, so changes and new photos have to wait. This updates by itself when it's back.</span>
          </div>
        </div>
      )}
      {profile === 'demo' && (
        <div className="ribbon" role="note">
          <span><strong>Demo closet.</strong> Sample clothes to look around with; your own closet is safe.</span>
          <button className="btn btn-small btn-on-accent" disabled={busy || offline} onClick={async () => {
            setBusy(true);
            try {
              await switchProfile('main');
            } catch (e) {
              toast((e as Error).message, 'error');
              setBusy(false);
            }
          }}>Back to my closet</button>
        </div>
      )}
    </>
  );
}

const NAV = [
  { key: 'closet', to: '/', label: 'Closet', Icon: HangerIcon },
  { key: 'archived', to: '/archived', label: 'Archived', Icon: ArchiveIcon },
  { key: 'add', to: '/add', label: 'Add', Icon: PlusIcon },
  { key: 'settings', to: '/settings', label: 'Settings', Icon: GearIcon },
] as const;

function Sidebar({ section, offline }: { section: string; offline: boolean }) {
  return (
    <nav className="sidebar" aria-label="Main">
      <div className="sidebar-brand"><span className="brand-dot"><HangerIcon /></span> Closet</div>
      <ul>
        {NAV.map(({ key, to, label, Icon }) => (
          <li key={key}>
            {key === 'add' && offline ? (
              <span className="nav-link is-disabled" aria-disabled="true" title="Adding photos needs Closet on your computer to be reachable">
                <Icon /> {label}
              </span>
            ) : (
              <Link to={to} className={`nav-link${section === key ? ' is-active' : ''}`} aria-current={section === key ? 'page' : undefined}>
                <Icon /> {label}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}

function TabBar({ section, offline }: { section: string; offline: boolean }) {
  const tabs = NAV.filter((n) => n.key !== 'archived');
  return (
    <nav className="tabbar" aria-label="Main">
      {tabs.map(({ key, to, label, Icon }) => {
        const active = section === key || (key === 'closet' && section === 'archived');
        if (key === 'add' && offline) {
          return (
            <button key={key} className="tab" disabled title="Adding photos needs Closet on your computer to be reachable">
              <Icon /><span>{label}</span>
            </button>
          );
        }
        return (
          <Link key={key} to={to} className={`tab${active ? ' is-active' : ''}`} aria-current={active ? 'page' : undefined}>
            <Icon /><span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
