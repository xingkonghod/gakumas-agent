const fs = require('fs');
const html = fs.readFileSync('docs/review_sample.html', 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>\s*<\/body>/);
if (!m) { console.error('no page script found'); process.exit(1); }
fs.writeFileSync('data/_p16_page_js.js', m[1]);
const jm = html.match(/<script type="application\/json" id="review-data">([\s\S]*?)<\/script>/);
const payload = JSON.parse(jm[1]);
console.log('embedded JSON ok:', payload.episode, 'trace_source=' + payload.trace_source, 'steps=' + payload.replay.steps, 'consistent=' + payload.replay.consistent);
console.log('banner:', html.includes('演示轨迹（合成数据'));
console.log('ann rows:', (html.match(/data-ann-id=/g) || []).length);
