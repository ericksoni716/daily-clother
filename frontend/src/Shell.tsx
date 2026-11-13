import { useState } from 'react';
import { ArchiveIcon, CloudOffIcon, GearIcon, HangerIcon, PlusIcon, SuitcaseIcon, SunIcon } from './components/Icons';
import { useLanding } from './landing';
import { Link, parseRoute, usePath, useMediaQuery, WIDE } from './router';
import { useCloset } from './store';
import { ClosetScreen } from './screens/Closet';
import { AddScreen } from './screens/Add';
import { SettingsScreen } from './screens/Settings';
import { ItemDetail } from './screens/ItemDetail';
import { TodayScreen } from './screens/Today';
import { TripsScreen } from './screens/Trips';
import { InsightsScreen } from './screens/Insights';
import { WornScreen } from './screens/Worn';
import { ReviewBadge, ReviewIcon, ReviewScreen, useReviewCount } from './screens/Review';
import { BagIcon, MissingScreen } from './screens/Missing';

export function Shell({ version }: { version: string }) {
  const path = usePath();
  const route = parseRoute(path);
  const wide = useMediaQuery(WIDE);
  const { offline, items } = useCloset();
  useLanding(path, items.active);
  const toReview = useReviewCount();

  let content;
  if (route.name === 'today') content = <TodayScreen itemId={route.itemId} wide={wide} />;
  else if (route.name === 'worn') content = <WornScreen />;
  else if (route.name === 'missing') content = <MissingScreen itemId={route.itemId} wide={wide} />;
  else if (route.name === 'add') content = <AddScreen />;
  else if (route.name === 'settings') content = <SettingsScreen version={version} />;
  else if (route.name === 'insights') content = <InsightsScreen />;
  else if (route.name === 'review') content = <ReviewScreen />;
  else if (route.name === 'trips') content = <TripsScreen tripId={route.tripId} />;
  else if (route.itemId && !wide) content = <ItemDetail key={route.itemId} id={route.itemId} status={route.status} />;
  else content = <ClosetScreen status={route.status} selectedId={route.itemId} wide={wide} />;

  // Insights is reached from the Closet screen and Worn from Today, so those stay the highlighted sections
  const section = route.name === 'closet' ? (route.status === 'archived' ? 'archived' : 'closet')
    : route.name === 'insights' ? 'closet' : route.name === 'worn' ? 'today' : route.name;

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <Sidebar section={section} offline={offline} toReview={toReview} />
      <div className="shell-main">
        <TopBanners />
        <main id="main" className="shell-content" tabIndex={-1}>{content}</main>
      </div>
      <TabBar section={section} offline={offline} toReview={toReview} />
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
          <span><strong>Demo closet</strong><span className="ribbon-more"> · sample clothes to look around with. Your own closet is safe.</span></span>
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
  { key: 'today', to: '/today', label: 'Today', Icon: SunIcon },
  { key: 'closet', to: '/', label: 'Closet', Icon: HangerIcon },
  { key: 'archived', to: '/archived', label: 'Archived', Icon: ArchiveIcon },
  { key: 'trips', to: '/trips', label: 'Trips', Icon: SuitcaseIcon },
  { key: 'review', to: '/review', label: 'Review', Icon: ReviewIcon },
  { key: 'missing', to: '/missing', label: "What's missing", short: 'Missing', Icon: BagIcon },
  { key: 'add', to: '/add', label: 'Add', Icon: PlusIcon },
  { key: 'settings', to: '/settings', label: 'Settings', Icon: GearIcon },
] as const;

function Sidebar({ section, offline, toReview }: { section: string; offline: boolean; toReview: number | null }) {
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
                <Icon /> {label}{key === 'review' && <ReviewBadge count={toReview} />}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}

function TabBar({ section, offline, toReview }: { section: string; offline: boolean; toReview: number | null }) {
  // the bottom bar is full: Trips is reached from Today and Settings on the phone
  const tabs = NAV.filter((n) => n.key !== 'archived' && n.key !== 'trips');
  return (
    <nav className="tabbar" aria-label="Main">
      {tabs.map((n) => {
        const { key, to, Icon } = n;
        const label = 'short' in n ? n.short : n.label;
        const active = section === key || (key === 'closet' && section === 'archived') || (key === 'today' && section === 'trips');
        if (key === 'add' && offline) {
          return (
            <button key={key} className="tab" disabled title="Adding photos needs Closet on your computer to be reachable">
              <Icon /><span>{label}</span>
            </button>
          );
        }
        return (
          <Link key={key} to={to} className={`tab${active ? ' is-active' : ''}`} aria-current={active ? 'page' : undefined}>
            <Icon /><span>{label}</span>{key === 'review' && <ReviewBadge count={toReview} />}
          </Link>
        );
      })}
    </nav>
  );
}
