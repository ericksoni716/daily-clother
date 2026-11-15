// node render.js <shoe-fragment.svg> <out.png>: puts one shoe (drawn in the frame's coordinates) on a pair of legs,
// mirrors it for the other foot, and renders it large and at phone size.
const { chromium } = require('playwright'); const fs = require('fs');
const frag = fs.readFileSync(process.argv[2], 'utf8');
const leg = `<g stroke-linejoin="round"><path d="M60,-150 L140,-150 L138,60 L62,60 Z" fill="#c98d6b" stroke="#26221f" stroke-width="4"/>
<path d="M61,-92 Q100,-80 139,-92 L138,60 L62,60 Z" fill="#2f7d4f" stroke="#26221f" stroke-width="4"/>
<path d="M62,-76 Q100,-64 138,-76 M62,-62 Q100,-50 138,-62" fill="none" stroke="#1f5a38" stroke-width="2"/></g>`;
const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 440 400"><rect width="440" height="400" fill="#f1eee8"/>
<g transform="translate(22,150)">${leg}<g transform="rotate(7 100 40)">${frag}</g></g>
<g transform="translate(418,150) scale(-1,1)">${leg}<g transform="rotate(7 100 40)">${frag.replace(/id="/g, 'id="r')
  .replace(/url\(#/g, 'url(#r').replace(/href="#/g, 'href="#r')}</g></g></svg>`;
(async () => { const br = await chromium.launch(); const pg = await br.newPage({ viewport: { width: 760, height: 520 } });
  await pg.setContent(`<body style="margin:0;display:flex;gap:20px;align-items:flex-end;background:#fff"><div style="width:560px">${svg}</div><div style="width:150px">${svg}</div></body>`);
  await pg.screenshot({ path: process.argv[3] }); await br.close();
  fs.writeFileSync(process.argv[3].replace(/\.png$/, '.full.svg'), svg); })();
