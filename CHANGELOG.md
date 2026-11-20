# Changelog

Alle noemenswaardige wijzigingen. Formaat: [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/),
versies volgens [SemVer](https://semver.org/lang/nl/).

## [Unreleased]
### Added
- **De app bouwt zichzelf op GitHub**: bij elke push naar main draaien de controles op macOS en Windows, en worden de app voor de Mac (Apple-chip en Intel, als zip) en voor Windows (één .exe) gebouwd en even gestart om te zien of hij opent en de handleiding vindt. Met *Run workflow* en het vinkje *Uitgave maken* komen ze op de Releases-pagina, met uitleg in het Nederlands en Engels. Zelf bouwen: `python tools/build_app.py --zip`. De handleiding met plaatjes zit in de app, zodat de knop ? ook werkt zonder de map van het project.
- **Windows**: gevonden door de tests op Windows. Een kaartimage in de bibliotheek bleef open staan zolang het programma liep; op Windows kon je dat bestand dan niet hernoemen, verplaatsen of weggooien (ook niet in Verkenner). Nu wordt het alleen even geopend om te lezen. Het logbestand van de opdrachtregel wordt netjes gesloten.
- **Gewijzigde songnamen zichtbaar**: geef je een song een andere naam, dan is die naam in de songlijst geel (dezelfde kleur als de balk "nog niet op de kaart"), met de oude naam klein en grijs erachter: "HET IS FEEST (was: FEEST)". Klik je op de song, dan staat in het paneel rechts "Naam veranderd · Eerst heette deze song: FEEST" met de knop **Oude naam terugzetten** (één eigen stap, dus ook weer ongedaan te maken). Ook na verplaatsen of kopiëren weet de song zijn oude naam; zet je de oude naam zelf terug, dan verdwijnt het geel. Na Op kaart zetten is alles weer gewoon.
- **Wijzigingen terughalen na een onverwachte stop**: zolang er wijzigingen zijn die nog niet op de kaart staan, bewaart het programma ze na elke wijziging in zijn eigen map op de computer (`KN Songboek/concept`, naast de back-ups; nooit op de kaart). Stopt het programma onverwacht, dan vraagt het bij de volgende start of je wilt verdergaan waar je gebleven was (Ja, verdergaan / Nee, weggooien / Later beslissen). Dat werkt voor een geopende kaart (alleen als dezelfde kaart er onveranderd in zit) en voor een nieuwe kaart in elkaar zetten; ongedaan maken werkt daarna gewoon. Songs uit de bibliotheek worden niet gekopieerd maar aangewezen, en gecontroleerd bij het terughalen. Bij oefenen wordt niets bewaard. Op kaart zetten, weggooien of bewust afsluiten ruimt het bewaarde op.
- **Favorieten gaan mee met hele mappen**: kopieer je een of meer hele mappen uit de bibliotheek naar je kaart, dan gaan de favorietenknoppen van die songs mee. Zelfde bank en knopnummer als dat kan (als die bank op je kaart nog leeg is of dezelfde naam heeft), anders een andere bank met dezelfde naam, anders de eerste lege bank (die krijgt de naam van de oude bank). Favorieten op je kaart worden nooit overschreven; wat niet past wordt in een eigen venstertje gemeld. Alles in één ongedaan-maken-stap. Een kaart die als geheel wordt overgenomen houdt al zijn favorietenbanken zoals ze waren.
- **Vrolijker startscherm**: bovenaan een blauwe band met "Wat wil je doen?" en de naam van de app. Elke taak heeft een eigen kleur (blauw, groen, oranje): een streep links, het plaatje in een rondje van die kleur en een pijltje rechts. Onder de knoppen staat wat er in je bibliotheek zit ("In je bibliotheek: 12 kaarten en 8 diskettes, samen 1.240 songs"; het aantal songs zodra de bibliotheek open is geweest). Ook in donkere modus.
- **Privacycontrole strenger**: namen van AI-hulpmiddelen en de oude naam van de app (ook in commitberichten, auteurs en e-mailadressen), regels met een medeauteur in een commit, en verborgen informatie in PNG-plaatjes (tekst- of herkomstgegevens) worden nu ook gevonden. `tools/strip_png.py` haalt die verborgen informatie uit plaatjes; het plaatje zelf blijft gelijk.
- **Stapvensters**: bovenin ronde stapjes met een nummer (blauw = waar je bent, groen vinkje = klaar) op een lichte balk, daaronder "Stap 2 van 3". Terwijl het programma werkt staat er een lijstje van wat het doet (genoeg ruimte, back-up, op de kaart zetten, teruglezen en controleren) dat één voor één een groen vinkje krijgt, en onder de balk "Haal de kaart er nog niet uit." (of de diskette, of de USB-stick). Annuleren staat links, de volgende stap rechts. Bij Klaar is stap 3 de blauwe, de stappen ervoor hebben een vinkje.
- Ook in een stapvenster: **Kaart doet raar?** (Nakijken → Herstellen → Klaar, met Klaar na het herstellen), **Back-up terugzetten** (Zeker weten? → Terugzetten → Klaar), **Back-up in de bibliotheek zetten** (Naam → Bewaren → Klaar) en **Nu een back-up maken**.
- **Meer mappen tegelijk**: kies op de kaart meer mappen (Cmd/Shift-klik) en sleep ze samen tussen twee andere mappen; ze komen als blok te staan, de rest schuift op (één ongedaan-maken-stap). In de bibliotheek kun je ook meer mappen kiezen: de knop wordt "2 hele mappen toevoegen aan je kaart", of sleep ze samen naar de kaart (op een lege map: ze beginnen daar). Elke map komt in een eigen lege map, alles of niets.
- **Privacycontrole** (`tools/privacy_check.py`, ook in `tools/check.py`): zoekt kaart- en diskettebestanden, eigen paden, e-mailadressen, namen van andere programma's en eigen woorden uit `.privacy-words`. `--install` zet hem als git pre-push hook: een push met zulke dingen wordt gestopt. `--history` controleert alle commits.
- De app heet nu **KN Songboek**, overal: vensters, menu, Over, handleiding, de Python-package (`kn_songboek`) en de mappen voor instellingen en back-ups (`KN Songboek`).
- Over KN Songboek toont een link naar de projectpagina (https://github.com/D8bp8Ags/KN-Songboek) en niet meer de versies van Python en Qt.
- README voor GitHub (wat het doet, installeren, gebruik, veiligheid, status), CONTRIBUTING.md voor ontwikkelaars en een MIT-licentiebestand.
- `.gitignore` uitgebreid: build-mappen, caches van editors en tools, en als vangnet alle kaart- en diskettebestanden.
- Nieuwe opdrachten: `kn-songboek` start de app, `kn-songboek-cli` is de opdrachtregel.
- **Songlijst afdrukken en CSV**: nieuwe keuzes. Volgorde map voor map of alle songs op naam (A tot Z, met Map en Nr als kolom). In de PDF: eigen titel (voorstel "Songlijst" + kaartnaam), datum en "Pagina 1 van 3" onderaan (allebei uit te zetten), grote letters, lege mappen weglaten. Alles wordt onthouden, behalve de titel. Bovenaan het venster staat waar de lijst van gemaakt wordt: de SD-kaart in de kaartlezer, een kaart uit de bibliotheek, een kaart in een map of de nieuwe kaart die je samenstelt. De PDF bleef leeg in donkere modus (witte tekst); de tekst is nu altijd zwart. **De hele bibliotheek** kan nu ook een songlijst worden (of alleen wat het filter laat zien): kaart voor kaart, of op naam met "Staat op" (kaart, map en nummer). Lege kolommen gaan uit de PDF, woorden worden niet meer afgebroken, Akkoorden staat kort ("zelf spelen", of "gemengd"), en de kolommen krijgen precies de ruimte die het papier heeft: eerst kleinere letters (tot 8 punt), en pas als het dan nog niet past worden de breedste teksten ingekort met "…". Minder kolommen kiezen geeft dus meteen meer ruimte. Nieuw vinkje: songs in diskette-sets elk op een eigen regel, met een kolom "Uit set". Nieuw vinkje: liggend papier.
- `tools/github_snapshot.py`: maakt of werkt de tak `public` bij met de bestanden van main, zonder de geschiedenis van deze computer. Die tak gaat naar GitHub, waar hij `main` heet. Met `--push` gaat hij er meteen heen (na de privacycontrole).

- **Songlijst: één venster voor PDF en CSV.** Bovenaan kies je "Opslaan als" PDF of CSV; achter allebei zit dezelfde code die de lijst maakt, alleen het wegschrijven verschilt. De CSV is nu dezelfde lijst als de afdruk: zelfde volgorde, "Uit set" na de naam, lege kolommen weg, en Map/Mapnaam vooraan in elke regel (in de PDF zijn dat koppen). "Lege mappen weglaten" werkt nu ook voor de CSV. De opmaakkeuzes (titel, datum, letters, papier) zijn bij CSV grijs.
- **Verplaatsen naar… / Kopiëren naar…**: de mappen staan in een tabel met kolommen Map, Naam, Songs en Nog vrij, netjes onder elkaar. Een map zonder naam staat schuin.

- **Eén knop voor de songlijst**: "Songlijst opslaan (PDF of CSV)…" vervangt de twee knoppen (en menu-items) voor PDF en CSV; het venster onthoudt welke je de vorige keer koos.

### Removed
- Verwijzingen naar andere programma's uit code en documentatie; `.coverage` uit git (bevatte eigen paden); twee oude schermafbeeldingen (vervangen door de demo-plaatjes van de handleiding); het pad van een eigen kaartkopie in `.vscode/launch.json` en in de uitleg van de echte-kaarttest.
- **Vijf filters in de bibliotheek** (onder Filter): Nog niet op mijn kaart (herkent een song aan de inhoud, ook met een andere naam), Maat, Maar op één kaart / Op meer dan één kaart, Alleen van SD-kaarten / Alleen van diskettes, Alleen beschadigd (⚠). De knop laat zien hoeveel filters er aan staan, bijvoorbeeld "Filter (2)".

### Changed
- **Commits op GitHub op jouw naam**: `tools/github_snapshot.py` gebruikt de naam en het e-mailadres die in git voor de map staan (bij voorkeur het privé-adres van GitHub, `NNN+naam@users.noreply.github.com`; de privacycontrole laat dat adres door). Alleen zonder ingestelde naam blijft het `kn_songboek`.
- **Schermafbeeldingen per taal**: de Engelse handleiding en het Engelse deel van de README tonen de app in het Engels, met Engelse voorbeeldsongs. Ze staan bij hun taal: `docs/nl/img/` en `docs/en/img/`. `tools/make_screenshots.py` maakt ze allebei (of één taal: `nl` of `en`).
- Een nieuwe kaart kijkt eerst of hij past en maakt pas daarna de back-up van wat er op de SD-kaart stond (past hij niet, dan wordt er niets gedaan).
- **docs/ opgeruimd per taal**: `docs/nl/` (handleiding en alle Nederlandse documentatie), `docs/en/` (Engelse handleiding), `docs/img/` (schermafbeeldingen voor allebei). `docs/README.md` wijst de weg. De app, de documentatiewebsite en de tests lezen de nieuwe plekken.
- **README**: één bestand, eerst Engels en dan Nederlands, met een pakkende opening, wat je ermee kunt, beginnen in 3 stappen, veiligheid en een oproep voor testers.

### Fixed
- **Songlijst met grote letters**: kolommen werden afgekapt ("8 Bea…") en de laatste kolom liep over de rand van het papier. Nu worden de letters eerst kleiner (ook met grote letters, tot 8 punt) en draait het papier zelf een kwartslag als de lijst te breed is; pas daarna wordt iets ingekort. Past een tabel toch niet (een ander lettertype dan gemeten), dan wordt hij als geheel kleiner, zoals een spreadsheet afdrukt, in plaats van over de rand te lopen.
- **Kopiëren naar… / Verplaatsen naar…**: volle mappen vielen stil weg uit de lijst, zodat het leek alsof mappen ontbraken. Nu staan ze er grijs in met "vol", met uitleg onder de lijst, en "+ Nieuwe map…" toont welke lege map het wordt.
- **Songlijst als PDF**: werd de lijst te breed, dan koos de app de grootste letters en kapte bijna elke kolom af ("8 Beat…", "A: Rau…"). Nu worden eerst de letters kleiner (tot 8 punt); pas als het dan nog niet past, wordt alleen de breedste kolom zo weinig mogelijk ingekort.
- **Privacycontrole**: eigen woorden (`.privacy-words`) worden nu ook gezocht in de controle zelf en in haar test, die voor de patronen worden overgeslagen. Daar bleef een eigen schijfnaam onopgemerkt. Een eigen woord telt alleen als heel woord ("Data" niet in "Database").
- **Lettergrootte** zie je meteen: het venster wordt opnieuw opgebouwd, zonder vraag en zonder herstart. De open kaart, de bibliotheek en wijzigingen die nog niet op de kaart staan blijven staan.
- Het menu **Taal** heeft een vinkje bij de taal die aan staat, net als Lettergrootte.
- Na het wisselen van map (op de kaart en in de bibliotheek) bleven de rijen die je in de vorige map koos gekozen, ook lege. Nu begint elke map zonder keuze.
- **Alle mappen leegmaken** duurde lang (zandloper): het scherm werd na elke song opnieuw opgebouwd. Nu is het één stap, ook bij Ongedaan maken.
- **Meer mappen tegelijk weghalen**: kies op de kaart een of meer mappen en druk op Delete (of rechtermuisknop › Map(pen) weghalen…). Eén vraag, daarna zijn de mappen leeg; ongedaan te maken.
- **Shift-klik in de mappenlijst van de bibliotheek** koos vanaf "Alle songs" in plaats van vanaf de map die je eerst aanklikte, en Cmd-klik haalde de andere mappen weg. De lijst werd na elke klik opnieuw opgebouwd; nu niet meer.
- **Cmd+A** koos altijd de songs van de kaart, ook als je in de bibliotheek werkte. Nu kiest hij alles in de lijst waar je in werkt.
- Over: bij Back-ups staat nu ook **Toon in Finder** als er nog geen back-up is (de map wordt dan eerst gemaakt).
- **Naar het begin** is grijs als je al op het startscherm bent.
- Het stappenvenster sluiten (Esc of het rondje) gaf een fout in het terminalvenster: de eigen methode `done` botste met die van Qt. Heet nu `finish`.
- "Geen kaart gevonden" noemde ook andere schijven (zoals een externe schijf) als "wat er nu wel in zit". Nu alleen een lege SD-kaart. Door die extra regel stond het stappenvenster ook ten onrechte op "Naam" in plaats van op stap 1; opgelost.
- Een kaart in de bibliotheek hernoemen sprong terug naar "Alle kaarten", en tempo en maat bleven op "…" staan na hernoemen, weghalen of bewaren.
- In het Engels opende de handleiding (?) in het Nederlands. Er is nu een Engelse handleiding (docs/manual.md) met dezelfde hoofdstukken; de app kiest de taal die je hebt ingesteld.
- **Lettergrootte op de Mac**: lijsten, tabellen, knoppen en labels kregen weer de kleine letters van de Mac, omdat macOS die na het starten (en bij licht/donker) terugzet en dat alleen aan de vensters laat weten. De app let nu op alle vensters en zet de gekozen grootte meteen terug.
- Een song verplaatsen en daarna kopiëren (voor Op kaart zetten) gaf een fout: de app las de grootte van het bestand op de plek waar het niet meer zou staan.
- KN6000-bestanden met twee delen (LSW van de diskettes) gingen niet helemaal uit te pakken: het tweede deel begint direct na het eerste, niet op de plek die de kop noemt. Nu wel, gecontroleerd met het controlegetal.
- Bij "2 versies" in de bibliotheek zegt de tooltip nu ook waar de andere versie met dezelfde naam staat.
- Een kaart uit de bibliotheek weghalen of hernoemen terwijl de nieuwe kaart er nog songs uit gebruikt gaf fouten bij Op kaart zetten. Dat kan nu niet meer: de app zegt dat je eerst de nieuwe kaart op een SD-kaart moet zetten of die songs moet weghalen.

### Changed
- **Mac en Windows gescheiden**: elke tekst in de app noemt alleen de toetsen en namen van de computer waarop hij draait (Option of Alt, Finder of Verkenner). Een tekst die op Windows anders is, heeft een eigen Windows-versie (sleutel met `_win`); `i18n.tr` kiest zelf. De handleiding achter de **?**-knop laat alleen de toetsen van jouw computer zien, met een eigen tabel sneltoetsen voor Mac en voor Windows.
- **Handleiding herschreven voor beginners**: korte zinnen, stap voor stap, een lijstje met woorden die vaak terugkomen (SD-kaart, map, bibliotheek, back-up), en een tabel met sneltoetsen. Verouderde stukken bijgewerkt (taal staat in de menubalk, diskettes werken al, Tweede kaart ernaast staat onder Bestand). Nieuwe schermafbeeldingen.
- **Bibliotheek en SD-kaart duidelijk gescheiden**: de bibliotheek staat in een eigen gekleurd vlak met de kop "Bibliotheek" (bewaard op deze computer; hier verandert niets), de kaart ernaast staat in een eigen blauw vlak met de kop "Je SD-kaart" (wat hier staat komt op de kaart met Op kaart zetten).
- **Knoppen van de bibliotheek**: "Kaart hernoemen…" en "Kaart weghalen…" staan er alleen als er één kaart gekozen is. "Naar kaart" heet nu "Hele map 02 WALSEN toevoegen aan je kaart" en staat onder "Zet in map …", bij het andere dat naar de kaart gaat; hij is er alleen als er een map of songlijst gekozen is.
- **Geen SD-kaart bij de hand?** Bij Op kaart zetten kan de nieuwe kaart nu ook "In de bibliotheek bewaren…" met een naam. Later zet je hem op een SD-kaart met Nieuwe kaart samenstellen › Beginnen met die naam.
- **Sneltoetsen** (Cmd op de Mac, Ctrl elders): Zoeken (Cmd+F), Alle songs in de map kiezen (Cmd+A), Nieuwe map (Shift+Cmd+N), Weghalen ook met Cmd+Backspace, Bibliotheek aan/uit (Shift+Cmd+L), Informatie over de song (Cmd+I), Naar het begin (Cmd+[), letters Groter/Kleiner (Cmd+plus / Cmd+min). Verplaatsen is Shift+Cmd+M geworden, want Cmd+M is op de Mac "minimaliseren".
- **Mapkeuzevenster**: de knop zegt wat er gebeurt ("Kopie hier maken", "Deze map als bibliotheek", "Deze kaart kiezen") in plaats van "Open"; de Mac laat de titel van dat venster niet zien.
- Weergave › Bibliotheek is grijs bij Nieuwe kaart samenstellen (de bibliotheek staat daar altijd open) en staat dan niet in Meer….
- **Foutmeldingen in gewone taal**: elke melding zegt wat er gebeurde en wat je kunt doen; technische details staan onderaan achter "Voor als je hulp vraagt". Het woord "database" is voor de speler "de inhoudsopgave van de kaart" geworden (ook Extra › Inhoudsopgave herstellen). Een lege map ("hier staat geen KN7000-kaart") en een beschadigde kaart krijgen nu elk een eigen melding.
- **Eén manier per ding**: Extra › "Kaart controleren" en "Inhoudsopgave herstellen" staan niet meer los in het menu; "Kaart doet raar?" (nu Ctrl/Cmd+K) controleert en biedt het herstellen aan. "Nieuwe kaart maken…" heet nu "Lege SD-kaart klaarmaken…", zodat het niet meer lijkt op "Nieuwe kaart samenstellen". De gele balk van een nieuwe kaart zegt alleen nog "Nieuwe kaart: nog leeg"; de uitleg staat op één plek.
- **Kaart doet raar?** zegt de gevonden problemen nu in gewone woorden ("Map 1, song 1: het bestand … ontbreekt, dus deze song speelt niet") in plaats van Engelse technische regels. De statusregel na openen zegt "Kaart geopend" in plaats van het bestandspad, en zegt het als de reservekopie gebruikt is.
- **Geen halve woorden op knoppen**: past "Verplaatsen naar…" enz. niet naast elkaar, dan komen de knoppen twee aan twee onder elkaar, met hele woorden; alleen als dat ook niet past blijft alleen het pictogram over (de tekst staat dan in de tooltip). Ook voor de knoppen van de bibliotheek ("Naar kaart" heeft nu een pictogram). De teller bovenin ("0 songs in 0 mappen") wordt niet meer afgeknipt.
- Na Op kaart zetten zegt de melding nu ook waar je de back-up terugzet (Meer… › Back-ups).
- **Kopie van de bibliotheek op een USB-stick of externe schijf** (Meer… › Hulp, en Bestand): de hele bibliotheek, met controle. Elk gekopieerd bestand wordt teruggelezen en vergeleken; een tweede keer naar dezelfde plek kopieert alleen wat nieuw of veranderd is. Bestanden die alleen nog op de kopie staan worden nooit weggehaald; de app zegt hoeveel het er zijn.
- **Lettergrootte** (Weergave › Lettergrootte: Normaal, Groot, Heel groot): letters, rijen, knoppen en pictogrammen groeien mee. Te zien na opnieuw openen; de app biedt aan dat meteen te doen. "Ongedaan maken" blijft altijd in woorden staan; "Opnieuw" wijkt als eerste.
- **Lettergrootte overal**: één manier voor alle maten. De letters van elk soort onderdeel (ook lijstkoppen, menu's, tooltips en meldingen, die op de Mac eigen kleine letters kunnen krijgen) volgen de gekozen grootte, ook na het wisselen tussen licht en donker; alle maten in stijlbladen gaan door `style.sheet()`, vaste maten in de code door `style.px()`, pictogrammen, vinkjes en rondjes groeien mee. Een test controleert dat er geen vaste maten meer in de code staan.
- **Bewerken-menu**: Verplaatsen, Kopiëren, Andere naam en Weghalen zijn grijs zolang er geen song gekozen is (ze waren klikbaar maar deden niets), en heten nu net als de knoppen onder de lijst.
- **Na verplaatsen of kopiëren** naar een andere (of nieuwe) map zijn de songs gekozen op de plek waar ze terechtkwamen; eerst bleven de oude regelnummers gekozen in de nieuwe map.
- **Lege SD-kaart klaarmaken** is weg uit het menu: Nieuwe kaart samenstellen doet hetzelfde (en kiest de SD-kaart bij Op kaart zetten).
- **Eén plek voor wat er in een song zit**: het venster Extra › Inhoud van de song… (Ctrl/Cmd+I) is weg. Het paneel rechts liet al hetzelfde zien en meer (per registratieknop ritme, tempo, akkoorden en klanken; elke pad in een raster met de naam als tooltip), dus er gaat niets verloren. Het paneel wordt nu ook nooit smaller dan wat erin staat: de instellingen van een knop ("Mod.Blue…", "klank ban…") en de pad-rijen werden rechts afgeknipt.
- **Oefenen is nu hetzelfde als in het echt**: "Eerst oefenen? Probeer alles uit met verzonnen songs" opent een oefenomgeving met een eigen kaartlezer, bibliotheek en back-ups (in de map van de app), uitgelegd in een eigen venster met een kop en een paar punten. De drie taken gebruiken dezelfde code en schermen als in het echt (kaart zoeken, Welke kaart, Op kaart zetten met back-up, bewaren in de bibliotheek met controles, Nog een kaart, de kaart eruit halen). Een kaart gaat erin met "Kaart wisselen…" (een oefenkaart met songs, een nieuwe lege SD-kaart, of geen); een lege kaart die eruit gaat blijft niet in die lijst staan. Zit er geen kaart in, dan zegt de vraag dat je er een in doet met Kaart wisselen. "Stoppen met oefenen" zet de echte kaartlezer, bibliotheek en back-ups terug; niets van het oefenen wordt onthouden. Alleen een map met OEFENEN.TXT erin wordt ooit vervangen. Zit er wel een kaart in maar niet de goede (bijvoorbeeld een lege), dan zegt de vraag wat er nu in zit.
- **Opmaak nagelopen**: tussen pictogram en woord op een knop zit nu wat ruimte ("→ Verplaatsen" in plaats van "→Verplaatsen"). "Bank hernoemen…" in het zijpaneel werd afgeknipt; de knop heet daar nu "Andere naam…", net als bij een song. Inhoud van de song: lange regels lopen door op de volgende regel in plaats van te eindigen op "…", en "1 noten" / "- · tempo" zijn nu "1 noot" en zonder streepje. Geschiedenis begint met "Begin: zoals de kaart was" in plaats van een streepje. Bij de oefenkaart staat bovenin niet de vrije ruimte van de computer (die zegt niets over een kaart).
- **Tweede kaart ernaast** staat niet meer in Meer… (met één kaartlezer kan het niet); in het menu Bestand staat het nog.
- Klaar-scherm opnieuw opgemaakt: wat er gebeurde groot, daaronder kleiner wat er daarna gebeurt, de controles in een kader, en "Nog een kaart met dezelfde songs" links, los van Klaar.
- **Nog een kaart met dezelfde songs**: is een nieuwe kaart na Op kaart zetten ook in de bibliotheek bewaard, dan staat er naast Klaar een knop "Nog een kaart met dezelfde songs". Die begint meteen een nieuwe kaart met de songs van die kaart; je hoeft alleen de volgende SD-kaart erin te doen.
- **Na het uitwerpen terug naar het begin**: na Op kaart zetten wordt de kaart uitgeworpen; de app laat die kaart daarna niet meer zien (een klik zou dan een fout geven) maar gaat terug naar het begin, en zegt dat in de Klaar-melding.
- **"Begrepen" bij een tip is niet meer felblauw**: blauw is voor de ene stap die je moet doen (Op kaart zetten), niet voor het wegklikken van een tip.
- **Bibliotheek gekozen in plaats van een kaart**: de app herkent dat en vraagt of je die bibliotheek wilt gebruiken, in plaats van een foutmelding.
- **Beschadigde songs in de bibliotheek**: een song waarvan een bestand niet uit te pakken is (of waarvan het controlegetal niet klopt) staat in oranje met ⚠ achter de naam; de tooltip zegt welk bestand. Naar een kaart slepen vraagt eerst of je het zeker weet. Live gelezen, niets opgeslagen.
- **Meerdere songs in een map verplaatsen**: selecteer een paar songs en sleep ze naar een andere plaats in dezelfde map. Ze komen daar als blok te staan, in hun eigen volgorde; de songs ertussen schuiven op. Naar boven begint het blok op de plek waar je loslaat, naar beneden eindigt het daar. Favorieten en songlijsten gaan mee, en het is één stap voor Ongedaan maken.
- **Controle bij bewaren in de bibliotheek** (`core/verify.py`): elk bestand van een kaart of diskette wordt twee keer gelezen (de tweede keer langs de cache van de computer), songbestanden worden uitgepakt (KN6000: controlegetal), en wat in de bibliotheek komt wordt teruggelezen. Na afloop staat elke controle in beeld met ✓; een probleem krijgt een eigen melding met de bestandsnamen. Leest een bestand drie keer anders, dan stopt het bewaren en blijft er geen halve kopie achter. Ook bij een back-up terugzetten in de bibliotheek.
- **Kaart niet uitgeworpen**: lukt het uitwerpen na "Op kaart zetten" niet, dan zegt de app nu dat je de kaart eerst zelf moet uitwerpen (Finder ⏏ of Verkenner › Uitwerpen) voordat je hem eruit haalt.
- **Windows**: nagelopen op alles wat op de Mac anders gaat.
  - Een kaart of diskette heet naar zijn naam en niet naar de letter, dus "KN7000 (E:)" in plaats van "E:".
  - Back-ups komen in de map met die naam.
  - De diskettedrive `A:` wordt gevonden, zonder de melding "geen schijf in station".
  - Op kaart zetten werpt de kaart uit en geeft hem de gekozen naam.
  - Na het kopiëren worden bestanden echt weggeschreven; onder Windows kan dat alleen met schrijfrechten.
  - Mapnamen als `CON` of `AUX`, die Windows zelf gebruikt, krijgen een `_`.
  - "Toon in Verkenner" in plaats van "Toon in Finder", en het eigen icoon staat in de taakbalk.
  - Niet getest op een echte Windows-pc.
- **Naamkolom blijft leesbaar**: werd de kolom Naam smal omdat het venster of paneel even smal was, dan groeit
  hij nu weer terug zodra er ruimte is (minstens een hele naam van 16 letters). Een smalle breedte van de vorige
  keer wordt niet meer onthouden.
- **Laadbalk rustiger**: in de statusbalk alleen tekst, een dun balkje en een percentage, zonder blauw blok.
- **Alle te ingewikkelde functies opgedeeld** (rest van de code-analyse): songpaneel, songinhoud, songfeiten,
  bibliotheeklijst, kaart bewaren, songlijst afdrukken, scherm verversen, op kaart zetten, paneelinstellingen,
  de opdrachtregel en het infopaneel. Geen functie scoort nog boven 20 (radon). Paneelinstellingen zijn
  nagelopen: oude en nieuwe code geven hetzelfde op alle echte knoppen en op 20.000 willekeurige.
- **Meer schermtests**: taakknoppen op het startscherm, de laadbalk onderin, openklappen in "Lijst" en het
  songpaneel met echte bestanden. Getest is nu 85% (songdeel van de presenter: van 62% naar 90%).
- **Opgeruimde code** (na de code-analyse): het hoofdvenster is verdeeld over `qt_app.py`, `widgets.py`,
  `dialogs.py` en `info_panel.py`, en de presenter over `presenter.py` en `presenter_song.py`. Het kopiëren van
  een songlijst en het samenvoegen van dubbele songs zijn in kleinere stukken opgedeeld. Het gedrag blijft gelijk.
  Een nieuwe test controleert dat elke tekst een NL- en een EN-versie heeft met dezelfde invulvelden.
- **Lijst sneller bij openklappen**: elke knop in "Lijst" is een eigen stuk, dus bij openklappen wordt alleen
  die knop opnieuw opgebouwd. Alles dichtgeklapt opbouwen: 0,1 s.
- **Bestanden echt op de kaart**: na elk kopiëren, verplaatsen en wissen wacht de app tot het echt op de kaart
  staat (niet alleen in het geheugen van de computer), en de controle na het opslaan leest van de kaart zelf.
- **Laadbalk onderin**: de voortgang (bijv. "Bibliotheek lezen…") staat nu in de statusbalk onderin, zodat het
  scherm niet meer verspringt.
- **Sneller door songs bladeren**: het uitpakken van songbestanden is ongeveer 4 keer sneller en de laatste
  64 uitgepakte bestanden worden onthouden. Op de echte kaart: van ±50 ms naar 8 ms per song, en 4 ms als
  je terug gaat.

### Added
- **Andere naam…** voor een kaart of diskette in de bibliotheek: de map krijgt in de app een nieuwe naam, zonder Finder. De kaartlijst staat nu op een eigen regel, de knoppen eronder.
- **Uit bibliotheek weghalen…**: een kaart of diskette uit de bibliotheek halen (bij Nieuwe kaart samenstellen, kaart kiezen). De knop staat er altijd (grijs bij "Alle kaarten"), zodat de kaartlijst even breed blijft. Na een vraag gaat de map naar de Prullenbak, nooit definitief weg; de kaart zelf en back-ups blijven staan.
- **Niet afgemaakt opslaan wordt opgemerkt**: tijdens "Op kaart zetten" staat er een klein briefje
  (`KNSONGBK.JOB`) in de hoofdmap van de kaart, dat na afloop weer weg gaat. Gaat het halverwege mis (kaart te vroeg
  eruit), dan ziet de app dat bij het volgende openen en biedt aan: terugzetten zoals het was (uit de back-up van
  dat moment), de database herstellen uit de bestanden, of later.
- **Ontbrekende bestanden bij openen**: noemt de database bestanden die niet op de kaart staan, dan meldt de app
  dat bij het openen en biedt "Database herstellen" aan.
- **Hele kaart nagekeken na opslaan**: na het terugkijken van de aangeraakte bestanden kijkt de app of alle
  bestanden van alle songs op de kaart staan, en zegt dat in de melding.
- **Melding bij losse bestanden**: staan er in de mappen bestanden die bij geen enkele song horen, dan meldt de
  app dat bij het openen, met "Opruimen" of "Laten staan". Er wordt nooit vanzelf iets weggehaald; opruimen is
  een gewone stap die je ongedaan kunt maken en die pas bij "Op kaart zetten" gebeurt, na de reservekopie.
- **Lijst klapt open**: in "Lijst" klapt een klik op een knop zijn instellingen eronder open (nog een klik
  klapt ze dicht), in plaats van naar "Knoppen" te springen. Een pijltje ▸/▾ laat zien dat het kan.
- **Eigen app-icoon**: een SD-kaart met muziek boven een klavier, in het blauw van de app. Getekend als
  SVG in de code (geen los plaatje); `tools/make_app_icon.py` schrijft PNG's voor latere Mac-verpakking.
- **Controle na elk opslaan**: vóór het opslaan rekent de app per aangeraakt bestand uit wat er na afloop moet
  staan (vingerafdruk van de inhoud), en na het opslaan leest hij elk van die bestanden terug en vergelijkt.
  Verplaatsen, wisselen, kopiëren, uit de bibliotheek halen en wissen worden zo byte voor byte gecontroleerd.
  Klopt iets niet, dan zegt de app welk bestand en dat de back-up de oude kaart nog heeft.
- **Eenvoudig of uitgebreid**: onder *Weergave* zet je het infopaneel aan of uit (*Informatie over de song*) en
  kies je *Uitgebreide informatie*. Eenvoudig (standaard) toont per knop ritme, tempo, akkoorden, klanken,
  begeleiding en klavier; uitgebreid toont alles wat gelezen wordt, ook de oranje waarden en de bestanden.
  Beide keuzes worden onthouden.
- **Downloads bewaren**: een uitgepakte zip met sets (zoals van stijl-websites) kies je bij *Kaart of diskette
  bewaren* met *Zelf een map kiezen…*; die gaat als diskette naar de bibliotheek. Bij een gewone map wordt
  niets uitgeworpen (eerder kon de app proberen de schijf uit te werpen waar die map op staat) en wordt niet om
  een volgende diskette gevraagd.
- **Alles per registratieknop**: onder de klanken staan nu ook variatie, TECHNI-CHORD, left hold, splitpunt,
  transpose, octaaf, de volumes van begeleiding en pads, per klank galm, chorus, multi, DSP, pan, toon en
  stemming (en drawbars bij een orgelklank), de akkoord- en baspedaalpartij, effecten, equalizer, pedalen, MIDI
  en de 16 sequencer-partijen. Waarvan de betekenis van het getal nog niet zeker is, staat in oranje.

### Fixed
- KN6000-bestanden met twee delen (LSW van de diskettes) gingen niet helemaal uit te pakken: het tweede deel begint direct na het eerste, niet op de plek die de kop noemt. Nu wel, gecontroleerd met het controlegetal.
- Infopaneel en songlijst (CSV/PDF) halen ritme, maat, tempo, model, ingespeeld, akkoorden, Reg Banks en
  songs-erin nu uit één en dezelfde functie, zodat ze altijd hetzelfde zeggen.
- De songlijst liep rechts buiten beeld (schuifbalk, afgesneden invoervakjes) als de Naam-kolom van vroeger
  breder was dan het paneel. De Naam-kolom past zich nu aan de breedte aan.
- Registraties: Knoppen en Lijst worden door dezelfde code gemaakt, zodat ze niet meer uit elkaar lopen. De lijst
  toont per knop ritme, tempo, akkoorden en klanken met volume; klik op een knop voor al zijn instellingen.
- De breedte van de panelen wordt onthouden (apart voor ordenen en nieuwe kaart).
- Mappen en songs zijn standaard zo breed als de langste naam (16 tekens); de extra ruimte gaat naar het
  infopaneel.
- Pads: de tabel versprong bij het openklappen. Het zijn nu vaste blokjes; een lange banknaam loopt door op de
  volgende regel.
- Songlijst als PDF: Map en Mapnaam staan als kop boven elke map, en volgen nu de vinkjes (uitgevinkt = niet in
  de kop). Het venster zegt dat erbij. Ook stond er "((geen naam))" met dubbele haakjes.
- De bankknoppen (A, B, C, 1–10) lagen op de Mac over elkaar als er twee rijen waren. Ze hebben nu een vaste hoogte.
- Het slepen van de scheidingslijn tussen de panelen haperde. Nu beweegt alleen een lijn mee, en de panelen
  worden één keer opnieuw ingedeeld bij het loslaten.
- Een KN5000-song (ouder model, bijv. uit stijl-downloads) gaf een technische foutmelding. Nu staat er
  *KN5000-bestand: de app kan het niet lezen, en het werkt misschien niet op een KN7000*, en bij Gemaakt op
  *KN5000*.
- Bij een set met 13 banks werden *Knoppen* en *Lijst* platgedrukt: de weergavekeuze staat nu op een eigen
  regel en de bankletters lopen door op een tweede regel.
- Een registratieknop zonder naam heette *leeg*, maar heeft wel instellingen (ritme, tempo, akkoorden,
  klanken); op de kaart van de vriend geldt dat voor alle 4.539 knoppen zonder naam. Die knoppen heten nu
  *zonder naam* en tonen hun gegevens, zodat de telling bij Akkoorden klopt met wat je ziet.

### Added
- **Bestanden met uitleg**: in het infopaneel staat bij elk songbestand wat erin zit, bijv. *PMT 10 KB ·
  registraties: de Reg Banks met hun 8 knoppen*. Het kopje *Eigen klanken* legt in de tooltip uit wat dat is.
- **Songlijst: alle Reg Banks**: de kolom *Reg Bank A* heet nu *Reg Banks* en toont elke gebruikte bank met
  naam, bijv. *A: West zuidwest · B: JAZZ · C: 60 & 70 Beats* (ook 1–10 bij een diskette-set).
- **Alle details in het infopaneel**: onder de korte gegevens staat nu alles wat in de song zit, onder kopjes
  die je dichtklikt (Registraties, Opname, Composer-stijlen, Pads, Eigen klanken, Homepage-afbeelding,
  Bestanden). Bij Registraties kies je **Knoppen** (bank kiezen, 8 knoppen zoals op het paneel, klik een knop
  voor ritme, tempo, akkoorden en klanken met volume) of **Lijst** (alle banks onder elkaar om te vergelijken).
  Pads als blokjes per bank, eigen pads groen. Weergave, bank en dichte kopjes blijven bij de volgende song. De knop *Wat zit erin?* is weg; Extra → Inhoud van de song… (Cmd+I) opent het nog in
  een groot venster.
- **Alle meldingen in beide talen**: foutmeldingen uit de kern (volle map, schrijfbeveiligd, geen ruimte, lege
  plaats ...) en de stappen bij Ongedaan maken/Opnieuw staan nu in het Nederlands of Engels, wat je gekozen
  hebt (was: altijd Engels). Fouten van het systeem (schijf vol, kaart eruit) ook. Een test controleert dat
  elke melding beide talen heeft.
- Bij een schrijfbeveiligde kaart blijft bovenin een balk staan met uitleg en *Opnieuw kijken*
  (was: een melding die snel verdween).
- **Klanken per knop** in *Wat zit erin?*: achter elke registratie staat welke klank op rechterhand 1 en 2 en
  linkerhand zit, bijv. *R1 Flute, R2 String Ensemble 1, L Warm Pad*. De naam is de soort klank (General
  MIDI-indeling, bank 32) of *Drawbars*; andere banks tonen hun nummers. De precieze Technics-namen volgen
  als we de klankenlijst van de KN7000 hebben.

### Changed
- **Schrijfbeveiligde kaart**: de kaartkeuze toont *· schrijfbeveiligd*. Bij *Kaart ordenen* zegt de app meteen
  dat je wel kunt kijken maar niets kunt opslaan, en hoe je het schuifje omzet. *Op kaart zetten* op een
  vergrendelde kaart vraagt om het schuifje om te zetten met *Opnieuw proberen* (was: een Engelse foutmelding).
  Diskettes worden alleen gelezen, dus daar maakt het lipje niet uit.
- **Akkoorden** in het infopaneel en de export: als de knoppen van een song verschillende akkoordmodi hebben,
  staat er nu *gemengd: 4 knoppen één vinger (one finger), 20 knoppen zelf spelen (fingered)* (was: alleen
  de meeste).
- Songs naar een andere map **slepen kopieert nu**; met Option/Alt ingedrukt wordt het verplaatsen.
  De mappen zijn setlijsten, dus dezelfde song in meer mappen is normaal.
### Added
- **Nieuwe kaart een naam geven**: klik bij het samenstellen op *Nieuwe kaart ✎* bovenin en typ een naam.
  Bij *Op kaart zetten* krijgt de SD-kaart die naam (op de Mac, met diskutil; hoogstens 11 tekens, in
  hoofdletters) en wordt hij voorgesteld als naam in de bibliotheek.
- **Songlijst afdrukken (PDF)** en **Songlijst voor Excel (CSV)** vragen eerst wat erin moet: kolommen
  (map, mapnaam, nummer, naam, ritme, maatsoort, tempo, opgenomen, model, akkoorden, Reg Bank A, songs erin,
  bestanden), alle mappen of alleen de open map, en bij PDF elke map op een nieuwe bladzijde. De keuze wordt
  onthouden.
- Infopaneel: **Opgeslagen met** *3 BANK (alleen Reg Bank A, B en C)* of *ALL*, en per bank een regel, bijv.
  **Reg Bank A** *Zeeman, 8 van de 8 knoppen* en **Reg Bank B** *leeg*; een volledige set (ALL) toont zo
  ook Reg Bank 1 t/m 10, in dezelfde opmaak. *Wat zit erin?* noemt de banks nu zoals het keyboard:
  Reg Bank A, B, C en 1–10 (was: bank 1, 2, 3 …).
- **Songs in een diskette-set**: een set van een diskette heeft registraties voor veel songs (Top Trax: 20).
  De bibliotheek toont *TRAX1 · set met 20 songs* met de namen onder de muis, zoeken op een songnaam vindt de
  set (*TRAX1 · met Annie's Song*) en het infopaneel heeft de regel *Songs erin*. *Wat zit erin?* toont nu alle
  banks van zo'n set (was: alleen sets van 3 banks).
- Infopaneel: **Akkoorden** *zelf spelen (fingered)*, *één vinger (one finger)* of *pianist*, uit de
  registraties van de song. Zo zie je het verschil tussen TRAX1 (fingered) en 1FINGR (one finger).
- **Help**-menu met *Handleiding…* en *Over KN Songboek* (op de Mac in het KN Songboek-menu): versie, wat het programma
  doet en waar bibliotheek en back-ups staan (met Toon in Finder).
- **Diskettes in de bibliotheek**: knop 3 heet nu *Kaart of diskette bewaren in de bibliotheek* en herkent zelf
  of er een SD-kaart of een muziekdiskette (KN6000/KN7000) in zit. Na elke diskette: *Nog een diskette?*, om een
  stapel af te werken. Elke diskette komt onder *Diskettes* als kaart met elke set als song (core/floppy.py);
  de originele bestanden blijven ongewijzigd bewaard in de map DISKETTE. Alle diskettes heten op de computer
  hetzelfde: een diskette die er al in staat wordt aan zijn bestanden herkend (overslaan of opnieuw inlezen),
  het naamvoorstel is altijd vrij en een andere diskette wordt nooit overschreven.

### Changed
- Het venster werd met de grote letters ongeveer 1600 punten breed, breder dan een laptopscherm. Daardoor zat
  alles op de kleinste maat en konden de panelen niet meer verschoven worden. Knoppen met een lange tekst
  (Verplaatsen naar…, Kopiëren naar… enz.) worden nu ingekort met "…" als er geen ruimte is, met de hele
  tekst als tip. Het venster past nu op een laptopscherm.
- Kolommen van de songlijst en de bibliotheek zijn allemaal breder of smaller te maken door de rand in de kop te
  slepen (dubbelklik op de rand past de kolom aan de tekst aan). De laatste kolom vult de rest. De breedtes
  blijven staan, ook na zoeken of filteren, en worden onthouden voor de volgende keer.
- Diskettes na elkaar inlezen is duidelijker: na elke diskette wordt hij uitgeworpen en staat er één scherm
  *✓ Diskette 2 staat in de bibliotheek … doe de volgende erin, het programma gaat vanzelf verder*, met de knop
  **Klaar** (was: *Doorgaan*/*Annuleren* en daarna *Kaarten zoeken…*). Tijdens het zoeken staat er
  *Diskette zoeken…*, de eerste stap heet *Kaart of diskette*, en een diskette die niet uitgeworpen werd telt
  pas weer mee als hij eruit is geweest.
- Panelen breder of smaller maken is beter te vinden: tussen de panelen staat een greepje (drie puntjes) dat
  blauw wordt onder de muis, met uitleg; dubbelklik zet de breedtes terug. Ook de rand van Favorieten en
  songlijsten licht op.
- Bij een nieuwe kaart (nog niet op een kaart gezet) staan Kaart doet raar?, Controleren en Herstellen uit:
  de songs staan dan nog in de bibliotheek, dus de controle meldde ten onrechte ontbrekende bestanden, en
  Herstellen had de nieuwe kaart leeg gemaakt.
- Infopaneel: **Gemaakt op** KN7000 of KN6000 (uit het SQT-bestand van de song).
- **Back-ups…** (was Back-up terugzetten): back-ups van alle kaarten, die van de open kaart bovenaan; rechts
  wat er toen op stond. Terugzetten op deze kaart (met extra vraag als de back-up niet op de kaart lijkt), als
  nieuwe kaart beginnen (dan Op kaart zetten, ook op een andere of lege kaart), in de bibliotheek zetten (ook
  oude bibliotheekversies), Nu een back-up maken en Toon in Finder.
- Opruimen van back-ups (laatste 10) telt alleen back-ups van dezelfde kaart: twee kaarten die allebei
  NO NAME heten, raken elkaars back-ups niet meer kwijt.
- De mappenlijst kan niet smaller worden dan de langste mapnaam, en geen paneel kan meer helemaal
  weggeschoven worden.
- Nieuwe kaart vanuit een bewaarde kaart: Op kaart zetten werkt meteen, zonder eerst iets te wijzigen.
- Inhoud van een song en het infopaneel werken ook voor songs die nog niet op de kaart staan (nieuwe kaart,
  of verplaatst maar nog niet opgeslagen).
- Het infopaneel (ritme, maat, tempo) blijft staan als Favorieten en songlijsten open is, en staat er ook bij
  een nieuwe kaart.
- Favorieten: de knop zegt wat er gebeurt ("Zet DANSEN op knop 3"); de tabbladen hebben geen rand meer
  waar knoppen overheen staken.
- Namen (song, map, favorietenbank): het invoerveld stopt bij 16 tekens en neemt alleen tekens aan die het
  keyboard kan tonen. De melding blijft als vangnet, nu in het Nederlands.
- Kaartimages zijn uit de app gehaald (Bestand → Kaartimage openen); de opdrachtregel kan er nog wel mee werken.
- **Nieuwe kaart samenstellen** kan beginnen met een bewaarde kaart (alle mappen, namen, songlijsten en
  favorieten in één keer), en na **Op kaart zetten** van een nieuwe kaart vraagt het programma of die ook in
  de bibliotheek moet: een reeks kaarten maken met één kaartlezer.
- Menubalk en **Meer…** opgeruimd: de menubalk heeft alles (Bestand, Bewerken, nieuw **Weergave** voor de
  panelen met vinkje, Extra, Taal); Meer… alleen wat een speler af en toe nodig heeft, met dezelfde namen als in
  het menu. Kaart openen, bibliotheek kiezen en taal staan alleen nog in de menubalk.
- Tabbladen (Favorieten / Songlijsten): het actieve tabblad is vet met een blauwe streep eronder.
- Bibliotheek: kies je één kaart, dan staan de mappen en songlijsten van die kaart als lijst links (zoals op het
  keyboard) in plaats van een tweede keuzevak, en de songs van een map met hun nummer 01–20.
- **Opnieuw** naast **Ongedaan maken**, en na ongedaan maken biedt het balkje onderin **Opnieuw** aan.
- Verplaatsen/Kopiëren naar zegt "3 songs, nog 17 plaatsen vrij" in plaats van "3 van 20".
- Iconen naast de woorden waar ze helpen (eigen lijntekeningen in `gui/icons.py`, volgen licht/donker): de drie
  taken op het startscherm, de knoppen onder de songs (pijl, twee blaadjes, potlood, prullenbak, i), Begin,
  Ongedaan maken, Op kaart zetten, Nieuwe map, Zet in map, Filter, een vergrootglas in de zoekvelden, een lampje
  bij de tip en de tegels onder Meer… (de oude tekentjes daar waren per lettertype anders). Nooit een icoon zonder
  woord; geen iconen in de lijsten met mappen en songs.
- Kleuren volgen de licht/donker-instelling van de computer (ook als die tijdens het werken omschakelt): eigen
  kleuren staan op één plek (`gui/style.py`), met een set voor licht en een voor donker en overal genoeg
  contrast; grijze tekst wordt afgeleid van de systeemkleuren. **Begrepen** in de tip is nu een blauwe knop.
- Bij **Nieuwe kaart samenstellen** staan alle 99 mappen open (lege als "02  leeg"); alleen bij ordenen worden
  lege mappen ingeklapt. Geen horizontale schuifbalk meer in de mappenlijst.
- Vervolgschermen makkelijker (UX-voorstel van 2026-11-15): grotere letters, regels en knoppen; lege mappen
  ingeklapt achter één regel ("94 lege mappen", tijdens slepen weer zichtbaar) en **+ Nieuwe map**; lege
  plaatsen als lichte stippelvakjes; bovenin de naam van de kaart met "14 songs in 5 mappen" en een meter voor
  de 99 × 20 plaatsen.
- Alles wat slepen doet kan ook met knoppen: onder de songs **Verplaatsen naar…**, **Kopiëren naar…**, **Andere
  naam**, **Weghalen** en **Wat zit erin?** (een lijst mappen om uit te kiezen in plaats van een nummer typen),
  rechtsklikmenu's, **+ Zet in map** en dubbelklik bij een nieuwe kaart, knoppen bij favorieten en songlijsten.
- Na verplaatsen, kopiëren of weghalen een balkje onderin met **Ongedaan maken**; weghalen vraagt niet meer
  "weet je het zeker?". Voortgang van lang werk staat als balk in het venster.
- **Op kaart zetten** en **Kaart bewaren in de bibliotheek** lopen in één venster met stappen (① Welke kaart ─
  ② Op kaart zetten ─ ③ Klaar), grote knoppen, voortgang erin, gaat vanzelf verder als de kaart erin gaat, en
  eindigt met een groot vinkje.
- Infopaneel rechts van de songs (plaats, ritme, maat, tempo, ingespeeld, favorieten, songlijsten).
- **Meer…** is een pagina met tegels (Spelen, Kaart, Hulp, Instellingen); **Kaart doet raar?** controleert en
  stelt herstellen voor; back-ups heten "Vandaag 14:32"; favorieten tonen "HET IS FEEST · map 01, nr 1".
- Nieuwe kaart: filters achter **Filter**, gelijke namen als "· 2 versies", een lege bibliotheek of lege nieuwe
  kaart zegt wat je moet doen.
- De eerste keer een tip per scherm; de **?**-knop toont het hoofdstuk van de handleiding over dat scherm.
- Eenvoudige werkwijze (ADR-0008): het programma begint met "Wat wil je doen?" en drie grote knoppen:
  *Kaart bekijken en ordenen* (vindt zelf de KN7000-kaart in de computer), *Nieuwe kaart samenstellen*
  (bibliotheek links, nieuwe kaart rechts met hoeveel songs en hoeveel ruimte) en *Kaart bewaren in de
  bibliotheek* (naam = etiket; een kaart die er al in staat wordt herkend en het programma vraagt of de kopie op de computer vervangen moet worden; de SD-kaart zelf
  verandert daarbij nooit).
- Wijzigingen zijn een concept: een gele balk "N wijziging(en) nog niet op de kaart" met één knop **Op kaart
  zetten** (controle, back-up, schrijven, "Klaar", op de Mac uitwerpen). Ctrl/Cmd+S doet hetzelfde.
- Favorieten, songlijsten, dubbele songs, inhoud, tweede kaart, back-ups, controleren en exporteren staan
  onder **Meer…**; de werkbalk en de zijpanelen zijn standaard weg. Geen technische woorden in de meldingen.
- De bibliotheek toont per song op welke kaart en in welke map hij staat ("Kaart 2019 (map 3)").
- De app opent niet meer vanzelf de vorige kaart; hij begint op het startscherm.
- Lang werk loopt in de achtergrond (een eigen thread): bibliotheek openen, kaarten zoeken, kijken of een kaart
  al in de bibliotheek staat, kaart bewaren, op kaart zetten met back-up, back-up terugzetten, herstellen en
  dubbele songs zoeken. Het venster blijft reageren en toont de voortgang; klikken en toetsen wachten tot het
  klaar is, zodat niets de kaart halverwege kan veranderen. De presenter roept dit werk aan via `runner`,
  zodat de kern en de tests zonder Qt blijven werken.

### Added
- `core/cards.py`: kaarten in de computer vinden en herkennen (KN7000, leeg, anders), een kaart in de
  bibliotheek bewaren of bijwerken (herkend aan de songs, zonder index), een nieuw samengestelde kaart op een
  kaart zetten (oude KN7000-gegevens eerst in een back-up), kaart uitwerpen. CLI: `cards`, `library add`.

### Fixed
- KN6000-bestanden met twee delen (LSW van de diskettes) gingen niet helemaal uit te pakken: het tweede deel begint direct na het eerste, niet op de plek die de kop noemt. Nu wel, gecontroleerd met het controlegetal.
- Gele balk in donkere modus: de knop **Op kaart zetten** was licht op geel en bijna onzichtbaar. De balk en
  de knop hebben nu vaste kleuren (blauwe knop; lichtgeel en uitgelegd als er nog geen songs op de nieuwe kaart
  staan). **Meer…** werd afgekapt en is nu een gewone knop met een menu.
- Delete-toets: op de Mac is de "delete"-toets Backspace en die verwijderde geen songs; nu werken Del én
  Backspace in de songtabel. In de favorieten en de songlijst wist de toets weer de knop of regel in plaats van
  door het venster te worden afgevangen.
- Tempo-events in SQT zijn twee 7-bitshelften (`3B 01` = 187), niet één byte.
- Slepen in de grafische versie toonde altijd een "+" (kopiëren). Slepen is nu verplaatsen; met Option/Alt (of Ctrl) ingedrukt kopieer je, en alleen dan toont de cursor een "+".
- Bestandsnaam van een song is `<ss><base>.<EXT>` (bijv. `01009KN7.LSW`), niet `<base><ss>`; gevonden op een echte kaart.
- Alfabetische index: lege plaatsen worden `FF FF` en `first_index` telt ze niet mee; de index van een echte kaart
  wordt nu byte voor byte gelijk nagebouwd.

### Added
- LZSS-encoder die byte voor byte dezelfde bestanden maakt als Technics (`formats/lzss_tree.py`, Okumura's
  zoekboom met N = 8192, F = 10, zelf geschreven). Gecontroleerd op alle ingepakte bestanden van een echte
  kaart. Vervangt de eenvoudigere encoder.
- Documentatie als website (`mkdocs.yml`, MkDocs Material, Nederlands, zoeken werkt ook vanaf schijf);
  ROADMAP en CHANGELOG staan erin via `tools/mkdocs_hooks.py`. Gebroken links laten de build falen.
- `tools/check.py`: ruff, mypy en alle tests in één opdracht (ontbrekende tools worden overgeslagen; `--fast`
  zonder GUI-tests). Ruff- en mypy-instellingen in `pyproject.toml`; de gevonden kleinigheden zijn opgelost.
  GUI-tests worden overgeslagen als PySide6 ontbreekt.
- Handleiding voor de gebruiker zonder technische kennis (`docs/handleiding.md`), met schermafbeeldingen van
  verzonnen democards, opnieuw te maken met `tools/make_screenshots.py`.
- Inhoud van een song tonen: panel memories (banken, namen, tempo), composer-stijlen met variatienamen, pads,
  eigen klanken en de homepage-afbeelding (`formats/songdata.py`, CLI `show [--picture]`, app Extra → Inhoud van
  de song, Ctrl+I). Alle songs van een echte kaart worden zonder fouten gelezen; HMP nog niet op een echt bestand getest.
- SD_SOUND lezen: namen uit SD_SOUND.TKM, volgorde uit SD_SOUND.PLM, MIDI-bestanden (`formats/sdsound.py`, CLI `sdsound`).
- Een hele map slepen in de mappenlijst, zoals in een afspeellijst: op de gele lijn tussen twee mappen komt hij
  ertussen en schuiven de mappen ertussen één plaats op (CLI `insert-folder`); op een lege map verhuist hij
  daarheen. Ruilen van twee mappen alleen via CLI `move-folder`. Favorieten en songlijsten gaan mee; één stap
  ongedaan te maken.
- Maatsoort van een song: `formats/rhythm.py` leest het ritme uit de panel memory (blok `0x42`) en zoekt de
  maat op in een eigen ritmetabel van het keyboard (220 ritmes, `formats/rhythm_table.py`, gegenereerd door
  `tools/gen_rhythm_table.py`) of in de eigen `.CMP` van de song. CLI `show` toont ritme en maat, de bibliotheek
  heeft een kolom "Maat".
- Bibliotheek: een hele map of songlijst van een kaart in één stap naar de open kaart kopiëren
  (`CardSession.import_folder`, `import_song_list`, CLI `library copy-folder/copy-list`, GUI knop "Naar kaart").
  Vinkje heet nu "Alleen ingespeeld".
- Songbibliotheek (ADR-0007): `core/library.py`, CLI `library ls/search/copy` en in de app links als startscherm
  (zoeken, filters, slepen naar de kaart rechts, Nieuwe kaart maken). Alle kaarten in één map, live gelezen,
  identieke songs één keer, tempo en opname uit het SQT-bestand.
- Tempo uit de panel memory van het songrecord (`sqt.panel_tempo`).
- Kaartimages direct openen (`FatImageStorage`, FAT12/16/32, met of zonder partitietabel): alle CLI-opdrachten
  nemen ook een imagebestand, GUI Bestand → Kaartimage openen. Eigen implementatie, getest tegen mkfs.fat/fsck.fat/mtools.
- Dubbele songs opsporen en opruimen: CLI `duplicates` en `dedupe`, GUI Extra → Dubbele songs zoeken,
  `CardSession.merge_duplicates`. Favorieten en songlijsten wijzen daarna naar de gehouden song.
- CLI `show`: bestanden van een song en de opgenomen sequencersong (formats/sqt.py).
- Bij slepen licht de map onder de cursor op en zegt de statusbalk of loslaten verplaatst of kopieert.
- Containers `JK D` (EFC) en KN6000-songs `I KD` / `IK D` (deflate) lezen.
- `tests/test_real_card.py`: test tegen een lokale kaartkopie via `KN_SONGBOEK_REAL_CARD`.
- VS Code-startconfiguraties (`.vscode/`).
- Automatische back-up (zip) vóór elke save, in CLI en GUI; opdrachten `backup`, `backups`, `restore`, `info`.
- Controle vóór het schrijven: schrijfbeveiliging en vrije ruimte.
- `--log BESTAND`: logboek van alle bestandsoperaties.
- `repair`: database opnieuw opbouwen uit de songbestanden; `check` wijst erop.
- GUI volwaardig: mappen en songs naast elkaar, slepen en neerzetten (ook meerdere songs), inline hernoemen,
  zoeken, undo/redo met geschiedenispaneel, voortgang bij opslaan, back-ups terugzetten, herstellen,
  export naar CSV/PDF, Nederlands/Engels, instellingen onthouden.
- Favorieten en songlijsten bewerken (core, GUI-paneel, CLI `set-favorite`, `rename-bank`, `songlist`).
- Tweede kaart naast de eerste in de GUI; songs overslepen. CLI `import` voor één song.
- `CardSession.redo()`; namen worden gecontroleerd (max. 16 tekens, gewone ASCII) in plaats van afgekapt.
### Changed
- Verplaatste, gekopieerde en geïmporteerde songs krijgen een expliciete base (`006KN7`) in de database,
  zoals op een echte kaart, in plaats van een lege.
- ADR-0004: alle formaatcode (ook LZSS-encoder en SQT-parser) wordt zelf geschreven; voorstel MIT.

## [0.2.0] - 2026-11-15
### Added
- Lagenstructuur `formats` / `storage` / `core` / `cli` / `gui` onder `src/` met `pyproject.toml`.
- `CardSession`: bewerkingen in het geheugen, geplande bestandsoperaties, undo, `on_change`, `save(progress)`.
- Nieuwe bewerkingen: `swap`, `merge`, `search`; songlijsten (0xBFE0) lezen en bijwerken.
- `Storage`-protocol met `DirectoryStorage` en `MemoryStorage`.
- CLI met subcommando's, `--json`, `--dry-run`, exitcodes.
- GUI-schets: PySide6-venster met MVP-presenter.
- Documentatie volgens Diátaxis, arc42-architectuur, zes ADR's, roadmap.
### Changed
- Opslaan zoals het keyboard: INF schrijven, teruglezen, BAK als identieke tweede kopie
  (in 0.1 was BAK de vorige versie).
- Favorieten én songlijsten volgen een verplaatste song en worden gewist bij verwijderen.

## [0.1.0] - 2026-11-14
### Added
- Eerste prototype: `KN7000MN.INF` lezen/schrijven, kaartbewerkingen, LZSS en containers, eenvoudige CLI.
