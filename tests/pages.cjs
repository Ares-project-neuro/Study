// Serve only the built static files under a project subpath, with no API server.
const {chromium,devices}=require('playwright');
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {execFileSync}=require('node:child_process');
const assert=require('node:assert/strict');
const root=path.resolve('_site'),prefix='/Study/';
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'neurostudy-pages-'));
const python=process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python';
const types={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.wasm':'application/wasm','.json':'application/json'};
const requests=[],errors=[];
const server=http.createServer((req,res)=>{
  requests.push(req.url);const relative=decodeURIComponent(new URL(req.url,'http://localhost').pathname).slice(prefix.length);
  if(!req.url.startsWith(prefix)){res.writeHead(404);return res.end('No API or root assets');}
  const file=path.resolve(root,relative||'index.html');
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);return res.end();}
  res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream'});fs.createReadStream(file).pipe(res);
});
let browser;
(async()=>{
  execFileSync(python,['scripts/pages-fixtures.py',temporary]);
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}${prefix}`;
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||undefined,headless:true,args:['--no-sandbox']});
  const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(20000);
  await page.goto(base);await page.getByLabel('Password',{exact:true}).fill('pages-password-tests-123');await page.locator('#login-form button').click();
  await page.getByRole('heading',{name:'Ogni giorno, un passo avanti.'}).waitFor();
  await page.getByText('GitHub Pages · archivio su questo dispositivo.').waitFor();
  await page.getByRole('link',{name:'I miei materiali',exact:true}).click();await page.getByRole('button',{name:'+ Carica materiale'}).click();
  const text='La miastenia presenta debolezza fluttuante e affaticabilita muscolare. La sensibilita generalmente rimane conservata nella malattia della giunzione neuromuscolare.';
  await page.locator('input[type=file]').setInputFiles({name:'Appunti Pages.txt',mimeType:'text/plain',buffer:Buffer.from(text)});
  await page.getByRole('button',{name:'Carica ed estrai il testo'}).click();await page.getByRole('heading',{name:'Appunti Pages.txt',exact:true}).waitFor();
  await page.getByRole('button',{name:'Genera quiz o flashcard'}).click();await page.locator('[name=document_ids]').check();await page.locator('[name=count]').fill('1');
  await page.getByRole('button',{name:'Genera e salva nel database'}).click();await page.getByRole('heading',{name:'Generazione completata'}).waitFor();await page.getByRole('link',{name:'Apri i contenuti'}).click();
  await page.getByRole('button',{name:'Modifica / approva'}).click();await page.locator('[name=review_required]').uncheck();await page.getByRole('button',{name:'Salva la revisione'}).click();
  await page.getByRole('button',{name:'Inizia una sessione'}).click();await page.locator('[name=mode]').selectOption('exam');await page.getByRole('button',{name:'Comincia il quiz'}).click();
  await page.getByRole('heading',{name:'Simulazione d’esame'}).waitFor();await page.locator('.option input').first().check();await page.getByRole('button',{name:'Conferma risposta'}).click();
  await page.getByText('Risposta salvata. La correzione sarà disponibile alla fine dell’esame.').waitFor();
  const quizPath=new URL(page.url()).hash.split('/').at(-1);
  const exam=await page.evaluate(id=>globalThis.NeuroStudyPages.api('/quizzes/'+id),quizPath);
  assert.equal('correct' in exam.questions[0],false);assert.equal('correct' in Object.values(exam.answers)[0],false);
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Concludi sessione'}).click();await page.getByRole('heading',{name:'Riparti da ciò che hai imparato.'}).waitFor();
  await page.getByRole('button',{name:'Crea flashcard'}).click();await page.getByRole('button',{name:'Conferma e crea flashcard'}).click();
  await page.getByRole('link',{name:'Flashcard',exact:true}).click();await page.getByRole('button',{name:'Inizia il ripasso'}).click();await page.locator('#review-start-form button').click();
  await page.getByRole('button',{name:'Mostra la risposta'}).click();await page.getByRole('button',{name:'Bene · intervallo adattivo'}).click();await page.getByRole('heading',{name:'Un altro passo avanti.'}).waitFor();
  // Actual Office and PDF extraction happens in the browser without upload requests.
  for(const name of ['appunti.docx','appunti.pptx','appunti.pdf']){
    const data=fs.readFileSync(path.join(temporary,name)).toString('base64');
    const doc=await page.evaluate(async({name,data})=>{
      const form=new FormData();form.set('file',new File([Uint8Array.from(atob(data),c=>c.charCodeAt(0))],name));form.set('topic','Parser browser');
      return globalThis.NeuroStudyPages.api('/documents',form);
    },{name,data});
    assert.ok(doc.sections.some(s=>s.text.includes('miastenia')),name+' testo estratto');
  }
  const blank=fs.readFileSync(path.join(temporary,'scansione.pdf')).toString('base64');
  const scanError=await page.evaluate(async data=>{const f=new FormData();f.set('file',new File([Uint8Array.from(atob(data),c=>c.charCodeAt(0))],'scan.pdf'));try{await globalThis.NeuroStudyPages.api('/documents',f);return '';}catch(e){return e.message;}},blank);
  assert.ok(scanError.includes('OCR'));
  const savedCards=await page.evaluate(()=>globalThis.NeuroStudyPages.api('/cards'));
  assert.equal(savedCards[0].reviews,1);assert.ok(new Date(savedCards[0].due)>new Date());
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'Esporta backup cifrato',exact:true}).click();
  const backup=path.join(temporary,'backup.json');await (await download).saveAs(backup);
  const encrypted=JSON.parse(fs.readFileSync(backup,'utf8'));
  assert.equal(encrypted.format,'neurostudy-encrypted-backup');assert.equal(JSON.stringify(encrypted).includes('Appunti Pages'),false);
  await page.reload();await page.getByLabel('Password',{exact:true}).waitFor();
  await page.getByLabel('Password',{exact:true}).fill('pages-password-tests-123');await page.locator('#login-form button').click();await page.getByRole('heading',{name:'Un altro passo avanti.'}).waitFor();
  assert.equal((await page.evaluate(()=>globalThis.NeuroStudyPages.api('/cards')))[0].due,savedCards[0].due);
  const phoneContext=await browser.newContext({...devices['Pixel 7'],locale:'it-IT'});
  const phone=await phoneContext.newPage();phone.on('pageerror',e=>errors.push(e.message));phone.setDefaultTimeout(20000);
  await phone.goto(base);await phone.getByRole('button',{name:'Importa un backup cifrato'}).click();await phone.locator('input[type=file]').setInputFiles(backup);
  await phone.locator('#pages-import-form [name=password]').fill('wrong-password-tests-123');await phone.locator('[name=replace]').check();await phone.getByRole('button',{name:'Verifica password e importa'}).tap();
  await phone.getByText('Password del backup errata o file danneggiato.').waitFor();
  assert.equal((await phone.evaluate(()=>globalThis.NeuroStudyPages.api('/status'))).setup_required,true);
  await phone.locator('#pages-import-form [name=password]').fill('pages-password-tests-123');await phone.getByRole('button',{name:'Verifica password e importa'}).tap();
  await phone.getByRole('heading',{name:'Ogni giorno, un passo avanti.'}).waitFor();
  assert.equal((await phone.evaluate(()=>globalThis.NeuroStudyPages.api('/documents'))).length,4);
  assert.equal((await phone.evaluate(()=>globalThis.NeuroStudyPages.api('/cards')))[0].reviews,1);
  await phone.getByRole('link',{name:'Casi clinici',exact:true}).tap();await phone.locator('[name=topic]').selectOption('Malattie neuromuscolari');await phone.getByRole('button',{name:'Apri il caso'}).tap();
  await phone.getByRole('heading',{name:'Un paziente. Il tuo ragionamento.'}).waitFor();
  for(const label of ['Esordio e andamento dei sintomi','Valutazione respiratoria e capacità vitale','Esame neurologico completo','Anticorpi anti-recettore ACh e anti-MuSK','Stimolazione nervosa ripetitiva / EMG']){
    const before=await phone.locator('.event').count();await phone.getByRole('button',{name:label,exact:true}).tap();await phone.locator('.event').nth(before).waitFor();
  }
  const caseId=new URL(phone.url()).hash.split('/').at(-1);
  const first=await phone.locator('.event .response').first().textContent();
  await phone.getByLabel('Chiedi al paziente o richiedi un accertamento').fill('Da quanto tempo sono presenti i sintomi?');await phone.getByRole('button',{name:'Invia richiesta'}).tap();await phone.locator('.event').nth(5).waitFor();
  assert.equal(await phone.locator('.event .response').last().textContent(),first);
  await phone.getByLabel('Ipotesi, localizzazione e differenziali').fill('Appunti persistenti in Pages Android');await phone.getByRole('link',{name:'Salva ed esci'}).tap();
  await phone.getByRole('heading',{name:'Ogni giorno, un passo avanti.'}).waitFor();await phone.locator(`a[href="#session/case/${caseId}"]`).tap();await phone.locator('#case-notes').waitFor();
  assert.equal(await phone.locator('#case-notes').inputValue(),'Appunti persistenti in Pages Android');
  await phone.getByRole('button',{name:'Concludi il caso'}).tap();await phone.getByLabel('Diagnosi principale').fill('miastenia gravis');await phone.getByLabel('Motivazione basata sui dati raccolti').fill('Affaticabilita fluttuante con ptosi e decremento');await phone.getByLabel('Localizzazione neurologica').fill('Giunzione neuromuscolare');await phone.getByLabel('Diagnosi alternative').fill('Lambert-Eaton');
  await phone.getByRole('button',{name:'Consegna e scopri il feedback'}).tap();await phone.getByRole('heading',{name:'Guarda il percorso, oltre la risposta.'}).waitFor();
  const assessment=await phone.evaluate(id=>globalThis.NeuroStudyPages.api('/cases/'+id),caseId);assert.equal(assessment.assessment.stars,5);
  assert.equal('dossier' in assessment,false);
  await phone.getByRole('link',{name:'Panoramica',exact:true}).tap();await phone.getByRole('heading',{name:'Ogni giorno, un passo avanti.'}).waitFor();
  assert.equal(await phone.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  fs.mkdirSync('test-results',{recursive:true});await phone.screenshot({path:'test-results/pages-android.png',fullPage:true});
  assert.equal(requests.some(r=>r.startsWith('/api')||r.startsWith('/static')),false);
  assert.deepEqual(errors,[]);
  console.log('Pages: sottopercorso /Study/, TXT/DOCX/PPTX/PDF, quiz esame, flashcard e scadenze, archivio cifrato, reload, backup Android, caso e ripresa: OK. Nessun server API.');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();await new Promise(r=>server.close(r));fs.rmSync(temporary,{recursive:true,force:true});});
