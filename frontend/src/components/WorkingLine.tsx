import { useRef, useState } from 'react';
import { workingLine } from '../progress';
import { useProgress } from '../queries';
import { Link } from '../router';
import type { ProgressList } from '../types';
import { AddedRow } from './AddedItem';
import { Sheet } from './ui';
import './Progress.css';

/**
 * The one line about all the work under way, floating above the closet grid (it moves nothing when it comes and
 * goes): "Working on 3 items". It opens the list of those items, each with how far it has got.
 */
export function WorkingLine() {
  const list = useProgress();
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const line = workingLine(list);
  if (!line || !list) return null;
  const going = list.going > 0;
  return (
    <div className="working-float">
      <button ref={button} type="button" className={`working-pill${going ? ' is-going' : ''}`} data-testid="working-line"
        aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen((o) => !o)}>
        {going ? <span className="spinner" aria-hidden="true" /> : <span className="working-wait" aria-hidden="true" />}
        {line}
      </button>
      {open && (
        <Sheet title={line} popover keep={button} className="working-sheet" testId="working-sheet" onClose={() => setOpen(false)}>
          <WorkingList list={list} />
        </Sheet>
      )}
    </div>
  );
}

function WorkingList({ list }: { list: ProgressList }) {
  return (
    <>
      {list.why && (
        <p className="notice" data-testid="working-why">{list.why} <Link to="/settings">Open Settings</Link></p>
      )}
      <ul className="queue-list working-list" aria-label="Being worked on">
        {list.items.map((i) => (
          <AddedRow key={i.id} item={i} progress={i.progress} testId="working-item" sub={i.progress.title} />
        ))}
      </ul>
    </>
  );
}
