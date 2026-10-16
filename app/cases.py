import re
from . import ai

ACTIONS = [
    ('history', 'Anamnesi', 'Esordio e andamento dei sintomi', ['anamnesi', 'esordio', 'da quanto', 'quando', 'sintomi']),
    ('medication', 'Anamnesi', 'Farmaci e allergie', ['farmaci', 'farmacologica', 'allergie', 'terapia abituale']),
    ('family', 'Anamnesi', 'Anamnesi familiare', ['familiare', 'famiglia']),
    ('vitals', 'Esame obiettivo', 'Parametri vitali e obiettività generale', ['parametri', 'pressione', 'vitali', 'obiettivo generale']),
    ('neuro', 'Esame neurologico', 'Esame neurologico completo', ['esame neurologico', 'obiettivo neurologico']),
    ('cranial', 'Esame neurologico', 'Nervi cranici', ['cranici', 'pupille', 'oculomozione']),
    ('motor', 'Esame neurologico', 'Forza e affaticabilità', ['forza', 'motilità', 'affaticabilità']),
    ('sensory', 'Esame neurologico', 'Sensibilità', ['sensibilità', 'sensitivo']),
    ('reflex', 'Esame neurologico', 'Riflessi e segni piramidali', ['riflessi', 'babinski', 'piramidali']),
    ('coordination', 'Esame neurologico', 'Coordinazione e marcia', ['coordinazione', 'marcia', 'cervelletto']),
    ('blood', 'Laboratorio', 'Emocromo, glicemia ed elettroliti', ['ematochimici', 'emocromo', 'glicemia', 'elettroliti']),
    ('ct', 'Imaging', 'TC encefalo senza contrasto', ['tc encefalo', 'tac', 'tomografia']),
    ('angio', 'Imaging', 'Angio-TC intracranica e dei tronchi sovraortici', ['angio', 'vasi']),
    ('mri', 'Imaging', 'RM encefalo e midollo', ['risonanza', 'rm encefalo', 'rm midollo', 'rmn']),
    ('emg', 'Neurofisiologia', 'Stimolazione nervosa ripetitiva / EMG', ['elettromiografia', 'emg', 'stimolazione ripetitiva']),
    ('eeg', 'Neurofisiologia', 'Elettroencefalogramma', ['eeg', 'elettroencefalogramma']),
    ('csf', 'Approfondimenti', 'Liquor con bande oligoclonali', ['liquor', 'puntura lombare', 'rachicentesi']),
    ('antibodies', 'Laboratorio', 'Anticorpi anti-recettore ACh e anti-MuSK', ['anticorpi', 'achr', 'musk']),
    ('respiration', 'Approfondimenti', 'Valutazione respiratoria e capacità vitale', ['respiratoria', 'capacità vitale', 'respiro']),
    ('consult', 'Consulenze', 'Consulenza neurologica urgente', ['consulenza', 'neurologo', 'stroke unit']),
]
ACTION_MAP = {a[0]: a for a in ACTIONS}
RUBRIC = [
    {'key': 'information', 'label': 'Raccolta delle informazioni', 'weight': 20},
    {'key': 'reasoning', 'label': 'Ragionamento e localizzazione', 'weight': 25},
    {'key': 'investigations', 'label': 'Appropriatezza e priorità', 'weight': 25},
    {'key': 'diagnosis', 'label': 'Diagnosi e motivazione', 'weight': 30},
]
THRESHOLDS = [0, 40, 55, 70, 85]


def norm(s):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', s.lower()) if unicodedata.category(c) != 'Mn')


def templates():
    return [
        dict(topic='Patologie cerebrovascolari', diagnosis='Ictus ischemico emisferico sinistro',
             aliases=['ictus ischemico', 'ischemia cerebrale', 'stroke ischemico', 'infarto cerebrale'],
             arrival='Uomo di 68 anni accompagnato dal coniuge per improvvisa difficoltà a parlare e debolezza al lato destro. È vigile; l’ora esatta di esordio non è ancora stata raccolta.',
             information=['history', 'vitals', 'neuro'], essential=['blood', 'ct', 'angio', 'consult'],
             useful=['medication', 'family', 'cranial', 'motor', 'sensory', 'reflex'], priority=['ct', 'angio', 'consult'],
             localization=['sinistr', 'emisfer', 'cortical', 'cerebrale media'],
             evidence=['improvvis', 'afasia', 'destr', 'vascolar', 'occlusion'],
             differentials=['emorragia cerebrale', 'ipoglicemia', 'crisi epilettica con deficit postcritico'],
             reports={
                 'history': 'Coniuge: «Stava bene fino a 50 minuti fa; all’improvviso ha lasciato cadere la tazza e non riusciva più a parlare normalmente. Nessun trauma o convulsione osservata». Ipertensione e fibrillazione atriale note.',
                 'medication': 'Assume ramipril. Riferisce sospensione autonoma dell’anticoagulante da due settimane. Nessuna allergia nota.',
                 'family': 'Padre con ictus a 76 anni; nessuna malattia neuromuscolare familiare nota.',
                 'vitals': 'PA 175/95 mmHg; FC 102/min irregolare; SpO₂ 97% in aria; T 36,7 °C; FR 16/min. Vigile, senza segni di trauma.',
                 'neuro': 'Afasia espressiva, paresi facio-brachio-crurale destra (arto superiore 2/5, inferiore 3/5), ipoestesia destra; sguardo preferenziale a sinistra. Nessun meningismo.',
                 'cranial': 'Paresi facciale centrale destra e sguardo preferenziale a sinistra. Pupille isocoriche, fotoreagenti.',
                 'motor': 'Forza MRC: arto superiore destro 2/5, inferiore destro 3/5; sinistra 5/5. Nessuna affaticabilità fluttuante.',
                 'sensory': 'Ipoestesia all’emisoma destro.', 'reflex': 'Riflessi più vivaci a destra; risposta plantare estensoria destra.',
                 'coordination': 'Non valutabile attendibilmente a destra per deficit di forza. Marcia non testata per sicurezza.',
                 'blood': 'Glicemia 108 mg/dL (70–100 a digiuno); Na 139 mmol/L (135–145); K 4,1 mmol/L (3,5–5,0); Hb 14 g/dL (13–17); piastrine 210 ×10⁹/L (150–400). Intervalli didattici, dipendono dal laboratorio.',
                 'ct': 'TC encefalo: nessuna emorragia intracranica; iniziale sfumatura della differenziazione cortico-sottocorticale insulare sinistra. Referto simulato.',
                 'angio': 'Angio-TC: occlusione del segmento M1 dell’arteria cerebrale media sinistra. Referto simulato.',
                 'mri': 'RM: restrizione della diffusione nel territorio dell’arteria cerebrale media sinistra. Accertamento non necessario per ritardare il percorso urgente in questo scenario.',
                 'consult': 'Il neurologo prende in carico il paziente nel percorso neurovascolare urgente e richiede documentazione dell’ultimo momento noto senza sintomi e dei farmaci assunti.',
             },
             pathway='Riconoscere il deficit focale improvviso; stabilire ultimo momento noto sano, farmaci e parametri; escludere ipoglicemia; attivare il percorso urgente con TC e imaging vascolare. Localizzare il deficit all’emisfero sinistro e integrare i referti. Il caso valuta il ragionamento, non prescrive trattamenti.'),
        dict(topic='Malattie neuromuscolari', diagnosis='Miastenia gravis generalizzata',
             aliases=['miastenia', 'myasthenia gravis'],
             arrival='Donna di 32 anni con visione doppia intermittente e difficoltà a finire i pasti da circa tre settimane. All’arrivo parla normalmente ed è vigile.',
             information=['history', 'neuro', 'respiration'], essential=['antibodies', 'emg'],
             useful=['medication', 'family', 'vitals', 'cranial', 'motor', 'sensory', 'reflex', 'blood'], priority=['respiration'],
             localization=['giunzion', 'postsinap', 'placca', 'neuromuscolar'],
             evidence=['fluttua', 'affatic', 'riposo', 'ptosi', 'decrement', 'anticorp'],
             differentials=['sindrome di Lambert-Eaton', 'miopatia', 'lesione del tronco encefalico'],
             reports={
                 'history': 'Paziente: «La sera va peggio. Le palpebre cadono dopo aver letto; dopo un po’ di riposo miglioro. Masticare a lungo mi stanca. Non ho formicolii». Non dispnea a riposo.',
                 'medication': 'Nessuna terapia cronica, nessuna nuova esposizione farmacologica riferita. Nessuna allergia nota.',
                 'family': 'Nessuna patologia neuromuscolare familiare nota.',
                 'vitals': 'PA 118/72 mmHg, FC 78/min, FR 15/min, SpO₂ 98% in aria, T 36,5 °C.',
                 'neuro': 'Ptosi bilaterale maggiore dopo sguardo sostenuto verso l’alto, diplopia fluttuante; lieve debolezza prossimale affaticabile. Sensibilità e riflessi conservati; pupille normali.',
                 'cranial': 'Ptosi e diplopia accentuate dallo sguardo prolungato; pupille isocoriche e fotoreagenti. Voce lievemente nasale dopo conteggio prolungato.',
                 'motor': 'Forza prossimale iniziale 4+/5 MRC, ridotta dopo movimenti ripetuti; recupero parziale con riposo.',
                 'sensory': 'Sensibilità superficiale e profonda conservata.', 'reflex': 'Riflessi osteotendinei presenti e simmetrici, plantari in flessione.',
                 'coordination': 'Coordinazione normale compatibilmente con la forza. Marcia autonoma.',
                 'blood': 'Hb 13,2 g/dL (12–16); Na 140 mmol/L (135–145); K 4,0 mmol/L (3,5–5,0); glicemia 90 mg/dL (70–100 a digiuno). Intervalli didattici.',
                 'emg': 'Stimolazione ripetitiva a bassa frequenza: decremento del potenziale motorio composto del 16% (soglia didattica di significatività >10%), maggiore nei muscoli prossimali. Referto simulato.',
                 'antibodies': 'Anticorpi anti-recettore ACh: 4,8 nmol/L (negativi <0,4 nel laboratorio simulato); anti-MuSK negativi.',
                 'respiration': 'Nessuna dispnea a riposo né uso dei muscoli accessori; capacità vitale forzata 43 mL/kg. Il dato va integrato con clinica e andamento, non esclude da solo rischio respiratorio.',
                 'mri': 'Nessuna lesione focale encefalica o midollare evidenziabile nel referto simulato.',
                 'consult': 'Richiesta rivalutazione di deglutizione, forza e funzione respiratoria; consulenza neurologica disponibile.',
             },
             pathway='Identificare fluttuazione e affaticabilità, verificare funzione bulbare e respiratoria, esaminare forza, pupille, sensibilità e riflessi. Localizzare alla giunzione neuromuscolare e cercare conferma con anticorpi e neurofisiologia, considerando le alternative.'),
        dict(topic='Malattie demielinizzanti', diagnosis='Sclerosi multipla con episodio midollare',
             aliases=['sclerosi multipla', 'multiple sclerosis'],
             arrival='Donna di 27 anni con formicolii alle gambe e difficoltà nella marcia, progressivi da cinque giorni. Non riferisce trauma; è vigile e orientata.',
             information=['history', 'neuro', 'sensory'], essential=['mri', 'csf'],
             useful=['vitals', 'medication', 'family', 'motor', 'reflex', 'cranial', 'blood', 'consult'], priority=['mri'],
             localization=['midoll', 'centrale', 'piramidal', 'toracic'],
             evidence=['episod', 'ottic', 'dissemin', 'bande', 'periventricolar', 'midoll'],
             differentials=['compressione midollare', 'NMOSD', 'malattia associata ad anticorpi MOG', 'carenza di vitamina B12'],
             reports={
                 'history': 'Paziente: «Un anno fa vedevo male da un occhio e mi faceva male muoverlo; poi era passato. Ora le gambe sono rigide e sento meno dal torace in giù». Nessuna febbre, recente infezione o sintomo sistemico riferito.',
                 'medication': 'Nessuna terapia cronica. Nessun uso di protossido di azoto riferito.',
                 'family': 'Nessuna patologia neurologica familiare nota.',
                 'vitals': 'PA 115/75 mmHg, FC 74/min, FR 14/min, T 36,6 °C, SpO₂ 99% in aria.',
                 'neuro': 'Paraparesi spastica lieve, iperreflessia agli arti inferiori e Babinski bilaterale, livello sensitivo toracico. Arti superiori senza deficit di forza.',
                 'motor': 'Arti inferiori 4/5 MRC bilateralmente con tono aumentato; arti superiori 5/5.',
                 'sensory': 'Ridotta sensibilità tattile e dolorifica da circa T6 in basso, ridotta pallestesia ai piedi.',
                 'reflex': 'Iperreflessia rotulea e achillea, risposta plantare estensoria bilaterale.',
                 'cranial': 'Lieve pallore papillare sinistro; non deficit oculomotori attuali.',
                 'coordination': 'Marcia spastica, non atassia degli arti superiori.',
                 'blood': 'Hb 13,0 g/dL (12–16), Na 140 mmol/L (135–145), glicemia 89 mg/dL (70–100 a digiuno); B12 420 pg/mL (200–900). Intervalli didattici.',
                 'mri': 'RM encefalo e midollo con contrasto: lesioni T2 periventricolari e juxtacorticali, alcune con enhancement e altre senza; lesione midollare breve a T5. Nessuna compressione. Referto didattico simulato.',
                 'csf': 'Liquor: 3 cellule/µL (0–5); proteine 34 mg/dL (15–45); bande oligoclonali IgG presenti nel liquor e assenti nel siero (pattern intratecale). Intervalli didattici.',
                 'consult': 'Il neurologo richiede integrazione di anamnesi, RM e liquor e valutazione delle diagnosi alternative prima della conclusione.',
             },
             pathway='Localizzare una sindrome midollare; escludere compressione con RM; ricercare episodi precedenti e segni di disseminazione spaziale e temporale, integrando RM e liquor. Considerare NMOSD, MOGAD e altre cause. I criteri diagnostici richiedono sempre esclusione di spiegazioni migliori.'),
    ]


def prepare(dossier, level, complexity):
    d = dict(dossier)
    d['reports'] = dict(dossier['reports'])
    for key in ACTION_MAP:
        d['reports'].setdefault(key, 'Dato non disponibile nel dossier: questo accertamento non è stato simulato. La mancata disponibilità non equivale a un risultato normale.')
    d['source'] = d.get('source', 'Demo redazionale: paziente fittizio, contenuto integrativo non tratto dai tuoi materiali; da sottoporre a revisione clinica.')
    d['rubric'] = RUBRIC
    d['thresholds'] = THRESHOLDS
    d['level'], d['complexity'] = level, complexity
    # Adapt the expected work, not the rarity of the diagnosis.
    d['expected_alternatives'] = 2 if level == 'specializzando' or complexity == 'avanzata' else 1
    d['require_localization'] = level == 'specializzando' or complexity != 'base'
    return d


def route(text, use_ai=False):
    t = norm(text)
    if any(x in t for x in ['ipotizzo', 'penso che', 'diagnosi', 'potrebbe essere', 'sospetto']):
        return {'kind': 'hypothesis'}
    matches = {key for key, _, _, words in ACTIONS if any(norm(w) in t for w in words)}
    if len(matches) == 1:
        return {'kind': 'action', 'action': matches.pop()}
    if use_ai:
        result = ai.complete('Interpreta UNA richiesta senza valutare diagnosi. Restituisci {"kind":"action|clarify|hypothesis", "action":"ID oppure null"}. Se ambigua, più richieste insieme, ipotesi diagnostica o esame non elencato: chiarisci o hypothesis. Non sostituire esami. Nessuna risposta clinica.',
                             {'request': text, 'actions': [{'id': a[0], 'label': a[2]} for a in ACTIONS]})
        if result.get('kind') == 'action' and result.get('action') in ACTION_MAP:
            return result
        if result.get('kind') == 'hypothesis':
            return result
    return {'kind': 'clarify', 'message': 'Specifica una sola richiesta scegliendo un’azione dal menu, oppure scrivi “ipotizzo …” per annotare un’ipotesi. Non è stato assegnato alcun esame.'}


def evaluate(case, submission):
    d = case['dossier']
    requested = list(dict.fromkeys(e['action'] for e in case['events'] if e.get('action')))
    seen = set(requested)
    # Requesting each component is equivalent to requesting a complete exam.
    if {'cranial', 'motor', 'sensory', 'reflex', 'coordination'}.issubset(seen):
        seen.add('neuro')
    info = round(20 * len(seen.intersection(d['information'])) / len(d['information']), 1)
    rationale = norm(submission['rationale'])
    loc = norm(submission['localization'])
    collected = norm(d['arrival'] + ' '.join(e['response'] for e in case['events'] if e.get('action')))
    evidence = [w for w in d['evidence'] if norm(w) in rationale and norm(w) in collected]
    localized = any(norm(w) in loc for w in d['localization'])
    alternatives = [s.strip() for s in re.split(r'[,;\n]', submission['alternatives']) if len(s.strip()) > 3]
    # Semantic quality is not inferred from length; only explicit fixed evidence terms count.
    reasoning = round(12 * min(1, len(evidence) / 2) + (8 if localized else (4 if not d['require_localization'] else 0)) + 5 * min(1, len(alternatives) / d['expected_alternatives']), 1)
    essential = seen.intersection(d['essential'])
    relevant = set(d['information'] + d['essential'] + d['useful'] + d['priority'])
    unnecessary = [a for a in requested if a not in relevant]
    first_test = next((a for a in requested if ACTION_MAP[a][1] in ('Imaging', 'Laboratorio', 'Neurofisiologia', 'Approfondimenti', 'Consulenze')), None)
    priority = first_test in d['priority'] or (first_test == 'blood' and d['topic'] == 'Patologie cerebrovascolari')
    investigations = round(max(0, 20 * len(essential) / len(d['essential']) + (5 if priority else 0) - min(5, 1.5 * len(unnecessary))), 1)
    diagnosis_text = norm(submission['diagnosis'])
    correct = any(norm(s) in diagnosis_text for s in d['aliases']) and not re.search(r'\b(non|escludo|esclusa|escludere)\b', diagnosis_text)
    diagnosis = (20 if correct else 0) + round(10 * min(1, len(evidence) / 2), 1)
    values = [info, reasoning, investigations, diagnosis]
    total = round(sum(values), 1)
    missing = [a for a in d['information'] + d['essential'] if a not in seen]
    return {
        'total': total, 'stars': sum(total >= t for t in THRESHOLDS),
        'dimensions': [dict(r, score=v) for r, v in zip(RUBRIC, values)],
        'diagnosis': d['diagnosis'], 'correct': correct, 'expected_alternatives': d['differentials'],
        'strengths': [ACTION_MAP[a][2] for a in requested if a in relevant],
        'omissions': [ACTION_MAP[a][2] for a in missing],
        'unnecessary': [{'label': ACTION_MAP[a][2], 'reason': 'Non aggiunge informazioni al percorso essenziale fissato per questo dossier. Un percorso alternativo motivato può richiedere revisione manuale.'} for a in unnecessary],
        'pathway': d['pathway'], 'topic': d['topic'], 'hints_used': len(case['hints']),
        'priority_met': priority, 'evidence_terms': evidence,
        'limits': 'Valutazione automatica euristica, non giudizio di competenza clinica: riconosce sinonimi predefiniti, termini di supporto, localizzazione e numero di alternative; non verifica semanticamente la correttezza delle alternative. Percorsi alternativi e sinonimi non riconosciuti possono essere segnalati per revisione. Senza motivazione non ci sono dati sufficienti per valutare il ragionamento.',
        'explanation': f'Informazioni: {len(seen.intersection(d["information"]))}/{len(d["information"])} azioni attese ×20. Ragionamento: 12 punti per almeno due reperti motivati, 8 per localizzazione (4 di base se non richiesta), 5 per {d["expected_alternatives"]} alternative. Accertamenti: frazione essenziali ×20 +5 per priorità, −1,5 per richiesta superflua (massimo −5). Diagnosi: 20 per sinonimo riconosciuto +10 per almeno due reperti motivati. Suggerimenti dichiarati, senza penalità.',
        'engine': 'euristico locale',
    }


def semantic_evaluation(case, submission, fallback):
    """An optional semantic judge, constrained to the frozen rubric and observed events."""
    from fastapi import HTTPException
    task = ('Valuta il ragionamento di uno studente sul dossier fissato. Non modificare diagnosi, reperti, pesi o soglie. '
            'Usa soltanto le azioni effettive, accetta sinonimi e percorsi alternativi clinicamente ragionevoli, non premiare quantità. '
            'Nessuna penalità per suggerimenti. Adatta aspettative al livello già fissato. '
            'Se una dimensione non è valutabile, indica insufficienza dati e non inventare prove. '
            'Rispondi {"dimensions":[{"key":string,"score":numero,"reason":string,"event_indices":[indici da zero]}], '
            '"strengths":[{"event_index":numero,"reason":string}], '
            '"omissions":[{"action_id":string,"reason":string}], '
            '"unnecessary":[{"event_index":numero,"reason":string}], '
            '"correct":boolean,"explanation":string}. Quattro dimensioni con chiavi information/reasoning/investigations/diagnosis, '
            'massimi 20/25/25/30. Ogni riferimento deve corrispondere a un evento reale, omissioni solo azioni non eseguite. '
            'La diagnosi indovinata senza percorso non può dare il massimo. Motiva in italiano usando i dati raccolti, '
            'non informazioni del dossier che lo studente non ha richiesto. Considera motivazione, localizzazione e differenziali della consegna.')
    try:
        result = ai.complete(task, {'dossier': case['dossier'], 'events': case['events'], 'hints': case['hints'],
                                    'submission': submission, 'action_catalog': [{'id': a[0], 'label': a[2]} for a in ACTIONS]})
        if not isinstance(result, dict) or not isinstance(result.get('correct'), bool):
            raise ValueError('Formato')
        dimensions = result['dimensions']
        if len(dimensions) != 4 or {d['key'] for d in dimensions} != {r['key'] for r in RUBRIC}:
            raise ValueError('Dimensioni')
        events = case['events']
        requested = {e['action'] for e in events if e.get('action')}
        valid_event = lambda i: type(i) is int and 0 <= i < len(events) and bool(events[i].get('action'))
        verified = []
        for rubric in RUBRIC:
            d = next(d for d in dimensions if d['key'] == rubric['key'])
            if (type(d['score']) not in (int, float) or not 0 <= d['score'] <= rubric['weight']
                    or not isinstance(d['reason'], str) or not d['reason'].strip()
                    or not isinstance(d['event_indices'], list) or not all(valid_event(i) for i in d['event_indices'])):
                raise ValueError('Punteggio o evidenza')
            if not requested and rubric['key'] in ('information', 'investigations') and d['score']:
                raise ValueError('Nessuna azione')
            verified.append(dict(rubric, score=round(d['score'], 1), reason=d['reason'], event_indices=d['event_indices']))
        strengths, omissions, unnecessary = [], [], []
        for s in result['strengths']:
            if not valid_event(s['event_index']) or not isinstance(s['reason'], str):
                raise ValueError('Punto di forza non osservato')
            strengths.append(events[s['event_index']]['request'] + ': ' + s['reason'])
        for s in result['omissions']:
            if s['action_id'] not in ACTION_MAP or s['action_id'] in requested or not isinstance(s['reason'], str):
                raise ValueError('Omissione non valida')
            omissions.append(ACTION_MAP[s['action_id']][2] + ': ' + s['reason'])
        for s in result['unnecessary']:
            if not valid_event(s['event_index']) or not isinstance(s['reason'], str):
                raise ValueError('Richiesta non osservata')
            unnecessary.append({'label': events[s['event_index']]['request'], 'reason': s['reason']})
        total = round(sum(d['score'] for d in verified), 1)
        if not isinstance(result['explanation'], str):
            raise ValueError('Motivazione')
        return dict(fallback, dimensions=verified, total=total, stars=sum(total >= t for t in THRESHOLDS),
                    strengths=strengths, omissions=omissions, unnecessary=unnecessary, correct=result['correct'],
                    explanation=result['explanation'], engine='IA semantica',
                    limits='Valutazione didattica generata da IA sui dati del dossier e sulle azioni registrate, con controllo di pesi e riferimenti agli eventi. Può contenere errori: i percorsi alternativi e le valutazioni incoerenti possono essere segnalati per revisione.')
    except (HTTPException, ValueError, KeyError, IndexError, TypeError, StopIteration):
        return dict(fallback, limits='Il valutatore IA non ha restituito un giudizio verificabile. È stato usato il valutatore locale. ' + fallback['limits'])
