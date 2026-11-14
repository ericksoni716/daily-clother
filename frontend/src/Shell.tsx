import { useState, type ReactNode } from 'react';
import { CloudOffIcon, GearIcon, HangerIcon, PlusIcon, SuitcaseIcon, SunIcon } from './components/Icons';
import { useLanding } from './landing';
import { Button, buttonClass } from './components/ui';
import { navSection, tabFor } from './nav';
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
import { ReviewBadge, reviewCountText, ReviewIcon, ReviewScreen, useReviewCount } from './screens/Review';
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
  else if (route.name === 'missing') content = <MissingScreen itemId={route.itemId} check={route.check} wishId={route.wishId} wide={wide} />;
  else if (route.name === 'add') content = <AddScreen />;
  else if (route.name === 'settings') content = <SettingsScreen version={version} />;
  else if (route.name === 'insights') content = <InsightsScreen />;
  else if (route.name === 'review') content = <ReviewScreen />;
  else if (route.name === 'trips') content = <TripsScreen tripId={route.tripId} />;
  else if (route.itemId && !wide) content = <ItemDetail key={route.itemId} id={route.itemId} status={route.status} />;
  else content = <ClosetScreen status={route.status} selectedId={route.itemId} wide={wide} toReview={toReview} />;

  const section = navSection(route);

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
          <span className="ribbon-sep" aria-hidden="true">·</span>
          <Button variant="link" small aria-label="Leave the demo closet" disabled={busy || offline} onClick={async () => {
            setBusy(true);
            try {
              await switchProfile('main');
            } catch (e) {
              toast((e as Error).message, 'error');
              setBusy(false);
            }
          }}>Leave</Button>
        </div>
      )}
    </>
  );
}

const ADD_OFFLINE = 'Adding photos needs Closet on your computer to be reachable';

const NAV = [
  { key: 'today', to: '/today', label: 'Today', Icon: SunIcon },
  { key: 'closet', to: '/', label: 'Closet', Icon: HangerIcon },
  { key: 'trips', to: '/trips', label: 'Trips', Icon: SuitcaseIcon },
  { key: 'missing', to: '/missing', label: "What's missing", Icon: BagIcon },
] as const;

function NavLink({ to, active, className = 'nav-link', children }: { to: string; active: boolean; className?: string; children: ReactNode }) {
  return <Link to={to} className={`${className}${active ? ' is-active' : ''}`} aria-current={active ? 'page' : undefined}>{children}</Link>;
}

function Sidebar({ section, offline, toReview }: { section: string; offline: boolean; toReview: number | null }) {
  const showReview = !!toReview || section === 'review';
  return (
    <nav className="sidebar" aria-label="Main">
      <div className="sidebar-brand"><span className="brand-dot"><HangerIcon /></span> Closet</div>
      {offline ? (
        <span className={buttonClass({ variant: 'primary', block: true, className: 'sidebar-add is-disabled' })} aria-disabled="true" title={ADD_OFFLINE}>
          <PlusIcon /> Add clothes
        </span>
      ) : (
        <Link to="/add" className={buttonClass({ variant: 'primary', block: true, className: 'sidebar-add' })}
          aria-current={section === 'add' ? 'page' : undefined}>
          <PlusIcon /> Add clothes
        </Link>
      )}
      <ul>
        {NAV.map(({ key, to, label, Icon }) => (
          <li key={key}>
            <NavLink to={to} active={section === key}>
              <Icon /> {label}{key === 'closet' && <ReviewBadge count={toReview} quiet />}
            </NavLink>
            {key === 'closet' && showReview && (
              <NavLink to="/review" active={section === 'review'} className="nav-link nav-sublink">
                <ReviewIcon /> Review{toReview ? <span className="visually-hidden">{reviewCountText(toReview)}</span> : null}
              </NavLink>
            )}
          </li>
        ))}
      </ul>
      <ul className="sidebar-bottom">
        <li><NavLink to="/settings" active={section === 'settings'}><GearIcon /> Settings</NavLink></li>
      </ul>
    </nav>
  );
}

const TABS = [
  { key: 'today', to: '/today', label: 'Today', Icon: SunIcon },
  { key: 'closet', to: '/', label: 'Closet', Icon: HangerIcon },
  { key: 'add', to: '/add', label: 'Add', Icon: PlusIcon },
  { key: 'missing', to: '/missing', label: 'Missing', Icon: BagIcon },
  { key: 'settings', to: '/settings', label: 'Settings', Icon: GearIcon },
] as const;

function TabBar({ section, offline, toReview }: { section: string; offline: boolean; toReview: number | null }) {
  const lit = tabFor(section);
  return (
    <nav className="tabbar" aria-label="Main">
      {TABS.map(({ key, to, label, Icon }) => {
        const active = lit === key;
        const add = key === 'add';
        const inner = add ? <><span className="tab-add-circle"><Icon /></span><span>{label}</span></> : <><Icon /><span>{label}</span></>;
        if (add && offline) {
          return <button key={key} type="button" className="tab tab-add" disabled title={ADD_OFFLINE}>{inner}</button>;
        }
        return (
          <Link key={key} to={to} className={`tab${add ? ' tab-add' : ''}${active ? ' is-active' : ''}`} aria-current={active ? 'page' : undefined}>
            {inner}
            {key === 'closet' && !!toReview && (
              <><span className="tab-dot" data-testid="review-dot" aria-hidden="true" /><span className="visually-hidden">{reviewCountText(toReview)}</span></>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
