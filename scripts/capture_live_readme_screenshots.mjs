// Read-only, headless live captures. Playwright is an external documentation tool,
// not a runtime dependency. Supply credentials through the environment, never arguments.
import {createRequire} from 'node:module';
import {mkdir, writeFile, access, readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import assert from 'node:assert/strict';

const require=createRequire(import.meta.url);
const {chromium}=require(process.env.SIGNAL_ARCADE_CAPTURE_PLAYWRIGHT || 'playwright');
const base=new URL(process.env.SIGNAL_ARCADE_CAPTURE_URL || 'http://127.0.0.1:8765/');
const password=process.env.SIGNAL_ARCADE_CAPTURE_PASSWORD;
const output=process.env.SIGNAL_ARCADE_CAPTURE_OUTPUT;
const expectedVersion=JSON.parse(await readFile(new URL('../package.json',import.meta.url),'utf8')).version;
if(!password || !output) throw new Error('Capture password and a new output directory are required');
assert.ok(['http:','https:'].includes(base.protocol));
assert.ok(!base.username && !base.password, 'Do not place credentials in the URL');
await mkdir(output, {recursive:false}); // Never overwrite an earlier capture set.
const report={version:null,started_at:new Date().toISOString(),source:'Live local paper-trading app on mainnet data',
  browser:`Headless ${process.env.SIGNAL_ARCADE_CAPTURE_BROWSER || 'chrome'}`,locale:'en-GB',timezone:'Europe/London',graphics:'Low',
  capture_policy:'Actual rendered UI; no synthetic responses, altered figures, hidden warnings or selected performance winners.',
  image:process.env.SIGNAL_ARCADE_CAPTURE_IMAGE || null,screenshots:[],errors:[],failed_requests:[],mutations:[]};
const browser=await chromium.launch({channel:process.env.SIGNAL_ARCADE_CAPTURE_BROWSER || 'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1040},deviceScaleFactor:1,locale:report.locale,timezoneId:report.timezone,
  httpCredentials:{username:'admin',password,origin:base.origin}});
await context.addInitScript(()=>localStorage.setItem('signal-arcade-champion-graphics-v1','low'));
await context.grantPermissions(['local-network-access'],{origin:base.origin});
const page=await context.newPage();
page.setDefaultTimeout(15000);
page.setDefaultNavigationTimeout(30000);
page.on('pageerror',e=>report.errors.push(e.message));
let websocketFrames=0;
page.on('websocket',socket=>socket.on('framereceived',()=>websocketFrames++));
page.on('response',r=>{if(r.status()>=400&&r.status()!==401)report.failed_requests.push({path:new URL(r.url()).pathname,status:r.status()});});
await page.route('**/*',r=>{
  if(!['GET','HEAD'].includes(r.request().method())) {report.mutations.push({method:r.request().method(),path:new URL(r.request().url()).pathname});return r.abort();}
  return r.continue();
});
async function nav(name){await page.getByRole('button',{name,exact:true}).first().click();await settle();await page.evaluate(()=>window.scrollTo({top:0,left:0,behavior:'instant'}));}
async function tab(name){await page.getByRole('tab',{name,exact:true}).click();await settle();await page.evaluate(()=>window.scrollTo({top:0,left:0,behavior:'instant'}));}
async function settle(){await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(700);}
async function capture(file,caption,selector){
  await settle();
  const target=selector?page.locator(selector):null;
  if(target)await target.scrollIntoViewIfNeeded();
  const text=await (target||page.locator('body')).innerText();
  assert.ok(!text.includes(password),'A capture contains a credential');
  const bounds=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
  assert.ok(bounds.scroll<=bounds.width+1,`Page overflow while capturing ${file}`);
  const destination=path.join(output,file);
  await assert.rejects(access(destination),'Screenshot already exists');
  const png=target?await target.screenshot({animations:'disabled'}):await page.screenshot({fullPage:false,animations:'disabled'});
  await writeFile(destination,png,{flag:'wx'});
  report.screenshots.push({file,caption,captured_at:new Date().toISOString(),viewport:page.viewportSize(),selector:selector||'viewport',
    width:png.readUInt32BE(16),height:png.readUInt32BE(20),bytes:png.length,sha256:createHash('sha256').update(png).digest('hex')});
  console.log(JSON.stringify({captured:file,bytes:png.length}));
}
async function openBattle(){
  const button=page.getByRole('button',{name:/^(Entry|Manipulation|Sizing|Exit): Watch battle in Champion Arena$/}).first();
  await button.waitFor();
  report.live_battle_skill=(await button.getAttribute('aria-label')).split(':')[0];
  await button.click();
  await page.locator('.ca-stage').scrollIntoViewIfNeeded();
  await page.locator('.ca-stage[data-renderer="3d"]').waitFor({timeout:20000});
  await page.waitForTimeout(3200);
}
try {
  const response=await context.request.get(new URL('/api/v1/snapshot',base).href);
  assert.ok(response.ok());const snapshot=await response.json();
  assert.ok(snapshot.paper_only&&!snapshot.demo_mode);assert.equal(snapshot.version,expectedVersion);report.version=snapshot.version;
  await page.goto(base.href,{waitUntil:'domcontentloaded'});await page.getByRole('button',{name:'Learning',exact:true}).waitFor({timeout:30000});
  await nav('Arena');await capture('01-arena-overview.png','Live paper Arena: equity, risk profile, positions and engine status.');
  await nav('Decisions');await capture('02-decision-board.png','Current decision board with real point-in-time evidence.');
  await nav('Results');const seasons=page.getByRole('button',{name:'Seasons',exact:true});if(await seasons.count())await seasons.click();
  await page.getByRole('table',{name:'Paper season scorecards'}).waitFor({timeout:45000});
  const strategy=page.locator('.season-strategy summary').first();if(await strategy.count())await strategy.click();
  await page.setViewportSize({width:1440,height:1400});await page.evaluate(()=>window.scrollTo(0,0));
  await capture('03-season-progress.png','Default season comparison and recorded strategy use; no performance group was selected for a better result.');
  await page.setViewportSize({width:1440,height:1040});
  await nav('Learning');await tab('Challenger');await capture('04-learning-lab.png','Statistical Challenger training, saved permission and actual independently qualified skill support.');
  await capture('10-skill-progress.png','Entry, Manipulation, Sizing and Exit: current candidates, saved Champions and proof gates.','.challenger-skill-grid');
  await capture('12-reigning-champions.png','Current saved Champions with stable portraits and recorded crown retentions.','.reigning-champions');
  await page.setViewportSize({width:1440,height:1440});await openBattle();
  await capture('11-champion-arena.png',`A live ${report.live_battle_skill} comparison: measured advantage and uncertainty, not win probability.`);
  await page.setViewportSize({width:390,height:1000});await page.locator('.ca-intro').scrollIntoViewIfNeeded();
  await capture('14-mobile-battle.png','Mobile live battle, with the same fighters and measured evidence.');
  await capture('17-mobile-evidence.png','Mobile advantage readout with timestamp, uncertainty and sample requirements.','.ca-readout');
  await page.getByRole('button',{name:'Close Champion Arena'}).click();assert.equal(await page.locator('[data-champion-renderer]').count(),0);
  await page.setViewportSize({width:1440,height:1440});
  await page.getByRole('button',{name:'Show champion journey',exact:true}).click();
  await page.getByRole('button',{name:'Animated recap',exact:true}).first().click();
  await page.locator('.ca-stage').scrollIntoViewIfNeeded();await page.locator('.ca-stage[data-renderer="3d"]').waitFor({timeout:20000});await page.waitForTimeout(1800);
  const result=page.getByRole('button',{name:'Result',exact:true});if(await result.count()){if(await result.isEnabled())await result.click();}
  else {const skip=page.getByRole('button',{name:'Skip animation',exact:true});if(await skip.count())await skip.click();}
  await capture('13-recorded-battle.png','A saved battle result replayed from the recorded comparison.');
  await page.getByRole('button',{name:'Close Champion Arena'}).click();
  await page.getByRole('button',{name:/^Entry: .* in Champion Arena$/}).click();
  await page.locator('.ca-stage').scrollIntoViewIfNeeded();await page.locator('.ca-stage[data-renderer="3d"]').waitFor({timeout:20000});
  await page.waitForTimeout(3200);
  await capture('16-entry-profile.png','The current Entry model profile, with its family identity and real proof status.');
  await page.getByRole('button',{name:'Close Champion Arena'}).click();
  await page.setViewportSize({width:1440,height:1040});await tab('AI Coach');await capture('09-ai-coach-room.png','Optional AI Coach research, separate from trading authority.');
  await nav('Replay');
  const chart=page.getByRole('slider',{name:'Inspect paper equity checkpoints'});
  await chart.waitFor();await chart.focus();await page.keyboard.press('Home');await page.keyboard.press('ArrowRight');
  await capture('18-replay-equity.png','Keyboard inspection of a saved equity checkpoint; no best-performing point was selected.','.replay-chart');
  await page.getByRole('table',{name:'Current-season paper fill receipts'}).evaluate(node=>
    window.scrollTo({top:window.scrollY+node.getBoundingClientRect().top-180,behavior:'instant'}));
  await capture('08-replay-receipts.png','Latest paper fill receipts with recorded fees, impact and latency.');
  await nav('Settings');const providers=page.getByRole('button',{name:'Show data providers',exact:true});if(await providers.count())await providers.click();
  await capture('05-data-providers.png','Provider roles, budgets and current activity; no secret editor is opened.','.provider-manager');
  const models=page.getByRole('button',{name:'Show local AI models',exact:true});if(await models.count())await models.click();
  await capture('06-local-ai.png','Installed local AI models and runtime information.','.ai-model-manager');
  await page.locator('.diagnostics-card').getByText(/Recording in the background|Recording delayed|Paused to protect storage/).waitFor();
  await page.locator('.diagnostics-card').evaluate(node=>node.scrollIntoView({block:'center',behavior:'instant'}));
  await capture('15-diagnostics-history.png','Separate bounded diagnostics history for reviewing long-term operation.','.diagnostics-card');
  await page.setViewportSize({width:390,height:1000});await nav('Arena');await capture('07-mobile-arena.png','Live paper Arena on a 390-pixel mobile viewport.');
  assert.equal(report.errors.length,0);assert.equal(report.failed_requests.length,0);assert.equal(report.mutations.length,0);
  assert.ok(websocketFrames>0,'Expected live WebSocket updates');report.websocket_frames=websocketFrames;
  report.completed_at=new Date().toISOString();
}catch(error){report.failure=error.message;throw error;}finally{
  await writeFile(path.join(output,'capture.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  try { await context.close(); } finally { await browser.close(); }
}
// This is a one-shot CLI. Some external Playwright transports retain idle handles
// after browser shutdown; all captures and the manifest are fully written above.
process.exit(0);
