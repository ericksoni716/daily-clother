import { describe, expect, it } from 'vitest';
import { parseInline, parseMarkdown } from './markdown';

const t = (text: string) => ({ kind: 'text', text });

describe('release notes as Markdown', () => {
  it('reads headings, relative to the largest one in the text', () => {
    expect(parseMarkdown('### Changed\n\n- One.\n\n### Fixed\n\n#### Small\n')).toEqual([
      { kind: 'heading', level: 1, children: [t('Changed')] },
      { kind: 'list', ordered: false, start: 1, items: [[t('One.')]] },
      { kind: 'heading', level: 1, children: [t('Fixed')] },
      { kind: 'heading', level: 2, children: [t('Small')] },
    ]);
    expect(parseMarkdown('## What\'s new ##\n# Big\n###### Tiny')).toEqual([
      { kind: 'heading', level: 2, children: [t("What's new")] },
      { kind: 'heading', level: 1, children: [t('Big')] },
      { kind: 'heading', level: 3, children: [t('Tiny')] },
    ]);
    // no space after the #: not a heading
    expect(parseMarkdown('#hashtag')).toEqual([{ kind: 'paragraph', children: [t('#hashtag')] }]);
  });

  it('joins a paragraph\'s lines and a list item\'s wrapped lines', () => {
    expect(parseMarkdown('First line\nsecond line.\n\nAnother.')).toEqual([
      { kind: 'paragraph', children: [t('First line second line.')] },
      { kind: 'paragraph', children: [t('Another.')] },
    ]);
    expect(parseMarkdown('- A shoe wears the plain\n  front view.\n* Second\n+ Third')).toEqual([
      { kind: 'list', ordered: false, start: 1, items: [[t('A shoe wears the plain front view.')], [t('Second')], [t('Third')]] },
    ]);
  });

  it('keeps numbered lists apart from bullets, with their first number', () => {
    expect(parseMarkdown('3. Three\n4) Four\n- Dash')).toEqual([
      { kind: 'list', ordered: true, start: 3, items: [[t('Three')], [t('Four')]] },
      { kind: 'list', ordered: false, start: 1, items: [[t('Dash')]] },
    ]);
  });

  it('reads bold, emphasis and code, nested', () => {
    expect(parseInline('Trips pack **lighter with `x`** and *much `more`* fun.')).toEqual([
      t('Trips pack '),
      { kind: 'strong', children: [t('lighter with '), { kind: 'code', text: 'x' }] },
      t(' and '),
      { kind: 'em', children: [t('much '), { kind: 'code', text: 'more' }] },
      t(' fun.'),
    ]);
    expect(parseInline('**bold with *emphasis* inside**')).toEqual([
      { kind: 'strong', children: [t('bold with '), { kind: 'em', children: [t('emphasis')] }, t(' inside')] },
    ]);
    expect(parseInline('`**not bold**`')).toEqual([{ kind: 'code', text: '**not bold**' }]);
  });

  it('keeps an unclosed mark as written', () => {
    expect(parseInline('Half **open and `tick')).toEqual([t('Half **open and `tick')]);
    expect(parseInline('2 * 3 * 4 and ****')).toEqual([t('2 * 3 * 4 and ****')]);
    expect(parseInline('\\*\\*escaped\\*\\*')).toEqual([t('**escaped**')]);
  });

  it('keeps a link as its words only', () => {
    expect(parseInline('See the [**release** page](https://github.com/o/r/releases) or [x](javascript:alert(1)).')).toEqual([
      t('See the '), { kind: 'strong', children: [t('release')] }, t(' page or x).'),
    ]);
    expect(parseInline('[not a link] (here)')).toEqual([t('[not a link] (here)')]);
  });

  it('keeps HTML as the text it is', () => {
    expect(parseMarkdown('<b>Not bold</b>\n\n- <img src=x onerror=alert(1)>')).toEqual([
      { kind: 'paragraph', children: [t('<b>Not bold</b>')] },
      { kind: 'list', ordered: false, start: 1, items: [[t('<img src=x onerror=alert(1)>')]] },
    ]);
  });

  it('drops rules and code fences, and reads nothing from nothing', () => {
    expect(parseMarkdown('One.\n---\n```\nTwo.\n```')).toEqual([
      { kind: 'paragraph', children: [t('One.')] },
      { kind: 'paragraph', children: [t('Two.')] },
    ]);
    expect(parseMarkdown('')).toEqual([]);
    expect(parseMarkdown(' \n\r\n ')).toEqual([]);
  });
});
