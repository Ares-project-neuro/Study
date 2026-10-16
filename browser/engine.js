import {vault} from './vault.js';
import {extract} from './documents.js';
import catalog from './cases.json';

const now=()=>new Date().toISOString();
const norm=s=>String(s||'').normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase();
const day=s=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Rome'}).format(s?new Date(s):new Date());
const addDays=d=>new Date(Date.now()+d*86400000).toISOString();
const actions=Object.fromEntries(catalog.actions.map(a=>[a[0],a]));
const requireThat=(condition,message)=>{if(!condition)throw Error(message);};
const get=(s,k,id)=>{const i=s[k].find(i=>i.id===id);requireThat(i,'Elemento non trovato.');return i;};
const save=(s,k,data)=>{const old=data.id?s[k].find(i=>i.id===data.id):null;const item={...data,id:data.id||crypto.randomUUID(),created_at:old?.created_at||data.created_at||now(),updated_at:now()};if(old)s[k][s[k].indexOf(old)]=item;else s[k].unshift(item);return item;};
const remove=(s,k,id)=>{s[k]=s[k].filter(i=>i.id!==id);};
const source=(d,section,quote)=>({document_id:d.id,document_name:d.name,revision:d.revision,section_id:section.id,label:section.label,quote:quote||section.text.slice(0,700),origin:d.demo?'demo':'materiale utente'});
const shuffle=a=>a.map(v=>[Math.random(),v]).sort((a,b)=>a[0]-b[0]).map(p=>p[1]);
const quizPublic=q=>{
  const result=structuredClone(q);
  if(!q.finished_at){
    if(q.mode==='exam')for(const a of Object.values(result.answers))delete a.correct;
    for(const i of result.questions)if(q.mode==='exam'||!q.answers[i.id])for(const k of ['correct','explanation','option_explanations','sources'])delete i[k];
  }
  return result;
};
function reviewPublic(s,r){
  const result=structuredClone(r);result.cards=[];
  for(const id of r.card_ids){const card=s.card.find(c=>c.id===id);if(!card)continue;const c=structuredClone(card);
    if(!r.revealed.includes(id)){c.front=c.front.replace(/\{\{.+?\}\}/g,'[…]');for(const k of ['back','extra','sources'])delete c[k];}
    result.cards.push(c);
  }
  return result;
}
function casePublic(c){
  const {dossier,...result}=structuredClone(c);
  Object.assign(result,{arrival:dossier.arrival,source:dossier.source,rubric:dossier.rubric,thresholds:dossier.thresholds});
  if(c.complexity==='base')result.support='Ricostruisci esordio e andamento, valuta i parametri e localizza il possibile deficit. I menu non indicano le azioni corrette.';
  return result;
}
function validQuestion(q){
  requireThat(typeof q.prompt==='string'&&q.prompt.trim().length>=10,'La domanda deve avere almeno 10 caratteri.');
  requireThat(Array.isArray(q.options)&&q.options.length>=2&&q.options.length<=6&&q.options.every(o=>typeof o==='string'&&o.trim())&&new Set(q.options.map(o=>o.trim().toLowerCase())).size===q.options.length,'Servono da 2 a 6 alternative distinte.');
  requireThat(Array.isArray(q.correct)&&q.correct.length&&q.correct.every(i=>Number.isInteger(i)&&i>=0&&i<q.options.length)&&new Set(q.correct).size===q.correct.length&&q.correct.length<q.options.length,'Indici delle risposte corrette non validi.');
  requireThat(['single','multiple'].includes(q.type)&&(q.type!=='single'||q.correct.length===1),'Tipo di risposta non valido.');
  requireThat(typeof q.explanation==='string'&&Array.isArray(q.option_explanations)&&q.option_explanations.length===q.options.length,'Serve una spiegazione per ogni alternativa.');
}
function validCard(c){
  requireThat(typeof c.front==='string'&&c.front.trim().length>=3&&typeof c.back==='string'&&c.back.trim(),'Inserisci domanda e risposta.');
  requireThat(['qa','cloze'].includes(c.type)&&(c.type!=='cloze'||/\{\{.+?\}\}/.test(c.front)),'Il completamento richiede {{risposta}}.');
}
function evaluate(c,b){
  const d=c.dossier,requested=[...new Set(c.events.filter(e=>e.action).map(e=>e.action))],seen=new Set(requested);
  if(['cranial','motor','sensory','reflex','coordination'].every(a=>seen.has(a)))seen.add('neuro');
  const round=n=>Math.round(n*10)/10;
  const info=round(20*d.information.filter(a=>seen.has(a)).length/d.information.length);
  const collected=norm(d.arrival+' '+c.events.filter(e=>e.action).map(e=>e.response).join(' '));
  const evidence=d.evidence.filter(w=>norm(b.rationale).includes(norm(w))&&collected.includes(norm(w)));
  const located=d.localization.some(w=>norm(b.localization).includes(norm(w)));
  const alternatives=(b.alternatives||'').split(/[,;\n]/).filter(s=>s.trim().length>3);
  const reasoning=round(12*Math.min(1,evidence.length/2)+(located?8:!d.require_localization?4:0)+5*Math.min(1,alternatives.length/d.expected_alternatives));
  const relevant=new Set([...d.information,...d.essential,...d.useful,...d.priority]);
  const unnecessary=requested.filter(a=>!relevant.has(a));
  const first=requested.find(a=>['Imaging','Laboratorio','Neurofisiologia','Approfondimenti','Consulenze'].includes(actions[a][1]));
  const priority=d.priority.includes(first)||(first==='blood'&&d.topic==='Patologie cerebrovascolari');
  const investigations=round(Math.max(0,20*d.essential.filter(a=>seen.has(a)).length/d.essential.length+(priority?5:0)-Math.min(5,unnecessary.length*1.5)));
  const correct=d.aliases.some(a=>norm(b.diagnosis).includes(norm(a)))&&!/\b(non|escludo|esclusa|escludere)\b/.test(norm(b.diagnosis));
  const diagnosis=(correct?20:0)+round(10*Math.min(1,evidence.length/2));
  const scores=[info,reasoning,investigations,diagnosis],total=round(scores.reduce((a,b)=>a+b,0));
  return {total,stars:catalog.thresholds.filter(t=>total>=t).length,dimensions:catalog.rubric.map((r,i)=>({...r,score:scores[i]})),
    diagnosis:d.diagnosis,correct,expected_alternatives:d.differentials,
    strengths:requested.filter(a=>relevant.has(a)).map(a=>actions[a][2]),
    omissions:[...d.information,...d.essential].filter(a=>!seen.has(a)).map(a=>actions[a][2]),
    unnecessary:unnecessary.map(a=>({label:actions[a][2],reason:'Non aggiunge informazioni al percorso essenziale di questo dossier; un’alternativa motivata può richiedere revisione.'})),
    pathway:d.pathway,topic:d.topic,hints_used:c.hints.length,priority_met:priority,evidence_terms:evidence,engine:'euristico locale nel browser',
    limits:'Valutazione didattica euristica: riconosce azioni, sinonimi e parole chiave predefiniti, ma non comprende semanticamente i differenziali. La raccolta dati insufficiente non consente un giudizio clinico. I dossier statici sono ispezionabili nel codice: non è un esame protetto. Segnala percorsi alternativi non riconosciuti.',
    explanation:`Informazioni: frazione di azioni attese ×20. Ragionamento: 12 per due reperti motivati e raccolti, 8 per localizzazione (4 se facoltativa assente), 5 per ${d.expected_alternatives} alternative. Accertamenti: frazione essenziali ×20 +5 per priorità −1,5 per superfluo (max −5). Diagnosi: 20 per sinonimo riconosciuto +10 per due reperti motivati e raccolti. Nessuna penalità per aiuti.`};
}
function dashboard(s){
  const metrics={};
  for(const quiz of s.quiz)for(const q of quiz.questions){const a=quiz.answers[q.id];if(!a||q.demo)continue;const m=metrics[q.topic]??={attempts:0,errors:0};m.attempts++;m.errors+=!a.correct;}
  const due=s.card.filter(c=>!c.suspended&&!c.demo&&!c.review_required&&c.due<=now());
  const summary=(k,kind)=>s[k].filter(i=>!i.finished_at).map(i=>({id:i.id,kind,created_at:i.created_at}));
  const history=(k,kind)=>s[k].filter(i=>i.finished_at).map(i=>({id:i.id,kind,created_at:i.created_at}));
  return {due:due.length,overdue:due.filter(c=>c.reviews&&day(c.due)<day()).length,new:due.filter(c=>!c.reviews).length,
    today_due:due.filter(c=>c.reviews&&day(c.due)===day()).length,metrics,rated_today:s.rating.filter(r=>r.day===day()&&!r.demo).length,settings:s.settings,
    assessments:s.case.filter(c=>c.assessment).map(c=>({id:c.id,at:c.finished_at,demo:true,topic:c.assessment.topic,dimensions:c.assessment.dimensions,total:c.assessment.total})),
    resume:[...summary('quiz','quiz'),...summary('review','review'),...summary('case','case')],history:[...history('quiz','quiz'),...history('case','case')],
    needs_review:[...s.card,...s.question].filter(c=>c.review_required).length};
}
async function generate(s,b){
  requireThat(b.engine!=='ai','GitHub Pages non esegue il servizio IA: usa la generazione locale o la versione Python con IA configurata.');
  requireThat(['question','card'].includes(b.kind)&&b.document_ids?.length,'Scegli tipo e materiali.');
  const count=Math.min(30,Math.max(1,Number(b.count)||5)),sentences=[];
  for(const id of b.document_ids){const d=get(s,'document',id);for(const section of d.sections){
    if(b.sections?.[id]&&!b.sections[id].includes(section.id))continue;
    for(const sentence of section.text.split(/(?<=[.!?])\s+|\n/)){
      const words=sentence.match(/[\p{L}\p{N}_-]{6,}/gu)||[];
      if(sentence.length>=40&&sentence.length<=700&&words.length)sentences.push({d,section,sentence,word:words.sort((a,b)=>b.length-a.length)[0]});
    }
  }}
  const vocabulary=[...new Set(sentences.flatMap(c=>c.sentence.match(/[\p{L}\p{N}_-]{6,}/gu)||[]))];
  const existing=new Set(s[b.kind].filter(i=>i.id!==b.replace_id).map(i=>norm(i.prompt||i.front)));
  const items=[],warnings=['Richiamo letterale locale: difficoltà non adattiva, contenuti da revisionare. Non verifica correttezza clinica o contraddizioni.'];
  for(const c of sentences){
    if(items.length>=count)break;
    const item={topic:c.d.topic,sources:[source(c.d,c.section,c.sentence)],origin:'extractive',review_required:true,review_reason:'Controlla chiarezza e supporto della fonte.',demo:!!c.d.demo,difficulty:b.difficulty||'base'};
    if(b.kind==='card')Object.assign(item,{front:c.sentence.replace(c.word,`{{${c.word}}}`),back:c.word,extra:c.sentence,type:'cloze',due:now(),interval:0,ease:2.5,reviews:0,suspended:false});
    else {
      const wrong=vocabulary.filter(w=>norm(w)!==norm(c.word)).slice(0,3);if(wrong.length<2)continue;
      const options=shuffle([...wrong,c.word]);Object.assign(item,{prompt:`Completa il passaggio del materiale: «${c.sentence.replace(c.word,'____')}»`,type:'single',options,correct:[options.indexOf(c.word)],explanation:'La fonte riporta: '+c.sentence,
        option_explanations:options.map(w=>w===c.word?'È il termine presente nella fonte.':'Non è il termine usato in questo passaggio; non implica che sia clinicamente falso in altri contesti.')});
    }
    const key=norm(item.prompt||item.front);if(existing.has(key))continue;existing.add(key);items.push(save(s,b.kind,item));
  }
  if(items.length<count)warnings.push(`Salvati ${items.length} contenuti su ${count}: fonti insufficienti o duplicati, senza riempimenti inventati.`);
  return {items,warnings};
}
function demo(s){
  if(s.document.some(d=>d.demo))return {ok:true,message:'Dati demo già presenti'};
  const text='La miastenia gravis presenta debolezza fluttuante e affaticabilità muscolare. La sensibilità è generalmente conservata nella miastenia gravis. La ptosi può peggiorare dopo sguardo prolungato verso l’alto.';
  const doc=save(s,'document',{name:'DEMO · Giunzione neuromuscolare.txt',topic:'Malattie neuromuscolari',course:'Demo redazionale',demo:true,revision:1,warnings:['Materiale sintetico redazionale, non caricato dall’utente né revisionato clinicamente.'],sections:[{id:'1',label:'Sezione dimostrativa',text}]});
  save(s,'question',{prompt:'Quale funzione è generalmente conservata nella miastenia gravis secondo la demo?',type:'single',options:['Sensibilità','Forza dopo attività ripetuta','Resistenza alla fatica oculare','Resistenza alla fatica bulbare'],correct:[0],explanation:'Il materiale descrive sensibilità conservata e debolezza affaticabile.',option_explanations:['Descritta come conservata.','La forza può affaticarsi.','I muscoli oculari possono affaticarsi.','I muscoli bulbari possono affaticarsi.'],topic:doc.topic,difficulty:'base',demo:true,origin:'demo',review_required:false,sources:[source(doc,doc.sections[0])]});
  save(s,'card',{front:'Nella miastenia gravis, come è generalmente la sensibilità?',back:'Conservata.',extra:'Contenuto demo didattico, da revisionare.',type:'qa',topic:doc.topic,sources:[source(doc,doc.sections[0])],demo:true,origin:'demo',review_required:false,suspended:false,due:now(),interval:0,ease:2.5,reviews:0});
  return {ok:true,message:'Creati materiale, quiz e flashcard demo, separati dai tuoi dati'};
}

async function dispatch(s,path,b,method){
  const [group,id,command,extra]=path.slice(1).split('/');
  if(group==='settings'){
    if(method==='PUT'){requireThat(Number.isInteger(b.daily_limit)&&b.daily_limit>=1&&b.daily_limit<=200&&Number.isInteger(b.daily_goal)&&b.daily_goal>=1&&b.daily_goal<=240,'Obiettivo o carico giornaliero non valido.');Object.assign(s.settings,b);}return s.settings;
  }
  if(group==='documents'){
    if(method==='GET')return s.document;
    if(method==='POST'){
      const file=b.get('file'),previous=b.get('document_id')?get(s,'document',b.get('document_id')):null;
      const {sections,warnings}=await extract(file);
      const doc=save(s,'document',{...(previous||{}),name:file.name,topic:b.get('topic')||'Neurologia',course:b.get('course')||'',sections,warnings,revision:(previous?.revision||0)+1,demo:false});
      if(previous&&b.get('mark_linked'))for(const k of ['question','card'])for(const i of s[k])if(i.sources?.some(r=>r.document_id===doc.id))Object.assign(i,{review_required:true,review_reason:'Fonte aggiornata: controlla o rigenera il contenuto.'});
      return doc;
    }
    if(method==='DELETE'){
      get(s,'document',id);remove(s,'document',id);for(const k of ['question','card'])for(const i of s[k])if(i.sources?.some(r=>r.document_id===id))Object.assign(i,{review_required:true,review_reason:'Fonte eliminata; la citazione storica resta nel contenuto e nelle sessioni passate.'});return {ok:true};
    }
  }
  if(group==='generate')return generate(s,b);
  if(group==='questions'){
    if(method==='GET')return s.question;
    const q=get(s,'question',id);
    if(method==='DELETE'){remove(s,'question',id);return {ok:true};}
    if(command==='bookmark'){q.bookmarked=!q.bookmarked;return q;}
    if(method==='PUT'){validQuestion(b);const {prompt,options,correct,type,explanation,option_explanations,topic,difficulty,review_required}=b;return save(s,'question',{...q,prompt,options,correct,type,explanation,option_explanations,topic,difficulty,review_required,version:(q.version||1)+1});}
  }
  if(group==='reports'){
    requireThat(['question','card','case'].includes(b.kind)&&b.text?.length>=5,'Segnalazione non valida.');const item=get(s,b.kind,b.target_id);if(b.kind!=='case')Object.assign(item,{review_required:true,review_reason:b.text});return save(s,'report',b);
  }
  if(group==='quizzes'){
    if(!id){
      requireThat(['training','exam'].includes(b.mode)&&['mixed','new','wrong','saved'].includes(b.filter),'Modalità non valida.');
      const history={};for(const q of s.quiz)for(const [qid,a] of Object.entries(q.answers)){const m=history[qid]??={attempts:0,errors:0};m.attempts++;m.errors+=!a.correct;}
      const pool=s.question.filter(q=>{
        const m=history[q.id]||{attempts:0,errors:0};
        return (!q.demo||b.include_demo)&&(!q.review_required||b.include_review)&&(!b.topics?.length||b.topics.includes(q.topic))&&(!b.document_ids?.length||q.sources?.some(r=>b.document_ids.includes(r.document_id)))&&(!b.difficulty||b.difficulty==='tutte'||b.difficulty===q.difficulty)&&!(b.filter==='new'&&m.attempts||b.filter==='wrong'&&!m.errors||b.filter==='saved'&&!q.bookmarked);
      }).map(q=>{const m=history[q.id]||{attempts:0,errors:0};return [Math.random()**(1/(1+3*m.errors/Math.max(1,m.attempts))),q];}).sort((a,b)=>b[0]-a[0]);
      requireThat(pool.length,'Nessuna domanda corrisponde ai filtri: genera, approva o includi demo / da revisionare.');
      const count=Math.min(100,Math.max(1,Number(b.count)||10));
      return quizPublic(save(s,'quiz',{...b,questions:structuredClone(pool.slice(0,count).map(p=>p[1])),answers:{},deadline:b.minutes?addDays(b.minutes/1440):null}));
    }
    const q=get(s,'quiz',id);
    if(command==='finish'){q.finished_at??=now();return quizPublic(q);}
    if(command==='answer'){
      requireThat(!q.finished_at,'Sessione già conclusa.');requireThat(!q.deadline||q.deadline>now(),'Tempo scaduto: concludi la sessione.');
      const item=q.questions.find(i=>i.id===b.question_id);requireThat(item,'Domanda non presente.');requireThat(!q.answers[item.id],'Risposta già registrata.');
      requireThat(b.selected?.length&&b.selected.every(i=>Number.isInteger(i)&&i>=0&&i<item.options.length)&&(item.type!=='single'||new Set(b.selected).size===1),'Selezione non valida.');
      q.answers[item.id]={selected:b.selected,correct:JSON.stringify([...new Set(b.selected)].sort())===JSON.stringify([...item.correct].sort()),at:now()};
    }
    return quizPublic(q);
  }
  if(group==='cards'){
    if(method==='GET')return s.card;
    if(method==='DELETE'){remove(s,'card',id);return {ok:true};}
    validCard(b);
    const {front,back,extra='',topic='Neurologia',type,suspended=false,review_required=false}=b;
    if(id)return save(s,'card',{...get(s,'card',id),front,back,extra,topic,type,suspended,review_required});
    const q=b.question_id?get(s,'question',b.question_id):null;
    return save(s,'card',{front,back,extra,topic,type,suspended,review_required:q?!!q.review_required:review_required,sources:q?.sources||[],demo:!!q?.demo,origin:q?'quiz':'manuale',due:now(),interval:0,ease:2.5,reviews:0});
  }
  if(group==='reviews'){
    if(!id){
      const limit=Math.max(0,s.settings.daily_limit-s.rating.filter(r=>r.day===day()).length);
      const pool=s.card.filter(c=>!c.suspended&&c.due<=now()&&(!c.demo||b.include_demo)&&(!c.review_required||b.include_review)&&(!b.topic||b.topic===c.topic)&&(!b.document_id||c.sources?.some(r=>r.document_id===b.document_id))).sort((a,b)=>Number(!a.reviews)-Number(!b.reviews)||a.due.localeCompare(b.due));
      requireThat(pool.length&&limit,'Nessuna scheda dovuta o carico giornaliero raggiunto.');
      return reviewPublic(s,save(s,'review',{card_ids:pool.slice(0,limit).map(c=>c.id),ratings:{},revealed:[]}));
    }
    const r=get(s,'review',id);
    if(command==='reveal'){requireThat(r.card_ids.includes(extra),'Scheda non presente.');if(!r.revealed.includes(extra))r.revealed.push(extra);}
    if(command==='rate'){
      requireThat(['again','hard','good','easy'].includes(b.grade),'Valutazione non valida.');requireThat(r.revealed.includes(b.card_id)&&!r.ratings[b.card_id],'Rivela prima la risposta o scheda già valutata.');
      const c=get(s,'card',b.card_id);requireThat(!c.suspended&&c.due<=now(),'Scheda sospesa o già ripassata in un’altra sessione.');
      requireThat(s.rating.filter(r=>r.day===day()).length<s.settings.daily_limit,'Carico giornaliero raggiunto.');
      let interval=c.interval||0,ease=c.ease||2.5;
      if(b.grade==='again'){interval=10/1440;ease=Math.max(1.3,ease-.2);}
      if(b.grade==='hard'){interval=Math.max(1,interval*1.2);ease=Math.max(1.3,ease-.15);}
      if(b.grade==='good')interval=!c.reviews?1:Math.max(2,interval*ease);
      if(b.grade==='easy'){interval=Math.max(4,interval*ease*1.3);ease=Math.min(3.2,ease+.15);}
      Object.assign(c,{interval:Math.round(interval*1e5)/1e5,ease,reviews:c.reviews+1,due:addDays(interval)});
      r.ratings[c.id]={grade:b.grade,due:c.due};if(Object.keys(r.ratings).length===r.card_ids.length)r.finished_at=now();
      save(s,'rating',{card_id:c.id,grade:b.grade,day:day(),due:c.due,demo:c.demo});
    }
    return reviewPublic(s,r);
  }
  if(group==='case-options')return {topics:catalog.templates.map(d=>d.topic),actions:catalog.actions.map(a=>({id:a[0],category:a[1],label:a[2]})),rubric:catalog.rubric,thresholds:catalog.thresholds,scoring:catalog.scoring};
  if(group==='cases'){
    if(!id){
      requireThat(b.engine==='demo','IA non disponibile su GitHub Pages. Usa i dossier demo o la versione Python con servizio IA.');
      const choices=catalog.templates.filter(d=>!b.topic||b.topic===d.topic);requireThat(choices.length,'Argomento non disponibile.');
      const d=structuredClone(choices[Math.floor(Math.random()*choices.length)]);
      for(const a of Object.keys(actions))d.reports[a]??='Dato non disponibile nel dossier: questo accertamento non è stato simulato; non equivale a un risultato normale.';
      Object.assign(d,{source:'Demo redazionale locale: paziente fittizio, non tratto dai tuoi materiali. Su Pages il dossier è contenuto nei file statici ed è ispezionabile; uso didattico, non esame protetto.',rubric:catalog.rubric,thresholds:catalog.thresholds,
        expected_alternatives:b.level==='specializzando'||b.complexity==='avanzata'?2:1,require_localization:b.level==='specializzando'||b.complexity!=='base'});
      return casePublic(save(s,'case',{...b,dossier:d,events:[],hints:[],notes:'',deadline:b.minutes?addDays(b.minutes/1440):null}));
    }
    const c=get(s,'case',id);
    if(command==='notes'){c.notes=String(b.notes||'').slice(0,20000);return {ok:true};}
    if(command==='finish'){
      if(!c.finished_at){requireThat(b.diagnosis?.trim().length>=2,'Inserisci la diagnosi.');c.submission={diagnosis:b.diagnosis,rationale:b.rationale||'',localization:b.localization||'',alternatives:b.alternatives||''};c.assessment=evaluate(c,c.submission);c.finished_at=now();}return casePublic(c);
    }
    if(command==='actions'||command==='hint')requireThat(!c.finished_at,'Caso già concluso.');
    if(command==='actions'){
      requireThat(!c.deadline||c.deadline>now(),'Tempo scaduto: consegna il caso.');
      const text=norm(b.text),matches=catalog.actions.filter(a=>a[3].some(w=>text.includes(norm(w))));
      const hypothesis=['ipotizzo','penso che','diagnosi','potrebbe essere','sospetto'].some(w=>text.includes(w));
      const action=b.action||(!hypothesis&&matches.length===1?matches[0][0]:null);
      if(action)requireThat(actions[action],'Azione non valida.');
      const event={at:now(),request:b.text||(action?actions[action][2]:''),kind:action?'action':hypothesis?'hypothesis':'clarify'};
      if(action)Object.assign(event,{action,response:c.dossier.reports[action]});
      else event.response=hypothesis?'Ipotesi annotata, senza conferma prima della consegna.':'Specifica una sola richiesta dal menu oppure scrivi “ipotizzo …”. Nessun esame è stato assegnato.';
      c.events.push(event);
    }
    if(command==='hint'){
      requireThat(c.mode==='guided'&&c.hints.length<3,'Suggerimenti non disponibili.');
      const hints=['Ricostruisci esordio, andamento e sintomi associati.','Confronta i reperti neurologici con la tua localizzazione.','Valuta se hai raccolto: '+c.dossier.information.map(a=>actions[a][2]).join(', ')];c.hints.push(hints[c.hints.length]);
    }
    return casePublic(c);
  }
  if(group==='dashboard')return dashboard(s);
  if(group==='demo')return demo(s);
  if(group==='export')return {version:1,exported_at:now(),documents:s.document,questions:s.question,cards:s.card,quizzes:s.quiz.map(quizPublic),reviews:s.review.map(r=>reviewPublic(s,r)),ratings:s.rating,cases:s.case.map(casePublic),settings:s.settings,reports:s.report};
  throw Error('Operazione non disponibile nella versione Pages.');
}
export async function pagesApi(path,body,method){
  method??=body===undefined?'GET':'POST';
  if(path==='/status')return vault.status();
  if(path==='/login')return vault.login(body.password);
  if(path==='/logout')return vault.logout();
  return vault.access(s=>dispatch(s,path,body||{},method),method!=='GET');
}
export {vault};
