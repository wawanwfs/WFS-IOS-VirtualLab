const {chromium}=require(process.env.WFS_PLAYWRIGHT);
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
 const page=await browser.newPage();await page.goto('http://localhost:8000');
 await page.waitForTimeout(1000);
 const frame=page.frames().find(f=>f.url().includes('vnc.html'));
 await frame.waitForFunction(()=>document.querySelector('#noVNC_status')?.textContent.includes('Connected'),null,{timeout:30000});
 const result=await frame.evaluate(()=>({cursor:getComputedStyle(document.querySelector('canvas')).cursor,showDot:document.querySelector('#noVNC_setting_show_dot').checked,viewOnly:document.querySelector('#noVNC_setting_view_only').checked}));
 if(result.cursor!=='crosshair'||!result.showDot||result.viewOnly)throw Error(JSON.stringify(result));
 fs.writeFileSync('artifacts/cursor-validation.json',JSON.stringify({...result,passed:true},null,2));console.log(result);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
