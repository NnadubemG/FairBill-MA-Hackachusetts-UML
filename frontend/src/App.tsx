import { useEffect, useRef, useState } from 'react';
import type { ExtractResponse, LineItem } from '@contracts';
import { Home } from './screens/Home';
import { Confirm } from './screens/Confirm';
import { Results } from './screens/Results';
import { Letter } from './screens/Letter';
import { Compare } from './screens/Compare';

type Screen = 'home' | 'confirm' | 'results' | 'letter' | 'compare';

/**
 * Single-page app, no login, no router dependency. Navigation is simple screen
 * state. Nothing about the bill is persisted (no localStorage, no analytics).
 */
export function App() {
  const [screen, setScreen] = useState<Screen>('home');
  const [items, setItems] = useState<LineItem[]>([]);
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    mainRef.current?.focus();
  }, [screen]);

  function handleExtracted(_text: string, result: ExtractResponse) {
    setItems(result.line_items);
    setScreen('confirm');
  }

  function handleConfirmed(confirmed: LineItem[]) {
    setItems(confirmed);
    setScreen('results');
  }

  return (
    <div className="app">
      <a className="skip-link" href="#main">Skip to main content</a>
      <header className="app-header">
        <button
          type="button"
          className="brand"
          onClick={() => setScreen('home')}
          aria-label="Go to the start"
        >
          Massachusetts Medical-Bill Helper
        </button>
      </header>

      <main id="main" className="app-main" ref={mainRef} tabIndex={-1}>
        {screen === 'home' && (
          <Home
            onExtracted={handleExtracted}
            onGoToCompare={() => setScreen('compare')}
          />
        )}
        {screen === 'confirm' && (
          <Confirm
            initial={items}
            onConfirmed={handleConfirmed}
            onBack={() => setScreen('home')}
          />
        )}
        {screen === 'results' && (
          <Results
            items={items}
            onGoToLetter={() => setScreen('letter')}
            onBack={() => setScreen('confirm')}
          />
        )}
        {screen === 'letter' && (
          <Letter items={items} onBack={() => setScreen('results')} />
        )}
        {screen === 'compare' && <Compare onBack={() => setScreen('home')} />}
      </main>

      <footer className="app-footer">
        <p>General information only. Nothing you enter is stored.</p>
      </footer>
    </div>
  );
}
