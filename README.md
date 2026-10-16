# NeuroStudy

Web app personale in italiano per lo studio della neurologia. Libreria, quiz, flashcard e casi clinici con dashboard: dati persistenti, nessuna rigenerazione all'apertura. Solo formazione, pazienti simulati.

## Avvio su Windows con doppio clic

Non aprire `app/static/index.html` come file: l'app usa anche un server Python e un database.

1. Scarica **l'intero progetto** dal ramo `codex/neurostudy-v1` su GitHub: **Code → Download ZIP**. Estrai lo ZIP in una cartella.
2. Installa Python **3.12 o successivo** da https://www.python.org/downloads/ se manca. Durante l'installazione abilita **Add Python to PATH**.
3. Nella cartella estratta fai doppio clic su **Avvia NeuroStudy.cmd**. Al primo avvio scarica le dipendenze, poi apre l'app nel browser.
4. Scegli la password nella pagina dell'app. Mantieni aperta la finestra del programma durante lo studio; Ctrl+C arresta il server.

Per gli avvii successivi usa lo stesso file nella stessa cartella: i tuoi dati rimangono in `.data`. Serve una connessione per la prima installazione; lo studio locale/demo non richiede IA. Se la porta 8000 è già occupata, la finestra di avvio lo segnala senza aprire altri servizi.

Su macOS/Linux, dalla cartella del progetto: `python3 start.py`. Il launcher prepara l'ambiente e apre il browser dopo aver verificato la disponibilità del servizio. Opzioni: `--no-browser`, `--port 8001` e `--lan` per l'accesso dalla rete locale.

## Android sulla stessa rete Wi-Fi di Windows

Android non richiede Python o installazione: usa Chrome aggiornato sul telefono. Il server rimane sul PC Windows; telefono e PC leggono lo **stesso database**, quindi materiali, ripassi, casi e appunti sono condivisi. Non copiare HTML sul telefono e non usare `localhost` sul telefono: indicherebbe il telefono stesso.

1. **Una sola volta:** avvia `Avvia NeuroStudy.cmd` sul PC e scegli la password nella pagina dell'app. Poi arresta il programma con Ctrl+C.
2. Avvia **Avvia NeuroStudy WiFi.cmd**. L'avvio Wi-Fi verifica prima che esista una password; se manca, non espone il server in rete e mostra le istruzioni.
3. Se Windows Firewall lo richiede, consenti Python **solo sulla rete privata** di casa. Il launcher non cambia il firewall automaticamente.
4. Collega Android alla **stessa rete Wi-Fi** del PC. Nella finestra di avvio appariranno uno o più indirizzi locali del PC: apri quello della rete Wi-Fi nel browser del telefono, poi inserisci la stessa password. Esempio di formato: `http://IP-DEL-PC:8000`. Non usare `0.0.0.0` come indirizzo nel browser.
5. Mantieni acceso il PC, senza sospensione, con il programma aperto durante lo studio. Le modifiche sono salvate subito sul PC; ricaricando l'altro dispositivo trovi gli aggiornamenti. Non c'è un aggiornamento automatico in tempo reale fra due pagine già aperte.

Se non si collega: verifica rete privata, autorizzazione firewall per Python e indirizzo IPv4 della scheda Wi-Fi con `ipconfig`. Reti ospiti con isolamento dei dispositivi possono impedirlo; VPN e altre schede possono produrre indirizzi non raggiungibili dal telefono. Il launcher elenca candidati locali senza inviare dati a servizi esterni.

L'accesso locale usa HTTP: serve una rete fidata, senza dati identificativi di pazienti. Non aprire porte del router per esporlo su Internet. Non funziona quando il PC è spento o il telefono è fuori rete: per quell'uso servirà un server online con HTTPS e volume persistente.

L'interfaccia include layout mobile e controlli touch. I test usano Chromium con emulazione Android Pixel 7 (touch, viewport e user agent) e un secondo accesso allo stesso database; non equivalgono a una prova su uno smartphone fisico. La CI esegue i controlli anche su Windows; gli esiti remoti vanno consultati in GitHub Actions.

## Avvio manuale

Richiede Python 3.12+. Non servono Node o un servizio database per usare l'app.

```bash
cd /workspace/study  # oppure la directory in cui hai clonato il repository
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Apri la porta 8000 nel tuo ambiente di sviluppo e scegli una password di almeno 10 caratteri al primo accesso. Non esporre l'istanza prima di aver impostato la password. Per un servizio pubblico usa HTTPS, un reverse proxy e `STUDY_PASSWORD` impostata in modo sicuro **prima del primo avvio**. La password viene conservata soltanto come hash scrypt con salt; i cookie di sessione sono HttpOnly e SameSite Strict, Secure quando la richiesta usa HTTPS. Configura il proxy per inoltrare lo schema HTTPS in modo attendibile. Non usare `--forwarded-allow-ips='*'` su una porta accessibile direttamente.

Il servizio è pensato per **un utente per istanza**. Autenticazione, rate limit di login e controlli di origine sono inclusi; multiutenza, recupero password, SSO, cifratura a riposo e backup gestiti non sono inclusi. Non usarlo con dati identificativi di pazienti o come sistema clinico.

## Dati persistenti

SQLite salva tutto in `.data/study.sqlite3` (directory ignorata da Git). `STUDY_DATA_DIR` può indicare un volume persistente diverso; usa un percorso assoluto. Non cambiare directory dati per errore fra due avvii. Nei container monta un volume e imposta `STUDY_DATA_DIR=/data`.

- I documenti originali vengono elaborati e scartati; rimangono testo estratto, avvisi e metadati.
- Le citazioni comprendono documento, versione, sezione/pagina e testo letterale.
- Un aggiornamento del documento non cambia automaticamente i contenuti esistenti. Puoi contrassegnarli per revisione e rigenerarli esplicitamente. La rigenerazione sostituisce il singolo originale solo se ottiene un risultato valido; le sessioni quiz precedenti conservano la loro copia.
- Eliminare un documento conserva le citazioni storiche nei contenuti collegati, segnalandoli. Per rimuovere anche quelle, elimina i contenuti interessati. Le copie nelle sessioni passate e nei backup/esportazioni restano: questa versione non include una procedura di cancellazione selettiva completa.
- La dashboard consente di esportare un JSON con materiali, contenuti, sessioni, scadenze e segnalazioni; non contiene password, chiavi o dossier nascosti. L'importazione non è inclusa.
- Per un backup completo, arresta il servizio e copia l'intera directory dati (include autenticazione e dossier). Proteggila: i testi non sono cifrati. Non commetterla in Git.

## Funzioni

### Libreria e generazione

Caricamento PDF, DOCX, PPTX, TXT UTF-8 e Markdown, organizzazione per argomento e corso/esame, lettura del testo estratto e selezione di sezioni. Limiti: 20 MB, 600 pagine PDF, 80 MB decompressi per Office, 1,5 milioni di caratteri estratti. Scansioni senza testo segnalate come richiedenti OCR; OCR non implementato. Immagini, formule e altre parti non elaborate sono segnalate. I numeri di pagina sono disponibili per PDF; DOCX usa sezioni/tabelle e PPTX diapositive.

Due motori separati:

1. **Locale estrattivo**, sempre disponibile: produce completamenti e quiz di richiamo letterale. Non simula una comprensione clinica, non adatta la difficoltà e non è un rilevatore di contraddizioni. Gli esercizi sono contrassegnati per revisione.
2. **IA**, opzionale: genera domande singole/multiple, vignette quando supportate e schede domanda/risposta o cloze. Il server verifica schema, indici, citazione letterale, origine e duplicati esatti. Ambiguità/discordanze devono essere segnalate dal modello. I risultati richiedono comunque revisione: corrispondenza letterale della citazione non significa validazione clinica, e la deduplicazione semantica non è garantita.

Le istruzioni eventualmente contenute nei file sono trattate come dati non attendibili; non vengono eseguite e non possono usare strumenti sul server. Non è possibile garantire che un modello non venga influenzato nel testo generato: revisione e verifica delle citazioni restano necessarie. Nessuna correzione automatica dei documenti e nessuna fonte esterna inventata.

### Quiz

Filtri per argomento, fonte, numero, difficoltà, nuove/sbagliate/salvate/miste, timer e modalità allenamento/esame. La correzione esame non è restituita dall'API della sessione fino alla consegna; la banca personale resta consultabile e non è un sistema antifrode. Spiegazione, alternative, citazioni, segnalazione, segnalibri e anteprima prima di creare una flashcard. Risposte immutabili dopo conferma. Domande insufficienti: sessione più breve dichiarata, mai duplicati aggiunti. Gli errori storici aumentano la probabilità di ricomparsa, progressivamente ridotta da successi ripetuti; nessuna singola risposta assegna padronanza.

### Flashcard

Creazione manuale o da fonte/quiz, formati Q/A e cloze, mazzi per argomento e fonte, modifica, sospensione, eliminazione e approvazione. La risposta di una scheda in ripasso è restituita solo dopo rivelazione. Scheduler ispirato a SM-2 con intervallo e facilità persistenti:

- Da ripetere: 10 minuti, facilità −0,20.
- Difficile: max(1 giorno, intervallo ×1,2), facilità −0,15.
- Bene: primo ripasso 1 giorno; poi max(2 giorni, intervallo ×facilità).
- Facile: max(4 giorni, intervallo ×facilità ×1,3), facilità +0,15.

Facilità minima 1,3, massima 3,2. Arretrati prima dei nuovi, carico giornaliero configurabile; la scheda fallita torna dopo 10 minuti in un nuovo ripasso, nel limite giornaliero. Il giorno è calcolato in Europe/Rome. Obiettivo dashboard espresso in flashcard personali valutate; demo escluse dalle metriche personali, ma comprese nel limite di carico.

### Casi clinici

Tre dossier demo redazionali (neurovascolare, neuromuscolare, demielinizzante), chiaramente etichettati, oppure nuovi dossier IA. Sono dati sintetici non revisionati clinicamente. Livello, complessità, argomento/casuale, guida/esame e timer. Complessità/livello cambiano supporto e aspettative su localizzazione/differenziali; nei casi IA cambiano anche presentazione e complessità delle alternative. Le tre demo restano gli stessi pazienti e gli stessi reperti: non sono una banca estesa.

Il dossier viene salvato prima dell'arrivo; diagnosi, referti e rubriche non vengono trasmessi al browser prima del momento pertinente. Azioni da menu ricercabile e testo libero, cronologia, annotazioni persistenti, suggerimenti progressivi solo in modalità guidata. Le richieste ripetute leggono lo stesso referto. Nessun cambiamento temporale implicito: i dossier rappresentano un singolo momento clinico; un dato non simulato resta dichiarato non disponibile, non viene inventato né trasformato in normalità.

Nelle demo il testo libero usa sinonimi/termini predefiniti: una richiesta non identificabile o con più azioni richiede chiarimento. Nei casi IA un classificatore vede richiesta e catalogo azioni, **non la diagnosi**; può scegliere solo un'azione valida o chiedere chiarimento, senza sostituire un esame. Le ipotesi vengono annotate senza conferma.

Consegna con diagnosi, motivazione, localizzazione e alternative; feedback per azioni effettive, omissioni, richieste poco utili, possibile percorso e collegamenti ai contenuti esistenti. Rubrica fissata: informazioni 20%, ragionamento/localizzazione 25%, appropriatezza/priorità 25%, diagnosi/motivazione 30%. Stelle: 1 sotto 40; 2 da 40; 3 da 55; 4 da 70; 5 da 85. Stesse soglie scalate per ogni dimensione. Aiuti dichiarati senza penalità.

- **Demo:** valutatore euristico deterministico con formula visibile prima dell'inizio e spiegazione del calcolo. Supporto basato su parole chiave nei reperti effettivamente raccolti; riconosce sinonimi diagnostici fissati nel dossier. Non comprende semanticamente i differenziali e può non riconoscere un percorso ragionevole: il limite è esplicito nel feedback.
- **Casi IA:** valutazione semantica aggiuntiva con pesi e soglie invariati. Il server verifica punteggi, riferimenti a eventi reali e omissioni non già eseguite. Se la risposta non è verificabile, usa il valutatore locale e lo dichiara. L'IA non è un docente o una certificazione; può sbagliare anche con uno schema valido.

Le segnalazioni vengono salvate localmente ed esportate, non inviate ad altri. Non c'è un servizio di revisione umana incluso.

## Attivare l'IA

Imposta sul server, attraverso i segreti dell'ambiente (mai nel browser, nel repository o in chat):

| Variabile | Scopo |
| --- | --- |
| `STUDY_AI_KEY` | Credenziale per un endpoint OpenAI compatibile |
| `STUDY_AI_BASE_URL` | Default `https://api.openai.com/v1`, solo HTTPS |
| `STUDY_AI_MODEL` | Default `gpt-4.1-mini`, modello con output JSON |
| `STUDY_PASSWORD` | Password iniziale opzionale, almeno 10 caratteri; letta solo quando il database non ha ancora password |
| `STUDY_DATA_DIR` | Directory database persistente, default `.data` |

Riavvia dopo aver impostato le variabili. La libreria consente di scegliere esplicitamente IA o estrazione locale; i casi consentono demo o IA. Solo i testi selezionati sono inviati al servizio per generare quiz/schede; i casi IA usano contenuti integrativi sintetici e inviano dossier e azioni al valutatore. Il provider può applicare costi e condizioni di trattamento dati. Non c'è recupero esterno di fonti, motore di ricerca o accesso a materiali diversi da quelli selezionati. Timeout e errori vengono mostrati senza inventare un risultato.

## Verifica

```bash
.venv/bin/python -m pytest -q
```

Test integrati su database temporanei: autenticazione/origine, estrazione Office/PDF illeggibili, fonti e revisioni, generazione, quiz ed esame, scheduler e carico, coerenza/privacy dei dossier, rubrica, scadenze, separazione demo, controlli dei risultati IA con risposte simulate.

Per verificare l'interfaccia completa (Node 22+ solo per questi test):

```bash
npm ci
npx playwright install chromium
npm run test:browser
# Se Chromium è già installato:
CHROMIUM_PATH=/usr/bin/chromium npm run test:browser
```

Il test avvia un server su porta 8011 e un database temporaneo, esegue caricamento → generazione → quiz → flashcard → ripasso e caso → ripresa → valutazione, verifica mobile, tema scuro e una seconda sessione Android emulata con tocchi e dati condivisi. Usa `.venv/Scripts/python.exe` su Windows e `.venv/bin/python` su Linux/macOS. Screenshot in `test-results/`, ignorata da Git. `STUDY_TEST_PORT` permette di cambiare la porta. Le chiamate IA reali non sono state verificate senza credenziali: i test dei contratti usano risposte simulate, senza costi o invio di materiali.

## Architettura

FastAPI per API e gestione server delle credenziali, SQLite con transazioni per persistenza senza servizi aggiuntivi, HTML/CSS/JavaScript nativi per un'interfaccia responsive senza build o CDN. Login personale e controlli su ogni API; file statici senza dati personali. Cookie e origine proteggono le mutazioni; output dei materiali sempre reso come testo, CSP senza script inline.

Moduli separati: `store.py` (persistenza), `documents.py` (estrazione), `ai.py` (provider), `cases.py` (dossier/rubrica), `main.py` (API), `static/` (interfaccia). Nuove sezioni possono aggiungere router e componenti senza costruirle ora. Specifica originale in `docs/SPEC.md`.

Questa versione funziona come strumento personale di studio. Prima di un rilascio pubblico multiutente servono separazione degli account e dei dati, backup/ripristino gestiti, revisione di sicurezza e validazione didattica dei casi e del valutatore. Non è stata pubblicata online dal setup.
