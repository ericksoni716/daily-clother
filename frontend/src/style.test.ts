import { describe, expect, it } from 'vitest';
import { lineSource, lineText, moreLines, removedWords, profileLines, shownLines, STYLE_WARN_WITHIN, styleChanged, styleCount, talkPoll, tidyStyle } from './style';
import type { TalkTurn } from './today';

describe('the style profile being written', () => {
  it('is tidied as the server keeps it, with the line breaks kept', () => {
    expect(tidyStyle('  I run warm.\r\n\r\nNo ties.\rNavy with brown.\n ')).toBe('I run warm.\n\nNo ties.\nNavy with brown.');
  });

  it('is a change only when the tidied text differs from the one in force', () => {
    expect(styleChanged('No ties.', 'No ties.')).toBe(false);
    expect(styleChanged('No ties.  \n', 'No ties.')).toBe(false);
    expect(styleChanged('No ties!', 'No ties.')).toBe(true);
    expect(styleChanged('', 'No ties.')).toBe(true);
  });

  it('counts its characters and warns in the last 200', () => {
    expect(styleCount(123, 4000)).toEqual({ text: '123 / 4000', warn: false });
    expect(styleCount(4000 - STYLE_WARN_WITHIN, 4000).warn).toBe(false);
    expect(styleCount(4000 - STYLE_WARN_WITHIN + 1, 4000)).toEqual({ text: '3801 / 4000', warn: true });
    expect(styleCount(4000, 4000).warn).toBe(true);
  });
});

describe('the lines of your style', () => {
  it('read without the dash a list line starts with', () => {
    expect(lineText('- No ties unless it is a wedding.')).toBe('No ties unless it is a wedding.');
    expect(lineText('  -  Navy with brown. ')).toBe('Navy with brown.');
    expect(lineText('I dress plainly.')).toBe('I dress plainly.');
    expect(lineText('-3 degrees is cold for me.')).toBe('-3 degrees is cold for me.');
  });

  it('say where each came from and when, in the words the wears use for a day', () => {
    const today = '2026-11-20';
    // noon UTC is the same calendar day in every time zone the tests run in
    expect(lineSource({ source: 'start', created_at: null }, today)).toBe('Starting rule');
    expect(lineSource({ source: 'start', created_at: '2026-11-12T12:00:00Z' }, today)).toBe('Starting rule');
    expect(lineSource({ source: 'owner', created_at: '2026-11-12T12:00:00Z' }, today)).toBe('You said this on 12 Nov');
    expect(lineSource({ source: 'owner', created_at: '2026-11-20T12:00:00Z' }, today)).toBe('You said this today');
    expect(lineSource({ source: 'talk', created_at: '2026-11-19T12:00:00Z' }, today)).toBe('From a conversation yesterday');
    expect(lineSource({ source: 'question', created_at: '2026-11-17T12:00:00Z' }, today)).toBe('Your answer on Tuesday');
    expect(lineSource({ source: 'talk', created_at: '2025-03-02T12:00:00Z' }, today)).toBe('From a conversation on 2 Mar 2025');
  });

  it('show the first three on the Settings card, and how many more there are', () => {
    expect(shownLines(['a', 'b'])).toEqual({ shown: ['a', 'b'], more: 0 });
    expect(shownLines(['a', 'b', 'c', 'd', 'e'])).toEqual({ shown: ['a', 'b', 'c'], more: 2 });
    expect(moreLines(1)).toBe('And 1 more line.');
    expect(moreLines(4)).toBe('And 4 more lines.');
  });

  it('say which line was removed, with one full stop', () => {
    expect(removedWords('- No ties unless it is a wedding.')).toBe('Removed “No ties unless it is a wedding.”');
    expect(removedWords('Navy with brown')).toBe('Removed “Navy with brown”.');
  });

  it('come from the text, a line each, in a copy saved before lines existed', () => {
    expect(profileLines({ text: '- One.\n\nTwo.', is_default: false })).toEqual([
      { id: -1, text: '- One.', source: 'owner', created_at: null }, { id: -2, text: 'Two.', source: 'owner', created_at: null }]);
    expect(profileLines({ text: 'x', is_default: true, lines: [] })).toEqual([]);
  });
});

describe('the style conversation', () => {
  const turn = (state: TalkTurn['state']): TalkTurn => ({ id: 't', said: 'Hi.', state, reply: null, message: null, remember: [], at: '' });

  it('is asked again every 1.5 seconds only while Claude is answering', () => {
    expect(talkPoll(undefined)).toBe(false);
    expect(talkPoll({ turns: [], answering: null })).toBe(false);
    expect(talkPoll({ turns: [turn('ready')], answering: null })).toBe(false);
    expect(talkPoll({ turns: [turn('working')], answering: null })).toBe(1500);
    expect(talkPoll({ turns: [], answering: 't' })).toBe(1500);
  });
});
