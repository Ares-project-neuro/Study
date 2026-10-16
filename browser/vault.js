// Nothing is sent to an API: one AES-GCM encrypted vault per Pages project path.
const name='neurostudy-pages:'+new URL('.',document.baseURI).pathname;
const encode=s=>new TextEncoder().encode(s);
const decode=b=>new TextDecoder().decode(b);
const b64=bytes=>{let s='';for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(s);};
const unb64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
let key=null,state=null;
const empty=()=>({version:1,document:[],question:[],card:[],quiz:[],review:[],rating:[],case:[],report:[],settings:{daily_limit:30,daily_goal:20,timezone:'Europe/Rome'}});
let dbPromise;
function db() {
  if(!dbPromise)dbPromise=new Promise((resolve,reject)=>{
    if(!globalThis.indexedDB||!globalThis.crypto?.subtle){reject(Error('Serve un browser aggiornato con archiviazione locale e HTTPS.'));return;}
    const req=indexedDB.open(name,1);
    req.onupgradeneeded=()=>req.result.createObjectStore('vault');
    req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(Error('Archiviazione del browser non disponibile. Controlla le impostazioni privacy.'));
  });
  return dbPromise;
}
async function read() {
  const database=await db();
  return new Promise((resolve,reject)=>{
    const tx=database.transaction('vault','readonly'),req=tx.objectStore('vault').get('current');
    req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);
  });
}
async function write(record) {
  const database=await db();
  return new Promise((resolve,reject)=>{
    const tx=database.transaction('vault','readwrite');tx.objectStore('vault').put(record,'current');
    tx.oncomplete=resolve;tx.onerror=()=>reject(Error('Salvataggio non riuscito: spazio del browser insufficiente o archiviazione negata. Esporta un backup.'));tx.onabort=tx.onerror;
  });
}
async function derive(password,salt) {
  const material=await crypto.subtle.importKey('raw',encode(password),'PBKDF2',false,['deriveKey']);
  return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:310000,hash:'SHA-256'},material,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);
}
async function decrypt(record,usedKey) {
  return JSON.parse(decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:unb64(record.iv)},usedKey,unb64(record.ciphertext))));
}
async function encrypt(data,usedKey,salt) {
  const iv=crypto.getRandomValues(new Uint8Array(12));
  return {format:'neurostudy-encrypted-backup',version:1,kdf:'PBKDF2-SHA256-310000',salt,iv:b64(iv),ciphertext:b64(new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv},usedKey,encode(JSON.stringify(data)))))};
}
let queue=Promise.resolve();
function locked(fn) {
  if(navigator.locks)return navigator.locks.request(name,fn);
  const next=queue.then(fn,fn);queue=next.catch(()=>{});return next;
}
export const vault={
  async status(){const record=await read();return {setup_required:!record,authenticated:!!key,ai:false,pages:true};},
  async login(password){
    if(typeof password!=='string'||password.length<10||password.length>256)throw Error('Password da 10 a 256 caratteri.');
    return locked(async()=>{
      const record=await read();
      if(record){
        const candidate=await derive(password,unb64(record.salt));
        let restored;try{restored=await decrypt(record,candidate);}catch{throw Error('Password non corretta o archivio illeggibile. Nessun dato è stato cancellato.');}
        state=restored;key=candidate;
      } else {
        const salt=b64(crypto.getRandomValues(new Uint8Array(16))),candidate=await derive(password,unb64(salt));
        const initial=empty();await write(await encrypt(initial,candidate,salt));key=candidate;state=initial;
        if(navigator.storage?.persist)navigator.storage.persist().catch(()=>{});
      }
      return {ok:true};
    });
  },
  logout(){key=null;state=null;return {ok:true};},
  async access(fn,mutating=false){
    if(!key)throw Error('Sblocca il tuo archivio per continuare.');
    return locked(async()=>{
      const record=await read();
      try{state=await decrypt(record,key);}catch{key=null;state=null;throw Error('Archivio sostituito da un’altra scheda. Ricarica e sblocca con la password del backup.');}
      const result=await fn(state);
      if(mutating)await write(await encrypt(state,key,record.salt));
      return structuredClone(result);
    });
  },
  async backup(){if(!key)throw Error('Sblocca prima l’archivio.');return read();},
  async restore(file,password){
    if(!file||file.size>100*1024*1024)throw Error('Backup troppo grande: massimo 100 MB.');
    let record;try{record=JSON.parse(await file.text());}catch{throw Error('File backup non valido.');}
    if(record.format!=='neurostudy-encrypted-backup'||record.version!==1||record.kdf!=='PBKDF2-SHA256-310000'||![record.salt,record.iv,record.ciphertext].every(v=>typeof v==='string'))throw Error('Formato backup non supportato.');
    const candidate=await derive(password,unb64(record.salt));
    let restored;try{restored=await decrypt(record,candidate);}catch{throw Error('Password del backup errata o file danneggiato.');}
    if(restored.version!==1||!['document','question','card','quiz','review','rating','case','report'].every(k=>Array.isArray(restored[k]))||!restored.settings)throw Error('Dati del backup non validi.');
    await locked(()=>write(record));key=candidate;state=restored;return {ok:true};
  }
};
