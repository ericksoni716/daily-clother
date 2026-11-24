import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { CloudOffIcon, GearIcon, HangerIcon, PlusIcon, SunIcon, WardrobeIcon } from './components/Icons';
import { NinesMark, NinesName } from './components/NinesMark';
import { useLanding } from './landing';
import { Button, buttonClass, ErrorBoundary } from './components/ui';
import { movedTo, placeOf, type AppPlace } from './places';
import { Link, navigate, parseRoute, usePath, useMediaQuery, WIDE } from './router';
import { useItems } from './queries';
import { outboxFor } from './outbox';
import { useApp, useKept } from './store';
import { ClosetScreen } from './screens/Closet';
import { AddScreen } from './screens/Add';
import { SeveralScreen } from './screens/Several';
import { SettingsScreen } from './screens/Settings';
import { ItemDetail } from './screens/ItemDetail';
import { TodayScreen } from './screens/Today';
import { TripsScreen } from './screens/Trips';
import { WornScreen } from './screens/Worn';
import { ReviewBadge, reviewCountText, ReviewScreen, useReviewCount } from './screens/Review';
import { WardrobeScreen } from './screens/Wardrobe';
import { Restarting, UpdateBanner, useUpdateStatus } from './components/Updates';
import { RestoreNotice } from './components/RestoreNotice';
import { PriceNewsBanner } from './components/PriceNews';

/** The Advanced settings: set once and rarely opened, so its code is fetched only when it is. */
const AdvancedScreen = lazy(() => import('./screens/Advanced').then((m) => ({ default: m.AdvancedScreen })));

export function Shell({ version }: { version: string }) {
  const path = usePath();
  const route = parseRoute(path);
  const wide = useMediaQuery(WIDE);
  const { offline } = useApp();
  const toReview = useReviewCount();
  // An address that has moved (a bookmark, the home-screen app, a reload) shows its new screen at once, and takes the
  // new address in place of the old, so Back and a later reload find it there.
  const moved = movedTo(window.location.pathname + window.location.search + window.location.hash);
  useEffect(() => {
    if (moved) navigate(moved, { replace: true });
  }, [moved]);

  let content;
  if (route.name === 'today') content = <TodayScreen key={route.day ?? 'today'} itemId={route.itemId} wide={wide} day={route.day ?? null} />;
  else if (route.name === 'worn') content = <WornScreen itemId={route.itemId} kept={!!route.kept} />;
  else if (route.name === 'wardrobe') {
    content = <WardrobeScreen itemId={route.itemId} check={route.check} wishId={route.wishId} wish={route.wish} link={!!route.link}
      wishlist={!!route.wishlist} wide={wide} />;
  }
  else if (route.name === 'add') content = <AddScreen />;
  else if (route.name === 'several') content = <SeveralScreen key={route.id} id={route.id} />;
  else if (route.name === 'settings') content = <SettingsScreen version={version} />;
  else if (route.name === 'advanced') {
    content = <Suspense fallback={<p className="hint" aria-busy="true">Opening the advanced settings…</p>}><AdvancedScreen /></Suspense>;
  }
  else if (route.name === 'review') content = <ReviewScreen />;
  else if (route.name === 'trips') content = <TripsScreen tripId={route.tripId} />;
  else if (route.itemId && !wide) content = <ItemDetail key={route.itemId} id={route.itemId} status={route.status} />;
  else content = <ClosetScreen status={route.status} selectedId={route.itemId} wide={wide} toReview={toReview} />;

  const place = placeOf(route);

  return (
    <div className="shell">
      <Landing path={path} />
      <a className="skip-link" href="#main">Skip to content</a>
      <Sidebar place={place} offline={offline} toReview={toReview} />
      <div className="shell-main">
        <TopBanners screen={path} wishId={route.name === 'wardrobe' ? route.wish ?? null : null} />
        <main id="main" className="shell-content" tabIndex={-1}><ErrorBoundary resetKey={path}>{content}</ErrorBoundary></main>
      </div>
      <TabBar place={place} offline={offline} toReview={toReview} />
    </div>
  );
}

/** Which screen the app opens on. On its own, so a change to the items draws only this, not the whole frame. */
function Landing({ path }: { path: string }) {
  useLanding(path, useItems('active').data ?? null);
  return null;
}

/** What is said above every screen. Each holds still while you read: what arrives after a screen opened is shown from
 * the next screen on (`useAsOpened`; DECISIONS, "Banners wait for the next screen"). */
function TopBanners({ screen, wishId }: { screen: string; wishId: string | null }) {
  const { offline, profile, switchProfile, toast } = useApp();
  const [busy, setBusy] = useState(false);
  useUpdateStatus(offline);
  // worn, rated or ticked while Nines could not be reached, and not sent yet
  const kept = useKept(outboxFor(profile)).length > 0;
  return (
    <>
      <Restarting />
      <UpdateBanner offline={offline} toast={toast} screen={screen} />
      <PriceNewsBanner offline={offline} toast={toast} screen={screen} wishId={wishId} />
      <RestoreNotice offline={offline} toast={toast} screen={screen} />
      {offline && (
        <div className="banner banner-offline" role="status">
          <CloudOffIcon />
          <div>
            <strong>Offline: showing your saved closet.</strong>
            {/* the one place that says something is kept: in place of the last words, and no longer, so nothing moves */}
            {kept ? <span data-testid="kept-line"> Nines on your computer can't be reached. What you marked is kept on this phone and will be sent when Nines answers.</span>
              : <span> Nines on your computer can't be reached, so changes and new photos have to wait. This updates by itself when it's back.</span>}
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

const ADD_OFFLINE = 'Adding photos needs Nines on your computer to be reachable';

/** The four places and Add, in the sidebar's order (Add is the button above them, Settings sits at the foot). */
const NAV = [
  { key: 'today', to: '/today', label: 'Today', Icon: SunIcon },
  { key: 'closet', to: '/', label: 'Closet', Icon: HangerIcon },
  { key: 'wardrobe', to: '/wardrobe', label: 'Wardrobe', Icon: WardrobeIcon },
] as const;

function NavLink({ to, active, className = 'nav-link', children }: { to: string; active: boolean; className?: string; children: ReactNode }) {
  return <Link to={to} className={`${className}${active ? ' is-active' : ''}`} aria-current={active ? 'page' : undefined}>{children}</Link>;
}

function Sidebar({ place, offline, toReview }: { place: AppPlace; offline: boolean; toReview: number | null }) {
  return (
    <nav className="sidebar" aria-label="Main">
      <div className="sidebar-brand"><NinesMark /> <NinesName /></div>
      {offline ? (
        <span className={buttonClass({ variant: 'primary', block: true, className: 'sidebar-add is-disabled' })} aria-disabled="true" title={ADD_OFFLINE}>
          <PlusIcon /> Add clothes
        </span>
      ) : (
        <Link to="/add" className={buttonClass({ variant: 'primary', block: true, className: 'sidebar-add' })}
          aria-current={place === 'add' ? 'page' : undefined}>
          <PlusIcon /> Add clothes
        </Link>
      )}
      <ul>
        {NAV.map(({ key, to, label, Icon }) => (
          <li key={key}>
            <NavLink to={to} active={place === key}>
              <Icon /> {label}{key === 'closet' && <ReviewBadge count={toReview} />}
            </NavLink>
          </li>
        ))}
      </ul>
      <ul className="sidebar-bottom">
        <li><NavLink to="/settings" active={place === 'settings'}><GearIcon /> Settings</NavLink></li>
      </ul>
    </nav>
  );
}

const TABS = [
  { key: 'today', to: '/today', label: 'Today', Icon: SunIcon },
  { key: 'closet', to: '/', label: 'Closet', Icon: HangerIcon },
  { key: 'add', to: '/add', label: 'Add', Icon: PlusIcon },
  { key: 'wardrobe', to: '/wardrobe', label: 'Wardrobe', Icon: WardrobeIcon },
  { key: 'settings', to: '/settings', label: 'Settings', Icon: GearIcon },
] as const;

function TabBar({ place, offline, toReview }: { place: AppPlace; offline: boolean; toReview: number | null }) {
  return (
    <nav className="tabbar" aria-label="Main">
      {TABS.map(({ key, to, label, Icon }) => {
        const active = place === key;
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
