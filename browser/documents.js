import JSZip from 'jszip';
import * as pdfjs from 'pdfjs-dist';

export async function extract(file) {
  if(!file || file.size>20*1024*1024)throw Error('Scegli un documento di massimo 20 MB.');
  const ext=file.name.toLowerCase().split('.').pop();
  const sections=[],warnings=[];
  const add=(label,text)=>{
    text=(text||'').replace(/[ \t]+/g,' ').trim();
    if(text)sections.push({id:String(sections.length+1),label,text});
    else warnings.push(`${label}: nessun testo estratto; potrebbe servire OCR.`);
  };
  const data=await file.arrayBuffer();
  try {
    if(['txt','md'].includes(ext)) {
      const text=new TextDecoder('utf-8',{fatal:true}).decode(data);
      text.split(/\n\s*\n/).filter(s=>s.trim()).forEach((s,i)=>add(`Paragrafo ${i+1}`,s));
    } else if(ext==='pdf') {
      pdfjs.GlobalWorkerOptions.workerSrc=new URL('./pdf/pdf.worker.min.mjs',document.baseURI).href;
      const loading=pdfjs.getDocument({data,cMapUrl:new URL('./pdf/cmaps/',document.baseURI).href,
        cMapPacked:true,standardFontDataUrl:new URL('./pdf/standard_fonts/',document.baseURI).href,
        wasmUrl:new URL('./pdf/wasm/',document.baseURI).href,isEvalSupported:false});
      try {
        const pdf=await loading.promise;
        if(pdf.numPages>600)throw Error('Massimo 600 pagine per PDF.');
        for(let i=1;i<=pdf.numPages;i++) {
          try {
            const page=await pdf.getPage(i),content=await page.getTextContent();
            add(`Pagina ${i}`,content.items.map(t=>t.str+(t.hasEOL?'\n':' ')).join(''));
            page.cleanup();
          } catch(e) {warnings.push(`Pagina ${i}: estrazione fallita, parte non elaborata.`);}
        }
      } finally {await loading.destroy();}
      warnings.push('PDF: immagini, scansioni e formule non sono interpretate; verifica ordine del testo e tabelle. OCR non incluso.');
    } else if(['docx','pptx'].includes(ext)) {
      const zip=await JSZip.loadAsync(data);
      if(Object.values(zip.files).reduce((n,f)=>n+(f._data?.uncompressedSize||0),0)>80*1024*1024)throw Error('Documento decompresso troppo grande: massimo 80 MB.');
      const xml=async name=>{
        const entry=zip.file(name);if(!entry)throw Error('Documento Office incompleto.');
        const text=await entry.async('string');
        if(text.length>8*1024*1024)throw Error('Parte XML troppo grande: suddividi il documento.');
        if(/<!DOCTYPE|<!ENTITY/i.test(text))throw Error('XML con dichiarazioni non supportate.');
        const doc=new DOMParser().parseFromString(text,'application/xml');
        if(doc.querySelector('parsererror'))throw Error('XML illeggibile.');
        return doc;
      };
      const tags=(node,name)=>[...node.getElementsByTagNameNS('*',name)];
      const paragraphs=doc=>tags(doc,'p').map(p=>tags(p,'t').map(t=>t.textContent).join('')).filter(Boolean);
      if(ext==='docx') {
        const doc=await xml('word/document.xml');
        let label='Sezione 1',lines=[];
        for(const p of tags(doc,'p')) {
          const text=tags(p,'t').map(t=>t.textContent).join('');
          const style=tags(p,'pStyle')[0];
          if(style && /heading|titolo/i.test([...style.attributes].map(a=>a.value).join(' ')) && lines.length) {
            add(label,lines.join('\n'));lines=[];label=text||'Sezione';
          }
          if(text)lines.push(text);
        }
        if(lines.length)add(label,lines.join('\n'));
        warnings.push('DOCX: pagine non disponibili; testo delle tabelle linearizzato. Immagini, formule, note, intestazioni e piè di pagina non elaborati.');
      } else {
        const names=Object.keys(zip.files).filter(n=>/^ppt\/slides\/slide\d+\.xml$/.test(n)).sort((a,b)=>Number(a.match(/slide(\d+)/)[1])-Number(b.match(/slide(\d+)/)[1]));
        for(const name of names)add(`Diapositiva ${name.match(/slide(\d+)/)[1]}`,paragraphs(await xml(name)).join('\n'));
        warnings.push('PPTX: solo testo delle diapositive; immagini, grafici, formule, note relatore e animazioni non elaborati.');
      }
    } else throw Error('Formati ammessi: PDF, DOCX, PPTX, TXT UTF-8 e MD.');
  } catch(e) {
    throw Error(`Documento non elaborato: ${e.name==='PasswordException'?'PDF protetto da password.':e.message||'Formato illeggibile.'}`);
  }
  if(!sections.length)throw Error('Nessun testo leggibile. Per scansioni usa OCR prima del caricamento.');
  if(sections.reduce((n,s)=>n+s.text.length,0)>1500000)throw Error('Troppo testo: suddividi il documento.');
  return {sections,warnings};
}
