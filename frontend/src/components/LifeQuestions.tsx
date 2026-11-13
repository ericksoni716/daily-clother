import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { api } from '../api';
import { FREQUENCIES, frequencyWords, newLife, SITUATIONS, type Life } from '../life';
import type { Settings } from '../types';
import { useMediaQuery } from '../router';
import './LifeQuestions.css';

export function LifeQuestions({ initial, locked, demo, onSaved, onClose }: {
  initial: Life | null; locked: boolean; demo: boolean;
  onSaved(settings: Settings): void | Promise<void>; onClose(): void;
}) {
  const [life, setLife] = useState<Life>(() => initial ?? newLife());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();
  const disabled = locked || demo || busy;
  const phone = useMediaQuery('(max-width: 680px)');
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (phone && dialog.current && !dialog.current.open) dialog.current.showModal();
  }, [phone]);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (disabled) return;
    setBusy(true);
    setError(null);
    try {
      const settings = await api.putSettings({ life, life_prompt_dismissed: true });
      await onSaved(settings);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const form = (
    <form className="life-questions" aria-labelledby={`${id}-title`} onSubmit={(e) => void save(e)}>
      <header className="life-heading">
        <div><p className="life-eyebrow">YOUR DAYS, YOUR CLOSET</p><h2 id={`${id}-title`}>How you live</h2></div>
        <span className="life-minute">About 1 minute</span>
      </header>
      <p className="life-intro">Days can overlap. For vacation, count days per week while away, not across the whole year.</p>
      {demo && <p className="notice">The demo uses fixed example answers. Switch to your own closet in Settings to save yours.</p>}
      {locked && <p className="notice">These are your saved answers. Connect to Closet on your computer to change them.</p>}
      <fieldset disabled={disabled}>
        <legend className="visually-hidden">How often do you dress for each part of your life?</legend>
        <div className="life-frequencies">
          {SITUATIONS.map(({ id: situation, label }) => (
            <label className="life-frequency" key={situation}>
              <span>{label}</span>
              <select aria-label={`${label} frequency`} value={life.situations[situation]}
                onChange={(e) => setLife({ ...life, situations: { ...life.situations, [situation]: Number(e.target.value) } })}>
                {FREQUENCIES.map((f) => <option value={f.value} key={f.value}>{f.label}</option>)}
                {!FREQUENCIES.some((f) => f.value === life.situations[situation]) &&
                  <option value={life.situations[situation]}>{frequencyWords(life.situations[situation])}</option>}
              </select>
            </label>
          ))}
        </div>
        <div className="life-details">
          {life.situations.work > 0 && <label className="field">
            <span>At work, you dress</span>
            <select value={life.work_dress} onChange={(e) => setLife({ ...life, work_dress: e.target.value as Life['work_dress'] })}>
              <option value="casual">Casual</option><option value="smart_casual">Smart casual</option>
              <option value="business">Business</option><option value="formal">Formal</option>
            </select>
          </label>}
          {life.situations.vacation > 0 && <div className="life-vacation">
            <label className="field">
              <span>Vacation weeks per year</span>
              <input type="number" min={Number.MIN_VALUE} max={52} step="any" required
                aria-describedby={`${id}-weeks-hint`} value={Number.isNaN(life.vacation_weeks) ? '' : life.vacation_weeks}
                onInvalid={(e) => {
                  if (e.currentTarget.validity.rangeUnderflow || e.currentTarget.validity.valueMissing) {
                    e.currentTarget.setCustomValidity('Enter more than 0 weeks, or set Vacation to Never.');
                  }
                }}
                onChange={(e) => {
                  e.target.setCustomValidity('');
                  setLife({ ...life, vacation_weeks: e.target.value === '' ? NaN : Number(e.target.value) });
                }} />
            </label>
            <label className="field"><span>Vacation weather</span>
              <select value={life.vacation_climate} onChange={(e) => setLife({ ...life, vacation_climate: e.target.value as Life['vacation_climate'] })}>
                <option value="warm">Warm</option><option value="cold">Cold</option><option value="both">Both</option>
              </select>
            </label>
          </div>}
          {life.situations.vacation > 0 && <p className="hint" id={`${id}-weeks-hint`}>Enter more than 0 weeks, or set Vacation to Never.</p>}
          <label className="field life-style">
            <span>My style in a few words <span className="muted">(optional)</span></span>
            <input value={life.style_words} onChange={(e) => setLife({ ...life, style_words: e.target.value })}
              maxLength={200} placeholder="e.g. relaxed, simple, a little colour" aria-describedby={`${id}-style-hint`} />
          </label>
          <p className="hint" id={`${id}-style-hint`}>Kept in your own words, not interpreted or used to rank suggestions yet.</p>
        </div>
      </fieldset>
      {error && <p role="alert" className="form-error">{error}</p>}
      <div className="row life-actions">
        {!demo && <button className="btn btn-primary" type="submit" disabled={disabled}>{busy ? 'Saving…' : 'Save my answers'}</button>}
        <button className="btn btn-ghost" type="button" disabled={busy} onClick={onClose}>{locked || demo ? 'Close' : 'Cancel'}</button>
      </div>
    </form>
  );

  return phone ? <dialog ref={dialog} className="life-dialog" aria-label="How you live"
    onCancel={(e) => { e.preventDefault(); if (!busy) onClose(); }}>
    {form}
  </dialog> : form;
}
