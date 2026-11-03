const {chromium}=require(process.env.WFS_PLAYWRIGHT);
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});await page.goto('http://localhost:8000');
 await page.waitForTimeout(1000);
 const frame=page.frames().find(f=>f.url().includes('vnc.html'));
 await frame.waitForFunction(()=>document.querySelector('#noVNC_status')?.textContent.includes('Connected'),null,{timeout:30000});
 await frame.evaluate(async()=>{
  const {default:UI}=await import('/app/ui.js');const r=UI.rfb;
  window.pointerTrace=[];const send=r._sendMouse.bind(r);
  r._sendMouse=(x,y,mask)=>{window.pointerTrace.push({x,y,mask,at:performance.now()});return send(x,y,mask)};
 });
 const box=await frame.locator('canvas').boundingBox();
 await page.mouse.move(box.x+box.width*.5,box.y+box.height*.458);
 await page.waitForTimeout(200);
 const hoverPackets=await frame.evaluate(()=>window.pointerTrace.length);
 if(hoverPackets!==0)throw Error('Hover sent remote input');
 await page.mouse.down();await page.waitForTimeout(350);
 await frame.evaluate(()=>window.dispatchEvent(new Event('blur')));
 await page.mouse.up();
 const result=await frame.evaluate(async()=>{
  const {default:UI}=await import('/app/ui.js');return {trace:window.pointerTrace,buttonMask:UI.rfb._mouseButtonMask,cursor:getComputedStyle(document.querySelector('canvas')).cursor};
 });
 if(result.buttonMask!==0||!result.trace.some(e=>e.mask===1)||result.trace.at(-1).mask!==0)throw Error(JSON.stringify(result));
 fs.writeFileSync('artifacts/pointer-release-validation.json',JSON.stringify({passed:true,hoverPackets,...result},null,2));console.log(JSON.stringify(result));
 await page.waitForTimeout(10000);await page.screenshot({path:'artifacts/pointer-release-display.png',fullPage:true});
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
