const {chromium}=require(process.env.WFS_PLAYWRIGHT);
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://localhost:8000');await page.waitForTimeout(1000);
 const frame=page.frames().find(f=>f.url().includes('vnc.html'));
 await frame.waitForFunction(()=>document.querySelector('#noVNC_status')?.textContent.includes('Connected'),null,{timeout:30000});
 const settings=await frame.evaluate(()=>({showDot:document.querySelector('#noVNC_setting_show_dot').checked,viewOnly:document.querySelector('#noVNC_setting_view_only').checked}));
 const box=await frame.locator('canvas').boundingBox();
 console.log(JSON.stringify({settings,box}));
 await page.mouse.move(box.x+box.width*.5,box.y+box.height*Number(process.argv[2]||.458));
 await page.mouse.up();await page.waitForTimeout(1000);
 await page.mouse.down();await page.waitForTimeout(500);await page.mouse.up();
 await page.screenshot({path:'artifacts/browser-input-cursor.png',fullPage:true});
 await page.waitForTimeout(30000);
 await page.screenshot({path:'artifacts/browser-input-after.png',fullPage:true});
 fs.writeFileSync('artifacts/browser-input-result.json',JSON.stringify({settings,box,errors,clicked:'Settings > General',at:new Date().toISOString()},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
