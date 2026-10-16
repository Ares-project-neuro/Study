import hashlib
import hmac
import json
import os
import random
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import store, documents, ai, cases

app = FastAPI(title='NeuroStudy', docs_url=None, redoc_url=None, openapi_url=None)
STATIC = Path(__file__).parent / 'static'


def auth_config():
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            return store.get('config', 'auth', db)
        except HTTPException:
            cfg = {'id': 'auth', 'signing': secrets.token_hex(32)}
            if os.environ.get('STUDY_PASSWORD'):
                cfg.update(password_hash(os.environ['STUDY_PASSWORD']))
            return store.save('config', cfg, db)


def password_hash(password):
    salt = secrets.token_hex(16)
    return {'salt': salt, 'hash': hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()}


def authenticated(request):
    token = request.cookies.get('study_session', '')
    try:
        expiry, signature = token.split('.')
        expected = hmac.new(auth_config()['signing'].encode(), expiry.encode(), hashlib.sha256).hexdigest()
        return int(expiry) > time.time() and hmac.compare_digest(signature, expected)
    except (ValueError, KeyError):
        return False


@app.middleware('http')
async def security(request, call_next):
    path = request.url.path
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        # No CORS, no form submissions or cross-site mutations.
        if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Origine non consentita'}, status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Richiesta non consentita'}, status_code=403)
    if path.startswith('/api/') and path not in ('/api/status', '/api/login') and not authenticated(request):
        return JSONResponse({'detail': 'Accedi per continuare'}, status_code=401)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/status')
def status(request: Request):
    cfg = auth_config()
    return {'setup_required': 'hash' not in cfg, 'authenticated': authenticated(request), 'ai': ai.enabled() if authenticated(request) else False}


class Login(BaseModel):
    password: str = Field(min_length=10, max_length=256)


LOGIN_ATTEMPTS = {}


@app.post('/api/login')
def login(body: Login, request: Request):
    ip = request.client.host if request.client else 'local'
    attempts = [t for t in LOGIN_ATTEMPTS.get(ip, []) if t > time.time()-60]
    if len(attempts) >= 8:
        raise HTTPException(429, 'Troppi tentativi. Attendi un minuto.')
    attempts.append(time.time())
    LOGIN_ATTEMPTS[ip] = attempts
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        cfg = store.get('config', 'auth', db)
        if 'hash' not in cfg:
            cfg.update(password_hash(body.password))
            store.save('config', cfg, db)
        else:
            hashed = hashlib.scrypt(body.password.encode(), salt=cfg['salt'].encode(), n=16384, r=8, p=1).hex()
            if not hmac.compare_digest(hashed, cfg['hash']):
                raise HTTPException(401, 'Password non corretta')
    expiry = str(int(time.time()) + 12*3600)
    signature = hmac.new(cfg['signing'].encode(), expiry.encode(), hashlib.sha256).hexdigest()
    response = JSONResponse({'ok': True})
    response.set_cookie('study_session', expiry + '.' + signature, httponly=True, samesite='strict',
                        secure=request.url.scheme == 'https', max_age=12*3600)
    return response


@app.post('/api/logout')
def logout():
    r = JSONResponse({'ok': True})
    r.delete_cookie('study_session')
    return r


def settings():
    try:
        return store.get('settings', 'settings')
    except HTTPException:
        return {'id': 'settings', 'daily_limit': 30, 'daily_goal': 20, 'timezone': 'Europe/Rome'}


@app.get('/api/settings')
def get_settings():
    return settings()


class Settings(BaseModel):
    daily_limit: int = Field(ge=1, le=200)
    daily_goal: int = Field(ge=1, le=240)


@app.put('/api/settings')
def put_settings(body: Settings):
    return store.save('settings', dict(settings(), **body.model_dump()))


@app.get('/api/documents')
def list_documents():
    return store.all_items('document')


@app.post('/api/documents')
def upload(file: UploadFile = File(...), topic: str = Form('Neurologia'), course: str = Form(''),
           document_id: str = Form(''), mark_linked: bool = Form(False)):
    content = file.file.read(documents.MAX_BYTES + 1)
    if len(content) > documents.MAX_BYTES:
        raise HTTPException(413, 'Massimo 20 MB per file')
    sections, warnings = documents.extract(file.filename or '', content)
    previous = store.get('document', document_id) if document_id else None
    doc = dict(previous or {}, name=Path(file.filename or 'Materiale').name[:200], topic=topic[:150], course=course[:150],
               sections=sections, warnings=warnings, revision=(previous or {}).get('revision', 0) + 1,
               demo=False, digest=hashlib.sha256(content).hexdigest())
    saved = store.save('document', doc)
    if previous and mark_linked:
        for kind in ('question', 'card'):
            for item in store.all_items(kind):
                if any(s['document_id'] == saved['id'] for s in item.get('sources', [])):
                    item['review_required'] = True
                    item['review_reason'] = 'Fonte aggiornata: controlla o rigenera esplicitamente questo contenuto.'
                    store.save(kind, item)
    return saved


@app.delete('/api/documents/{ident}')
def remove_document(ident: str):
    store.get('document', ident)
    store.delete('document', ident)
    for kind in ('question', 'card'):
        for item in store.all_items(kind):
            if any(s['document_id'] == ident for s in item.get('sources', [])):
                item['review_required'] = True
                item['review_reason'] = 'Fonte eliminata. La citazione storica rimane nel contenuto: elimina anche il contenuto per rimuoverla.'
                store.save(kind, item)
    return {'ok': True}


class Generate(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=20)
    sections: dict[str, list[str]] = Field(default_factory=dict)
    kind: str = 'question'
    count: int = Field(default=5, ge=1, le=30)
    difficulty: str = 'intermedia'
    engine: str = 'extractive'
    replace_id: str | None = None


def source(doc, section, quote=None):
    return {'document_id': doc['id'], 'document_name': doc['name'], 'revision': doc['revision'],
            'section_id': section['id'], 'label': section['label'], 'quote': quote or section['text'][:700],
            'origin': 'demo' if doc.get('demo') else 'materiale utente'}


def valid_question(q):
    opts = q.get('options', [])
    correct = q.get('correct', [])
    return (isinstance(q.get('prompt'), str) and 10 <= len(q['prompt']) <= 3000
            and isinstance(opts, list) and 2 <= len(opts) <= 6 and all(isinstance(o, str) and o.strip() for o in opts)
            and len(set(o.casefold().strip() for o in opts)) == len(opts)
            and isinstance(correct, list) and bool(correct) and all(type(i) is int and 0 <= i < len(opts) for i in correct)
            and len(set(correct)) == len(correct) and len(correct) < len(opts)
            and isinstance(q.get('explanation'), str)
            and isinstance(q.get('option_explanations'), list) and len(q['option_explanations']) == len(opts)
            and all(isinstance(s, str) for s in q['option_explanations'])
            and q.get('type') in ('single', 'multiple') and (q['type'] == 'multiple' or len(correct) == 1))


@app.post('/api/generate')
def generate(body: Generate):
    if body.kind not in ('question', 'card'):
        raise HTTPException(422, 'Tipo non valido')
    if body.replace_id:
        store.get(body.kind, body.replace_id)
    docs = [store.get('document', i) for i in body.document_ids]
    chunks = []
    for d in docs:
        selected = body.sections.get(d['id'])
        for s in d['sections']:
            if selected is None or s['id'] in selected:
                chunks.append({'key': f'{d["id"]}:{s["id"]}', 'topic': d['topic'], 'source': source(d, s), 'text': s['text']})
    if not chunks:
        raise HTTPException(422, 'Seleziona almeno una sezione')
    total = sum(len(c['text']) for c in chunks)
    warnings, candidates = [], []
    if body.engine == 'ai':
        if total > 70000:
            raise HTTPException(422, 'Seleziona meno sezioni: massimo 70.000 caratteri per richiesta IA')
        task = ('Genera contenuti didattici supportati dalle fonti. Restituisci {"items": [...], "warnings": [string]}. '
                'Ogni item deve avere source_key, quote (citazione letterale continua della fonte), topic. '
                'Segnala disaccordi senza scegliere una fonte. Nessuna conoscenza esterna. '
                + ('Per quiz: prompt, type single|multiple, options (4 testi plausibili simili per stile e lunghezza), correct (indici da 0), explanation, option_explanations (una per opzione). Anche vignette brevi solo se supportate. '
                   if body.kind == 'question' else 'Per flashcard: front, back (essenziale), extra (approfondimento), type qa|cloze; cloze usa {{risposta}} nel front. Un solo concetto per scheda. '))
        result = ai.complete(task, {'count': body.count, 'difficulty': body.difficulty,
                                   'sources': [{'key': c['key'], 'text': c['text'], 'topic': c['topic']} for c in chunks]})
        if not isinstance(result, dict) or not isinstance(result.get('items'), list):
            raise HTTPException(502, 'Formato IA non valido')
        warnings = [str(w)[:1000] for w in result.get('warnings', [])][:30]
        for item in result['items'][:body.count]:
            if not isinstance(item, dict):
                continue
            c = next((c for c in chunks if c['key'] == item.get('source_key')), None)
            quote = item.get('quote')
            if not c or not isinstance(quote, str) or len(quote.strip()) < 15 or quote not in c['text']:
                warnings.append('Contenuto scartato: citazione non riscontrabile letteralmente nella fonte.')
                continue
            item['sources'] = [dict(c['source'], quote=quote)]
            item['topic'] = c['topic']
            item['origin'] = 'ai'
            # A literal citation establishes provenance, not clinical entailment.
            item['review_required'] = True
            item['review_reason'] = 'Generato da IA: verifica supporto clinico e alternative prima di approvare.'
            candidates.append(item)
    elif body.engine == 'extractive':
        warnings.append('Modalità estrattiva locale: esercizi di richiamo letterale, difficoltà non adattiva; non verifica la correttezza clinica né individua tutte le contraddizioni. Revisione richiesta.')
        sentences = []
        for c in chunks:
            for sentence in re.split(r'(?<=[.!?])\s+|\n', c['text']):
                words = re.findall(r'\b[\wÀ-ÿ-]{6,}\b', sentence)
                if 40 <= len(sentence) <= 700 and words:
                    sentences.append((c, sentence, max(words, key=len)))
        vocabulary = list(dict.fromkeys(w for _, s, _ in sentences for w in re.findall(r'\b[\wÀ-ÿ-]{6,}\b', s)))
        for c, sentence, word in sentences:
            if len(candidates) >= body.count:
                break
            masked = sentence.replace(word, '{{' + word + '}}', 1)
            item = dict(topic=c['topic'], sources=[dict(c['source'], quote=sentence)], origin='extractive',
                        review_required=True, review_reason='Richiamo letterale locale: controlla chiarezza e supporto della fonte.')
            if body.kind == 'card':
                item.update(front=masked, back=word, extra=sentence, type='cloze')
            else:
                distractors = [w for w in vocabulary if w.casefold() != word.casefold()][:3]
                if len(distractors) < 2:
                    continue
                options = distractors + [word]
                random.shuffle(options)
                item.update(prompt='Completa il passaggio del materiale: «' + sentence.replace(word, '____', 1) + '»',
                            options=options, correct=[options.index(word)], type='single',
                            explanation='Richiamo testuale. La fonte riporta: ' + sentence,
                            option_explanations=['È il termine presente nella citazione.' if w == word else 'Non è il termine usato in questo passaggio; ciò non implica che sia clinicamente falso in altri contesti.' for w in options])
            candidates.append(item)
    else:
        raise HTTPException(422, 'Motore non valido')
    saved = []
    existing = {i.get('prompt' if body.kind == 'question' else 'front', '').strip().casefold() for i in store.all_items(body.kind) if i['id'] != body.replace_id}
    for item in candidates:
        if body.kind == 'question' and not valid_question(item):
            warnings.append('Domanda scartata: formato o risposte non validi.')
            continue
        if body.kind == 'card' and (not isinstance(item.get('front'), str) or not isinstance(item.get('back'), str) or not item['front'].strip() or not item['back'].strip()):
            warnings.append('Scheda scartata: domanda o risposta mancante.')
            continue
        key = item['prompt' if body.kind == 'question' else 'front'].strip().casefold()
        if key in existing:
            warnings.append('Duplicato esatto scartato.')
            continue
        existing.add(key)
        allowed = ('prompt', 'options', 'correct', 'type', 'explanation', 'option_explanations') if body.kind == 'question' else ('front', 'back', 'extra', 'type')
        clean = {k: item[k] for k in allowed if k in item}
        clean.update({k: item[k] for k in ('topic', 'sources', 'origin', 'review_required', 'review_reason')})
        clean.update(difficulty=body.difficulty, demo=all(d.get('demo') for d in docs))
        if body.kind == 'card':
            clean.update(due=store.now(), interval=0, ease=2.5, reviews=0, suspended=False)
        saved.append(store.save(body.kind, clean))
    if len(saved) < body.count:
        warnings.append(f'Salvati {len(saved)} contenuti su {body.count} richiesti: fonti insufficienti, formato non valido o duplicati. Nessun riempimento inventato.')
    return {'items': saved, 'warnings': warnings}


@app.get('/api/questions')
def questions():
    return store.all_items('question')


class Question(BaseModel):
    prompt: str = Field(min_length=10, max_length=3000)
    options: list[str]
    correct: list[int]
    type: str
    explanation: str
    option_explanations: list[str]
    topic: str = 'Neurologia'
    difficulty: str = 'intermedia'
    review_required: bool = False


@app.put('/api/questions/{ident}')
def edit_question(ident: str, body: Question):
    if not valid_question(body.model_dump()):
        raise HTTPException(422, 'Domanda o risposte non valide')
    q = store.get('question', ident)
    q.update(body.model_dump())
    q['version'] = q.get('version', 1) + 1
    return store.save('question', q)


@app.delete('/api/questions/{ident}')
def delete_question(ident: str):
    store.delete('question', ident)
    return {'ok': True}


@app.post('/api/questions/{ident}/bookmark')
def bookmark(ident: str):
    q = store.get('question', ident)
    q['bookmarked'] = not q.get('bookmarked', False)
    return store.save('question', q)


class Report(BaseModel):
    kind: str
    target_id: str
    text: str = Field(min_length=5, max_length=5000)


@app.post('/api/reports')
def report(body: Report):
    if body.kind not in ('question', 'card', 'case'):
        raise HTTPException(422, 'Tipo non valido')
    item = store.get(body.kind, body.target_id)
    if body.kind != 'case':
        item.update(review_required=True, review_reason=body.text)
        store.save(body.kind, item)
    return store.save('report', body.model_dump())


class QuizOptions(BaseModel):
    topics: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    count: int = Field(default=10, ge=1, le=100)
    difficulty: str = 'tutte'
    filter: str = 'mixed'
    mode: str = 'training'
    minutes: int = Field(default=0, ge=0, le=240)
    include_demo: bool = False
    include_review: bool = False


def public_quiz(q):
    q = dict(q)
    complete = bool(q.get('finished_at'))
    if not complete and q['mode'] == 'exam':
        q['answers'] = {k: {a: b for a, b in v.items() if a != 'correct'} for k, v in q['answers'].items()}
    q['questions'] = [dict(item) for item in q['questions']]
    for item in q['questions']:
        answered = item['id'] in q['answers']
        if not complete and (q['mode'] == 'exam' or not answered):
            for k in ('correct', 'explanation', 'option_explanations', 'sources'):
                item.pop(k, None)
    return q


@app.post('/api/quizzes')
def start_quiz(body: QuizOptions):
    if body.mode not in ('training', 'exam') or body.filter not in ('mixed', 'new', 'wrong', 'saved'):
        raise HTTPException(422, 'Modalità non valida')
    history = {}
    for quiz in sorted(store.all_items('quiz'), key=lambda s: s['created_at']):
        for ident, answer in quiz['answers'].items():
            h = history.setdefault(ident, {'attempts': 0, 'errors': 0})
            h['attempts'] += 1
            h['errors'] += not answer['correct']
    pool = []
    for q in questions():
        h = history.get(q['id'], {'attempts': 0, 'errors': 0})
        if q.get('demo') and not body.include_demo or q.get('review_required') and not body.include_review:
            continue
        if body.topics and q['topic'] not in body.topics:
            continue
        if body.document_ids and not any(s['document_id'] in body.document_ids for s in q.get('sources', [])):
            continue
        if body.difficulty != 'tutte' and q['difficulty'] != body.difficulty:
            continue
        if body.filter == 'new' and h['attempts'] or body.filter == 'wrong' and not h['errors'] or body.filter == 'saved' and not q.get('bookmarked'):
            continue
        # Errors reappear; repeated success lowers the error ratio instead of erasing history.
        weight = 1 + 3*h['errors']/max(1, h['attempts'])
        pool.append((random.random() ** (1/weight), q))
    pool.sort(key=lambda p: p[0], reverse=True)
    if not pool:
        raise HTTPException(422, 'Nessuna domanda corrisponde ai filtri. Genera o approva contenuti, oppure includi Demo / da revisionare.')
    chosen = [q for _, q in pool[:body.count]]
    q = store.save('quiz', dict(body.model_dump(), questions=chosen, answers={},
                               deadline=(datetime.now(timezone.utc)+timedelta(minutes=body.minutes)).isoformat() if body.minutes else None))
    return public_quiz(q)


@app.get('/api/quizzes/{ident}')
def get_quiz(ident: str):
    return public_quiz(store.get('quiz', ident))


class Answer(BaseModel):
    question_id: str
    selected: list[int]


@app.post('/api/quizzes/{ident}/answer')
def answer_quiz(ident: str, body: Answer):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        q = store.get('quiz', ident, db)
        if q.get('finished_at'):
            raise HTTPException(409, 'Sessione conclusa')
        if q['deadline'] and store.now() > q['deadline']:
            raise HTTPException(409, 'Tempo scaduto: concludi per vedere i risultati')
        question = next((i for i in q['questions'] if i['id'] == body.question_id), None)
        if not question:
            raise HTTPException(404, 'Domanda non presente nella sessione')
        if body.question_id in q['answers']:
            raise HTTPException(409, 'Risposta già registrata')
        if any(type(i) is not int or i < 0 or i >= len(question['options']) for i in body.selected) or not body.selected:
            raise HTTPException(422, 'Selezione non valida')
        if question['type'] == 'single' and len(set(body.selected)) != 1:
            raise HTTPException(422, 'Scegli una sola risposta')
        q['answers'][body.question_id] = {'selected': body.selected, 'correct': set(body.selected) == set(question['correct']), 'at': store.now()}
        store.save('quiz', q, db)
    return public_quiz(q)


@app.post('/api/quizzes/{ident}/finish')
def finish_quiz(ident: str):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        q = store.get('quiz', ident, db)
        q.setdefault('finished_at', store.now())
        store.save('quiz', q, db)
    return public_quiz(q)


class Card(BaseModel):
    front: str = Field(min_length=3, max_length=3000)
    back: str = Field(min_length=1, max_length=3000)
    extra: str = Field(default='', max_length=10000)
    topic: str = Field(default='Neurologia', max_length=150)
    type: str = 'qa'
    suspended: bool = False
    review_required: bool = False
    question_id: str | None = None


@app.get('/api/cards')
def cards():
    return store.all_items('card')


@app.post('/api/cards')
def create_card(body: Card):
    if body.type not in ('qa', 'cloze') or body.type == 'cloze' and not re.search(r'\{\{.+?\}\}', body.front):
        raise HTTPException(422, 'Tipo non valido: cloze richiede {{risposta}}')
    data = body.model_dump()
    if body.question_id:
        q = store.get('question', body.question_id)
        data.update(sources=q.get('sources', []), demo=q.get('demo', False), origin='quiz', review_required=q.get('review_required', False))
    else:
        data.update(sources=[], demo=False, origin='manuale')
    return store.save('card', dict(data, due=store.now(), interval=0, ease=2.5, reviews=0))


@app.put('/api/cards/{ident}')
def edit_card(ident: str, body: Card):
    if body.type not in ('qa', 'cloze') or body.type == 'cloze' and not re.search(r'\{\{.+?\}\}', body.front):
        raise HTTPException(422, 'Cloze richiede {{risposta}}')
    card = store.get('card', ident)
    card.update(body.model_dump(exclude={'question_id'}))
    return store.save('card', card)


@app.delete('/api/cards/{ident}')
def delete_card(ident: str):
    store.delete('card', ident)
    return {'ok': True}


class ReviewOptions(BaseModel):
    topic: str = ''
    document_id: str = ''
    include_demo: bool = False
    include_review: bool = False


def today():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('Europe/Rome')).date().isoformat()


@app.post('/api/reviews')
def start_review(body: ReviewOptions):
    day = today()
    done = sum(1 for r in store.all_items('rating') if r['day'] == day)
    limit = max(0, settings()['daily_limit'] - done)
    pool = [c for c in cards() if not c.get('suspended') and c['due'] <= store.now()
            and (not c.get('demo') or body.include_demo) and (not c.get('review_required') or body.include_review)
            and (not body.topic or c['topic'] == body.topic)
            and (not body.document_id or any(s['document_id'] == body.document_id for s in c.get('sources', [])))]
    pool.sort(key=lambda c: (c.get('reviews', 0) == 0, c['due']))
    if not pool or not limit:
        raise HTTPException(422, 'Nessuna scheda dovuta per questi filtri, oppure carico giornaliero raggiunto.')
    return public_review(store.save('review', {'card_ids': [c['id'] for c in pool[:limit]], 'ratings': {}, 'revealed': []}))


def public_review(review):
    result = dict(review)
    result['cards'] = []
    for ident in review['card_ids']:
        try:
            c = store.get('card', ident)
        except HTTPException:
            continue
        c = dict(c)
        if ident not in review['revealed']:
            c['front'] = re.sub(r'\{\{.+?\}\}', '[…]', c['front'])
            for key in ('back', 'extra', 'sources'):
                c.pop(key, None)
        result['cards'].append(c)
    return result


@app.get('/api/reviews/{ident}')
def get_review(ident: str):
    return public_review(store.get('review', ident))


@app.post('/api/reviews/{ident}/reveal/{card_id}')
def reveal(ident: str, card_id: str):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        r = store.get('review', ident, db)
        if card_id not in r['card_ids']:
            raise HTTPException(404, 'Scheda non presente')
        if card_id not in r['revealed']:
            r['revealed'].append(card_id)
        store.save('review', r, db)
    return public_review(r)


class Rating(BaseModel):
    card_id: str
    grade: str


@app.post('/api/reviews/{ident}/rate')
def rate(ident: str, body: Rating):
    if body.grade not in ('again', 'hard', 'good', 'easy'):
        raise HTTPException(422, 'Valutazione non valida')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        r = store.get('review', ident, db)
        if body.card_id not in r['revealed'] or body.card_id in r['ratings']:
            raise HTTPException(409, 'Rivela prima la risposta o scheda già valutata')
        if sum(1 for rating in store.all_items('rating', db) if rating['day'] == today()) >= settings()['daily_limit']:
            raise HTTPException(409, 'Carico giornaliero raggiunto')
        c = store.get('card', body.card_id, db)
        if c.get('suspended'):
            raise HTTPException(409, 'Scheda sospesa')
        if c['due'] > store.now():
            raise HTTPException(409, 'Scheda già ripassata in un’altra sessione. La nuova scadenza è stata conservata.')
        interval, ease = c.get('interval', 0), c.get('ease', 2.5)
        if body.grade == 'again':
            interval, ease = 10 / 1440, max(1.3, ease - .2)
        elif body.grade == 'hard':
            interval, ease = max(1, interval*1.2), max(1.3, ease-.15)
        elif body.grade == 'good':
            interval = 1 if c['reviews'] == 0 else max(2, interval*ease)
        else:
            interval, ease = max(4, interval*ease*1.3), min(3.2, ease+.15)
        c.update(interval=round(interval, 5), ease=ease, reviews=c['reviews']+1,
                 due=(datetime.now(timezone.utc)+timedelta(days=interval)).isoformat())
        store.save('card', c, db)
        r['ratings'][body.card_id] = {'grade': body.grade, 'due': c['due']}
        if len(r['ratings']) == len(r['card_ids']):
            r['finished_at'] = store.now()
        store.save('review', r, db)
        store.save('rating', {'card_id': c['id'], 'grade': body.grade, 'day': today(), 'due': c['due'], 'demo': c.get('demo', False)}, db)
    return public_review(r)


class CaseOptions(BaseModel):
    level: str = 'studente'
    complexity: str = 'base'
    topic: str = ''
    mode: str = 'guided'
    minutes: int = Field(default=0, ge=0, le=240)
    engine: str = 'demo'


@app.get('/api/case-options')
def case_options():
    return {'topics': [d['topic'] for d in cases.templates()], 'actions': [{'id': a[0], 'category': a[1], 'label': a[2]} for a in cases.ACTIONS],
            'rubric': cases.RUBRIC, 'thresholds': cases.THRESHOLDS,
            'scoring': 'Soglie stelle: 1 <40; 2 ≥40; 3 ≥55; 4 ≥70; 5 ≥85 su 100. Informazioni: azioni essenziali raccolte. Ragionamento: reperti motivati (12), localizzazione (8), alternative (5). Accertamenti: essenziali (20), priorità (5), superflui −1,5 ciascuno (max −5). Diagnosi: sinonimo (20), reperti motivati (10). Nessuna penalità per aiuti. Valutazione euristica con limiti espliciti: non sostituisce revisione docente. Studente/base: una alternativa, localizzazione facoltativa (4/8 se assente); altri livelli: localizzazione richiesta; specializzando o avanzato: due alternative. Base: campi e azioni raggruppate, suggerimenti strutturati; avanzato: nessun indizio aggiuntivo iniziale. Il dossier e la rubrica vengono fissati prima dell’avvio.'}


def public_case(c):
    d = c['dossier']
    result = {k: v for k, v in c.items() if k != 'dossier'}
    # Random cases do not leak topic, diagnosis, reports, aliases or evaluation criteria.
    result.update(arrival=d['arrival'], source=d['source'], rubric=d['rubric'], thresholds=d['thresholds'])
    if c['complexity'] == 'base':
        result['support'] = 'Parti da esordio, andamento e parametri; esamina la sede del possibile deficit prima di formulare la diagnosi. I menu non indicano le azioni corrette.'
    return result


@app.post('/api/cases')
def start_case(body: CaseOptions):
    if body.level not in ('studente', 'specializzando') or body.complexity not in ('base', 'intermedia', 'avanzata') or body.mode not in ('guided', 'exam'):
        raise HTTPException(422, 'Opzioni non valide')
    if body.engine == 'ai':
        template = cases.templates()[0]
        schema = {k: v for k, v in template.items() if k != 'reports'}
        schema['reports'] = {a[0]: 'reperto coerente, unità/intervalli se numerico, non anticipare altri risultati' for a in cases.ACTIONS}
        d = ai.complete('Crea un dossier clinico fittizio di neurologia, coerente e completo, prima dell’interazione. Restituisci {"dossier":oggetto}. Usa lo schema fornito, stessi tipi e tutte le chiavi. Azioni solo dagli ID forniti, essential/information/priority non vuoti. Arrivo senza diagnosi o reperti risolutivi; adatta complessità del ragionamento e differenziali al livello, non solo rarità. Nessun dato reale. Non usare fonti utente. Tutti i reports devono essere presenti; non dare suggerimenti nei referti.',
                        {'schema': schema, 'options': body.model_dump()})
        d = d.get('dossier') if isinstance(d, dict) else None
        listkeys = ('aliases', 'information', 'essential', 'useful', 'priority', 'localization', 'evidence', 'differentials')
        if (not isinstance(d, dict) or not all(isinstance(d.get(k), str) and d[k].strip() for k in ('topic', 'diagnosis', 'arrival', 'pathway'))
                or not all(isinstance(d.get(k), list) and d[k] and all(isinstance(s, str) for s in d[k]) for k in listkeys)
                or not isinstance(d.get('reports'), dict) or not all(isinstance(d['reports'].get(a), str) for a in cases.ACTION_MAP)
                or not all(a in cases.ACTION_MAP for k in ('information', 'essential', 'useful', 'priority') for a in d[k])):
            raise HTTPException(502, 'Dossier IA incompleto: caso non avviato')
        d['source'] = 'Caso generato da IA: integrativo, non derivato dai tuoi materiali, non revisionato clinicamente. Paziente fittizio.'
    elif body.engine == 'demo':
        choices = [d for d in cases.templates() if not body.topic or d['topic'] == body.topic]
        if not choices:
            raise HTTPException(422, 'Argomento demo non disponibile')
        d = random.choice(choices)
    else:
        raise HTTPException(422, 'Motore non valido')
    d = cases.prepare(d, body.level, body.complexity)
    c = store.save('case', dict(body.model_dump(), dossier=d, events=[], hints=[], notes='',
                               deadline=(datetime.now(timezone.utc)+timedelta(minutes=body.minutes)).isoformat() if body.minutes else None))
    return public_case(c)


@app.get('/api/cases/{ident}')
def get_case(ident: str):
    return public_case(store.get('case', ident))


class CaseAction(BaseModel):
    action: str | None = None
    text: str = Field(default='', max_length=3000)


@app.post('/api/cases/{ident}/actions')
def case_action(ident: str, body: CaseAction):
    # Natural-language routing sees only the request and catalog, never the diagnosis.
    c = store.get('case', ident)
    routed = {'kind': 'action', 'action': body.action} if body.action else cases.route(body.text, c['engine'] == 'ai')
    if routed['kind'] == 'action' and routed.get('action') not in cases.ACTION_MAP:
        raise HTTPException(422, 'Azione sconosciuta')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        c = store.get('case', ident, db)
        if c.get('finished_at'):
            raise HTTPException(409, 'Caso già concluso')
        if c['deadline'] and store.now() > c['deadline']:
            raise HTTPException(409, 'Tempo scaduto: consegna la conclusione')
        event = {'at': store.now(), 'request': body.text or cases.ACTION_MAP[body.action][2], 'kind': routed['kind']}
        if routed['kind'] == 'action':
            action = routed['action']
            event.update(action=action, response=c['dossier']['reports'][action])
        elif routed['kind'] == 'hypothesis':
            event['response'] = 'Ipotesi annotata. Verrà discussa dopo la consegna; nessuna conferma anticipata.'
        else:
            event['response'] = routed.get('message', 'Richiesta ambigua: specifica una sola azione dal menu. Nessun accertamento assegnato.')
        c['events'].append(event)
        store.save('case', c, db)
    return public_case(c)


class Notes(BaseModel):
    notes: str = Field(max_length=20000)


@app.put('/api/cases/{ident}/notes')
def notes(ident: str, body: Notes):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        c = store.get('case', ident, db)
        c['notes'] = body.notes
        store.save('case', c, db)
    return {'ok': True}


@app.post('/api/cases/{ident}/hint')
def hint(ident: str):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        c = store.get('case', ident, db)
        if c['mode'] == 'exam' or c.get('finished_at'):
            raise HTTPException(409, 'Suggerimenti non disponibili')
        d = c['dossier']
        hints = ['Ricostruisci esordio, andamento e sintomi associati; poi prova a localizzare il deficit.',
                 'Confronta i reperti dell’esame neurologico con la tua ipotesi di localizzazione.',
                 'Valuta se hai raccolto: ' + ', '.join(cases.ACTION_MAP[a][2] for a in d['information'])]
        if len(c['hints']) >= len(hints):
            raise HTTPException(409, 'Tutti i suggerimenti sono già stati utilizzati')
        c['hints'].append(hints[len(c['hints'])])
        store.save('case', c, db)
    return public_case(c)


class Conclusion(BaseModel):
    diagnosis: str = Field(min_length=2, max_length=1000)
    rationale: str = Field(default='', max_length=10000)
    localization: str = Field(default='', max_length=2000)
    alternatives: str = Field(default='', max_length=3000)


@app.post('/api/cases/{ident}/finish')
def finish_case(ident: str, body: Conclusion):
    snapshot = store.get('case', ident)
    if snapshot.get('finished_at'):
        return public_case(snapshot)
    assessment = cases.evaluate(snapshot, body.model_dump())
    if ai.enabled() and snapshot['engine'] == 'ai':
        assessment = cases.semantic_evaluation(snapshot, body.model_dump(), assessment)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        c = store.get('case', ident, db)
        if not c.get('finished_at'):
            if c['events'] != snapshot['events'] or c['hints'] != snapshot['hints']:
                raise HTTPException(409, 'Il caso è cambiato durante la valutazione. Consegna di nuovo sullo stato aggiornato.')
            c.update(submission=body.model_dump(), assessment=assessment, finished_at=store.now())
            store.save('case', c, db)
    return public_case(c)


@app.get('/api/dashboard')
def dashboard():
    cs, qs, rs = store.all_items('case'), store.all_items('quiz'), store.all_items('review')
    metrics = {}
    for quiz in qs:
        for q in quiz['questions']:
            a = quiz['answers'].get(q['id'])
            if not a or q.get('demo'):
                continue
            m = metrics.setdefault(q['topic'], {'attempts': 0, 'errors': 0})
            m['attempts'] += 1
            m['errors'] += not a['correct']
    due = [c for c in cards() if not c.get('suspended') and not c.get('demo') and not c.get('review_required') and c['due'] <= store.now()]
    day = today()
    from zoneinfo import ZoneInfo
    def local_day(value):
        return datetime.fromisoformat(value).astimezone(ZoneInfo('Europe/Rome')).date().isoformat()
    overdue = [c for c in due if c['reviews'] and local_day(c['due']) < day]
    ratings = [r for r in store.all_items('rating') if r['day'] == day and not r.get('demo')]
    summary = lambda items, kind: [{'id': s['id'], 'kind': kind, 'created_at': s['created_at']} for s in items if not s.get('finished_at')]
    assessments = [{'id': c['id'], 'at': c['finished_at'], 'demo': c['engine'] == 'demo', 'topic': c['assessment']['topic'], 'dimensions': c['assessment']['dimensions'], 'total': c['assessment']['total']} for c in cs if c.get('assessment')]
    return {'due': len(due), 'overdue': len(overdue), 'new': sum(c['reviews'] == 0 for c in due),
            'today_due': sum(c['reviews'] > 0 and local_day(c['due']) == day for c in due),
            'metrics': metrics, 'rated_today': len(ratings), 'settings': settings(), 'assessments': assessments,
            'resume': summary(qs, 'quiz') + summary(rs, 'review') + summary(cs, 'case'),
            'history': [{'id': q['id'], 'kind': 'quiz', 'created_at': q['created_at']} for q in qs if q.get('finished_at')] + [{'id': c['id'], 'kind': 'case', 'created_at': c['created_at']} for c in cs if c.get('finished_at')],
            'needs_review': sum(i.get('review_required', False) for i in cards()+questions())}


@app.get('/api/export')
def export():
    # Auth signing key, password hash and unrevealed dossiers are never exported.
    return {'version': 1, 'exported_at': store.now(), 'documents': list_documents(), 'questions': questions(), 'cards': cards(),
            'quizzes': [public_quiz(q) for q in store.all_items('quiz')], 'reviews': [public_review(r) for r in store.all_items('review')],
            'ratings': store.all_items('rating'), 'cases': [public_case(c) for c in store.all_items('case')],
            'settings': settings(), 'reports': store.all_items('report')}


@app.post('/api/demo')
def demo():
    if any(d.get('demo') for d in list_documents()):
        return {'ok': True, 'message': 'Dati demo già presenti'}
    text = ('La miastenia gravis è una malattia della giunzione neuromuscolare caratterizzata da debolezza fluttuante e affaticabilità. '
            'La sensibilità è generalmente conservata nella miastenia gravis. '
            'La ptosi può peggiorare dopo sguardo prolungato verso l’alto. '
            'Il coinvolgimento respiratorio richiede una valutazione clinica tempestiva.')
    doc = store.save('document', {'name': 'DEMO · Giunzione neuromuscolare.txt', 'topic': 'Malattie neuromuscolari', 'course': 'Demo redazionale',
                                 'demo': True, 'revision': 1, 'warnings': ['Materiale dimostrativo redazionale; non caricato dall’utente, non validato da un docente.'],
                                 'sections': [{'id': '1', 'label': 'Sezione dimostrativa', 'text': text}]})
    s = source(doc, doc['sections'][0], 'La sensibilità è generalmente conservata nella miastenia gravis.')
    store.save('question', {'prompt': 'Quale funzione è generalmente conservata nella miastenia gravis secondo il testo demo?',
                           'type': 'single', 'options': ['Sensibilità', 'Forza dopo esercizio prolungato', 'Resistenza alla fatica dei muscoli oculari', 'Resistenza alla fatica dei muscoli bulbari'], 'correct': [0],
                           'explanation': 'La sede del disturbo è la giunzione neuromuscolare; il passaggio demo distingue la sensibilità dalla debolezza affaticabile.',
                           'option_explanations': ['Il testo afferma che è generalmente conservata.', 'La forza può peggiorare con l’attività.', 'I muscoli oculari possono affaticarsi.', 'I muscoli bulbari possono affaticarsi.'],
                           'topic': doc['topic'], 'difficulty': 'base', 'sources': [s], 'demo': True, 'review_required': False, 'origin': 'demo'})
    store.save('question', {'prompt': 'Quali caratteristiche sono descritte nel materiale demo? Seleziona tutte le risposte corrette.',
                           'type': 'multiple', 'options': ['Debolezza fluttuante', 'Affaticabilità', 'Sensibilità sempre abolita', 'Ptosi invariabile durante la giornata'], 'correct': [0, 1],
                           'explanation': 'Il testo descrive fluttuazione e affaticabilità, non anestesia o ptosi invariabile.',
                           'option_explanations': ['Descritta nella prima frase.', 'Descritta nella prima frase.', 'Contrasta con la sensibilità generalmente conservata.', 'Il testo descrive peggioramento dopo sguardo sostenuto.'],
                           'topic': doc['topic'], 'difficulty': 'base', 'sources': [source(doc, doc['sections'][0])], 'demo': True, 'review_required': False, 'origin': 'demo'})
    store.save('card', {'front': 'Nella miastenia gravis, come è generalmente la sensibilità?', 'back': 'Conservata.',
                       'extra': 'Il disturbo interessa la trasmissione neuromuscolare; questa scheda è solo didattica.', 'type': 'qa', 'topic': doc['topic'],
                       'sources': [s], 'demo': True, 'origin': 'demo', 'review_required': False, 'suspended': False,
                       'due': store.now(), 'interval': 0, 'ease': 2.5, 'reviews': 0})
    return {'ok': True, 'message': 'Creati materiale, due quiz e una flashcard demo, separati dai tuoi dati'}


@app.get('/')
def index():
    return FileResponse(STATIC / 'index.html')


app.mount('/static', StaticFiles(directory=STATIC), name='static')
