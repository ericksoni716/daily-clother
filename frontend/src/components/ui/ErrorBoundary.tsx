import { Component, type ErrorInfo, type ReactNode } from 'react';
import { WarnIcon } from '../Icons';
import { Button } from './Button';
import { EmptyState } from './EmptyState';

interface Props {
  children?: ReactNode;
  /** When this changes (the screen's address, say), a screen that failed is tried again. */
  resetKey?: unknown;
  /** The last resort around the whole app, where there is no screen around it to keep. */
  whole?: boolean;
}

interface State {
  error: Error | null;
  resetKey: unknown;
}

/** Words of the message shown in place of what failed (exported for its test). */
export const CRASH = {
  screen: 'Something went wrong on this screen.',
  whole: 'Something went wrong, and Closet could not show anything.',
  body: 'Anything you saved is kept. You can try again, or reload Closet.',
  retry: 'Try again',
  reload: 'Reload Closet',
};

/**
 * Keeps one failed screen from blanking the whole app: what failed is replaced by a plain message, the tab bar and
 * the sidebar stay, and going to another screen (a new `resetKey`) tries again. The error goes to the console.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, resetKey: this.props.resetKey };

  static getDerivedStateFromError(error: unknown): Partial<State> {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey !== state.resetKey ? { error: null, resetKey: props.resetKey } : null;
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error('Closet could not show this screen:', error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    const { whole } = this.props;
    return (
      <div className={whole ? 'crash crash-whole' : 'crash'} role="alert">
        <EmptyState big icon={<WarnIcon />} title={whole ? CRASH.whole : CRASH.screen} body={CRASH.body}
          action={(
            <div className="crash-actions">
              <Button variant="primary" onClick={() => this.setState({ error: null })}>{CRASH.retry}</Button>
              <Button onClick={() => window.location.reload()}>{CRASH.reload}</Button>
            </div>
          )} />
      </div>
    );
  }
}
