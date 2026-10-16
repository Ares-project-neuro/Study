# Pubblicare NeuroStudy su GitHub Pages

GitHub Pages ospita la **versione autonoma nel browser**. Non serve Python sul computer o sul telefono: si apre il sito in Chrome/Edge su Windows o Chrome su Android, anche con il PC spento. La versione Python precedente rimane nel repository e continua a funzionare per l'uso con database condiviso e IA server.

## Attivazione nel repository

Le modifiche sono nel ramo **`codex/neurostudy-v1`**.

1. Apri il repository `Ares-project-neuro/Study` su GitHub.
2. Vai in **Settings → Pages → Build and deployment** e imposta **Source: GitHub Actions**. Le opzioni Pages devono essere disponibili per la visibilità e il piano del repository; questo progetto non cambia la visibilità del repository.
3. Vai in **Actions → Publish NeuroStudy to GitHub Pages**. Il push del ramo avvia il workflow automaticamente; se il primo tentativo era fallito perché Pages non era ancora attivo, apri l'esecuzione e usa **Re-run all jobs** dopo aver completato il punto 2.
4. Se l'ambiente `github-pages` richiede approvazione, autorizza il deployment da quel pannello. Se ha restrizioni sui rami, consenti `codex/neurostudy-v1` oppure incorpora le modifiche in `main` prima di pubblicare.
5. Quando il job `deploy` termina, usa il collegamento prodotto dall'azione o quello in **Settings → Pages**. Non aprire `index.html` dai Download.

Il workflow pubblica i push a `main` e `codex/neurostudy-v1`, oltre all'avvio manuale. Il pulsante **Run workflow** è disponibile quando il file workflow è presente nel ramo predefinito; fino ad allora usa l'esecuzione partita dal push e la relativa riesecuzione. Quando lo sviluppo verrà incorporato in `main`, puoi limitare il trigger a `main` per avere un solo ramo di pubblicazione.

Il workflow installa le dipendenze bloccate, costruisce `_site/`, esegue i test della versione statica e carica **solo `_site/`** come artifact Pages. Non pubblica `.data`, database SQLite, documenti personali, `.env`, chiavi IA o il server Python. Non impostare Source su una cartella del repository: i file pronti per il sito sono generati dal workflow.

**La presenza del workflow e il push del codice non provano che il sito sia già online.** La pubblicazione richiede le impostazioni sopra e un job `deploy` riuscito. L'attivazione del sito non è stata eseguita dall'agente.

## Cosa funziona nella versione Pages

| Funzione | Pages |
| --- | --- |
| Interfaccia Windows / Android, chiaro/scuro | Disponibile nel browser aggiornato |
| Materiali TXT, MD, DOCX, PPTX, PDF testuali | Estratti sul dispositivo, senza upload a un'API |
| Immagini e scansioni | Segnalate; nessun OCR |
| Quiz / flashcard dai materiali | Generazione estrattiva locale, con fonte e revisione |
| Quiz allenamento / esame, timer, segnalibri | Disponibili, sessioni persistenti |
| Flashcard manuali / da quiz, ripassi e scadenze | Disponibili, stesso scheduler della versione server |
| Casi clinici | Tre dossier demo redazionali e valutatore euristico |
| Cronologia, appunti, ripresa, dashboard | Disponibili localmente |
| Backup e trasferimento PC / Android | Esportazione e importazione cifrate, manuali |
| IA generativa e valutazione semantica | Disattivate: Pages non esegue Python o servizi IA |
| Sincronizzazione automatica fra dispositivi | Non inclusa; richiede un server condiviso |

Non sono state inserite chiavi IA nel JavaScript. Per conservare le funzioni IA usa la versione Python con credenziale sul server; un futuro collegamento fra Pages e un backend HTTPS richiederà gestione dedicata di autenticazione e accessi. Il sito statico attuale non promette né tenta chiamate a un backend inesistente.

## Archivio, password e backup

Al primo accesso scegli una password di almeno 10 caratteri. La password **cifra l'archivio locale**, non crea un account GitHub o un account online. Tutti i dati applicativi sono salvati in IndexedDB come un unico archivio cifrato AES-256-GCM, con chiave derivata dalla password tramite PBKDF2-SHA256 (310.000 iterazioni), salt casuale e IV casuale a ogni salvataggio. La password e la chiave non vengono memorizzate nel repository né inviate a un servizio. La chiave rimane nella memoria della scheda fino all'uscita o al ricaricamento; dopo il reload devi sbloccare di nuovo l'archivio.

**Non esiste recupero della password.** Conserva la password e un backup. La cifratura a riposo non protegge da estensioni malevole o script compromessi mentre l'archivio è sbloccato; usa un dispositivo fidato. Il sito pubblico e i suoi file JavaScript non sono protetti da questa password.

Materiali e progressi appartengono al **browser e all'indirizzo del sito**. Cancellare dati del sito, usare navigazione privata, cambiare browser, dominio o percorso può rendere i dati precedenti inaccessibili. Il browser può rimuovere dati in caso di poco spazio; la richiesta di archiviazione persistente è facoltativa e non equivale a un backup. L'app segnala salvataggi negati o spazio insufficiente.

Per trasferire lo studio da PC ad Android:

1. Sul PC, nell'app, premi **Esporta backup cifrato**.
2. Trasferisci il file JSON sul telefono con il metodo che preferisci.
3. Apri lo stesso sito Pages su Android e premi **Importa un backup cifrato** (disponibile anche prima di creare un archivio).
4. Scegli il file e inserisci la password usata sul PC. Conferma la sostituzione dell'archivio del telefono.

L'importazione verifica la password prima di sostituire i dati. Ripristina anche sessioni, dossier, cronologia, scadenze e impostazioni. **Sostituisce l'archivio, non unisce due dispositivi.** Se hai studiato separatamente su entrambi, esporta prima entrambi i backup per non perdere attività.

L'esportazione originale **Esporta i dati di studio** resta disponibile come JSON leggibile: contiene testi e progressi non cifrati, non è un backup completo per il ripristino e non contiene i dossier interni. Proteggila. Il nuovo importatore accetta i backup cifrati Pages, non il database SQLite o le precedenti esportazioni leggibili. Nessun dato della versione Python viene cancellato o migrato automaticamente.

## Limiti dei casi e dei contenuti

Il dossier viene fissato prima dell'interazione, le richieste ripetute restituiscono lo stesso reperto, la diagnosi viene mostrata nell'interfaccia dopo la consegna. **In un sito statico il codice e i dossier demo sono scaricabili e ispezionabili dal browser**: questa è un'esercitazione personale, non un esame protetto. La cifratura dei progressi non rende segreti i dossier distribuiti insieme all'app.

Il generatore locale crea richiami letterali, non nuove spiegazioni cliniche o vignette con comprensione semantica. Richiede revisione. Citazioni verificabili non garantiscono validità clinica. Il valutatore dei casi usa azioni e parole chiave, con limiti dichiarati; le fonti esterne non vengono recuperate. Per le tre demo, i contenuti sono redazionali e non revisionati da un docente. Non usare dati identificativi di pazienti.

## Build e test locali

Node 22+ per la build; il workflow usa Node 24. Il sito pubblicato non richiede Node o Python. Tutte le librerie sono incluse negli asset dello stesso sito, senza CDN esterni per documenti o chiavi.

```bash
npm ci
npm run build:pages
```

Servi `_site/` con un server statico locale; il file scaricato via `file://` non è un metodo di avvio supportato. In locale puoi usare un server HTTP su loopback per verifiche interne; su Pages il servizio fornisce HTTPS. I percorsi relativi supportano sia `/Study/` sia la radice di un dominio personalizzato. Non usare il server di sviluppo per esporre la cartella completa con database personali.

```bash
# Per i test: ambiente Python e librerie servono solo a produrre fixture PDF/Office.
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npx playwright install chromium
npm run test:pages
# Se Chromium è già presente:
CHROMIUM_PATH=/usr/bin/chromium npm run test:pages
```

Il test serve esclusivamente `_site/` sotto `/Study/`, senza API Python, ed esercita upload ed estrazione TXT/DOCX/PPTX/PDF, avvisi scansioni, generazione, quiz esame senza correzione anticipata, flashcard e scadenze persistenti, cifratura, reload, importazione su Android emulato, password errata senza cancellazione, casi ripetibili, appunti e valutazione. La CI esegue anche la versione Python originale per intercettare regressioni.

I dossier statici sono in `browser/cases.json`, derivati dai dossier Python: quando aggiorni i contenuti redazionali esegui `.venv/bin/python scripts/export-cases.py` e verifica la coerenza delle due versioni. Nessun dossier viene generato casualmente a ogni apertura di una sessione salvata.
