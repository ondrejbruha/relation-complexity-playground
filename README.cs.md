# Relační komplexita konečných grafů

[English README](README.md) · [Algoritmus](docs/algorithm.md) ·
[Přispívání](CONTRIBUTING.md) · [Licence MIT](LICENSE)

Skript počítá strukturální relační komplexitu konečných grafů, průběžně ukládá
každý výsledek a kreslí závislost na počtu vrcholů. Cílem je zkoumat
`f(N) = max {rc(G) : |V(G)| = N}`.

## Spuštění

Použij Python 3.12 nebo 3.13; místní ověření proběhlo na Pythonu 3.13.
Nejprve vytvoř virtuální prostředí:

```sh
python -m venv .venv
```

Na Windows PowerShell ho aktivuj a nainstaluj závislosti:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py --mode atlas --max-n 7 --workers 4 --output results/atlas
```

Na Linuxu/macOS aktivuj prostředí pomocí `source .venv/bin/activate` a používej
stejné příkazy `python`. Přímé závislosti jsou pouze NetworkX a matplotlib.

Režim `atlas` zahrnuje **všechny** neizomorfní jednoduché grafy do 7 vrcholů,
včetně nesouvislých. Režim `catalog` přidává úplné katalogy pro N = 8 a 9
od [Brendana McKaye](https://users.cecs.anu.edu.au/~bdm/data/graphs.html).
Stáhne je jednou do výstupního adresáře, ověří počty záznamů a jejich jedinečnost
a uloží SHA-256 pro kontrolu při dalším spuštění. Úplnost do izomorfismu vychází
z publikovaného katalogu, samotný počet řádků ji nedokazuje.

```powershell
.venv\Scripts\python.exe main.py --mode catalog --max-n 9 --workers 4 --plot-every 25000 --output results/catalog
```

Stejný příkaz naváže na uložená data. Rozsah N lze rozšířit, počet procesů změnit
a u vzorkování přidat další vzorky. Již hotové přesné výsledky se nepřepočítávají.
V režimu `families` lze ve stejném adresáři také změnit seznam `--families`:
nové rodiny se doplní a dřívější výsledky zůstanou uložené. Exporty zahrnují
všechny dosud uložené rodiny; pro samostatné srovnání jen vybraných rodin použij
nový `--output`. Pro jiné parametry datasetu (např. režim, pravděpodobnost, seed
nebo vstupní soubor) použij jiný `--output`.

Pokud je virtuální prostředí již aktivované, stačí `python main.py ...`.
Alternativní spuštění modulu je `python -m main ...`; za `-m` se nepíše `.py`.

První Ctrl+C zastaví zadávání nových úloh; několik rozpracovaných grafů doběhne
a uloží se. Druhé Ctrl+C může ukončit čekání; již potvrzené záznamy zůstanou
v SQLite. Po pádu nebo násilném ukončení se nedokončené grafy při příštím běhu
zpracují znovu. Jednotlivý graf se obnovuje od začátku, nikoli uprostřed hledání.
Spouštěj jednu zapisující instanci na výstupní adresář.

## Co se ukládá

- `experiment.sqlite`: checkpoint po **každém** grafu, i pokud se podaří pouze meze.
- `values.csv`: jednotlivé grafy v graph6, přesná hodnota nebo meze, stav výpočtu,
  čas, počet automorfismů a svědek minimální překážky rozšíření.
- `summary.csv`: maxima, počty hotových a nehotových grafů, průměr pouze přes přesně
  dokončené výpočty, horní mez a příznak `maximum_certified`.
- `distribution.csv`: četnosti jednotlivých přesných hodnot podle N.
- `plot.png`, `plot.svg`: lineární pohled a pohled s logaritmickou osou N.
- `extremal_candidates.g6`: jeden kandidát pro každé N v pořadí řádků summary.csv;
  případně lepší menší graf doplněný izolovanými vrcholy.

Exporty se obnovují po `--plot-every` grafech, přibližně jednou za minutu a na konci.
Při velkém katalogu používej větší `--plot-every`; opakovaný export všech dat něco stojí.
Graf můžeš znovu vykreslit bez výpočtu:

```powershell
.venv\Scripts\python.exe main.py --plot-only --output results/catalog
```

`observed_lower_bound` je největší prokázaná hodnota přímo mezi zkoumanými grafy
dané velikosti. `padded_lower_bound` využívá i menší grafy: doplnění izolovanými
vrcholy vysokou komplexitu neztrácí.
Tato dolní mez proto neklesá, i když zrovna pro další N zkoušíme slabší kandidáty.

Plné body označují certifikovaná přesná maxima **v rámci algoritmu a úplného
zdrojového katalogu**. Prázdné trojúhelníky jsou pouze dolní meze pro globální
maximum. `global_upper_bound` využívá meze všech grafů, je-li enumerace kompletní;
jinak používá obecnou mez N - 1 pro N >= 1. Čára log2(N) je pouze referenční
křivka. Nemá význam dokázané horní nebo dolní meze ani automatického fitu.

## Které grafy dávají smysl pro výzkum

Začni úplnou enumerací malých N. Potom zkoumej několik nezávislých symetrických
rodin; samotná jedna rodina nemůže určit globální maximum.

```powershell
.venv\Scripts\python.exe main.py --mode families --min-n 3 --max-n 35 --families cycle cube petersen rook kneser --workers 4 --output results/families
.venv\Scripts\python.exe main.py --mode circulant --min-n 6 --max-n 20 --samples 1000 --workers 4 --output results/circulants
```

`families` počítá skutečné grafy obecným algoritmem:

- `cycle`: cykly, vhodná kontrolní rodina; od C6 mají komplexitu 2.
- `cube`: hyperkrychle Qd na 2^d vrcholech.
- `rook`: mřížkové grafy L(K(s,s)) na s² vrcholech.
- `petersen`: Petersenův graf na 10 vrcholech.
- `kneser`: liché Kneserovy grafy KG(2k+1,k), k >= 2; v rozsahu do 35 jde
  o KG(5,2) a KG(7,3). Kneserovo N **není** parametr k, ale binom(2k+1,k).
- `path`, `complete`, `bipartite`: další kontrolní rodiny; poslední znamená
  K(floor(N/2),ceil(N/2)).

`circulant` prochází spojovací množiny v přirozeném binárním pořadí, nejvýše
`--samples` na N. Pomocí komplementace vynechá druhou polovinu množin; některé
izomorfní grafy zůstávají. Jde o systematické hledání kandidátů, nikoli náhodný
nebo úplný vzorek všech grafů. Při omezení počtu vzorků se pořadí může projevit
ve výsledcích. Režim není určen k odhadu pravděpodobnostního rozdělení.

Pro vyšší komplexity jsou zvlášť zajímavé Johnsonovy/Kneserovy grafy, Grassmannovy
grafy a katalogy silně regulárních grafů. Grassmannův graf J2(5,2) už má
155 vrcholů; současný backend s enumerací automorfismů pro tuto velikost není
praktická cesta. Teoretické hodnoty a meze je potřeba označovat zvlášť od měření.

Náhodné G(N,p) grafy mají často triviální automorfismy, a potom rc = 1. Hodí se
ke kontrole nebo studiu typických hodnot, nikoli jako hlavní hledání maxima:

```powershell
.venv\Scripts\python.exe main.py --mode random --min-n 5 --max-n 30 --samples 100 --p 0.3 --seed 42 --workers 4 --output results/random
```

## Větší úplné enumerace a vlastní katalogy

Pro další N použij [nauty/Traces geng](https://users.cecs.anu.edu.au/~bdm/nauty/),
který generuje po jednom zástupci každé izomorfní třídy. Nainstaluj ho v prostředí,
ve kterém běží Python, a nastav cestu k executable:

```powershell
.venv\Scripts\python.exe main.py --mode geng --geng C:\tools\nauty\geng.exe --min-n 10 --max-n 10 --workers 8 --plot-every 25000 --output results/geng
```

Skript používá `geng -q -g N`, výstup čte postupně a v paměti drží nejvýše několik
úloh na pracovní proces. Generátor `geng` zde není nainstalovaný; tento režim byl
ověřen pomocí malého náhradního generátoru. Počty grafů rostou velmi rychle:
N = 8 má 12 346 grafů, N = 9 má 274 668, N = 10 má 12 005 168. Úplná enumerace
tak narazí na počet grafů i po zrychlení výpočtu jednotlivého grafu.

Vlastní graph6 katalog, například silně regulární grafy, lze načíst bez generátoru:

```powershell
.venv\Scripts\python.exe main.py --mode graph6 --input moje_grafy.g6 --min-n 10 --max-n 40 --workers 4 --output results/vlastni
```

U běžného graph6 vstupu se globální maximum nikdy automaticky necertifikuje,
protože skript neví, zda soubor obsahuje všechny grafy. `--connected` v režimech
atlas/catalog/geng/graph6 omezí experiment na souvislé grafy; výsledky potom
neoznačuje za globální f(N).

## Správná definice a algoritmus

Původní `gpt_rc_brute_force.py` zůstává zachovaný jako draft. Testuje
`Aut(G)^(k) = Aut(G)`. Automorfismová grupa grafu je ale již 2-uzavřená: kdo
zachovává všechny orbity uspořádaných dvojic, zachovává i hrany. Tento test by
proto nikdy nedal hodnotu nad 2. **Nestačí zachování grupy; je potřeba
ultrahomogenita po přidání invariantních relací.**

Používáme strukturální konvenci rc = 0 pro již ultrahomogenní graf. Hrany se
při homogenizaci zachovávají; rc = 1 například dovoluje přidat invariantní
unární relace. Výsledky proto nelze bez úpravy srovnávat s grupovou konvencí,
která již binární ultrahomogenní strukturu označuje aritou 2.

Nový algoritmus v `relational_complexity.py` hledá **minimální nerozšiřitelná
částečná izomorfní zobrazení**. Pokud takové zobrazení má r vrcholů, všechna
vlastní omezení se rozšíří na automorfismus, ale celé zobrazení ne. Proto
zachovává všechny invarianty arity menší než r, a potřebujeme invariant arity r.
Naopak každé nerozšiřitelné částečné zobrazení obsahuje minimální takové
omezení. Největší velikost minimální překážky tedy přesně určuje rc.

Pro r >= 2 lze vynechat jeden vrchol x a rozšířit zbývající zobrazení na
automorfismus g. Složením s g^(-1) dostaneme ekvivalentní překážku ve tvaru
**identita na množině S a x -> y**. Stačí tedy hledat množiny S, nikoli všechny
uspořádané n-tice nebo všechny částečné permutace:

1. Rozpoznáme ultrahomogenní grafy pomocí Gardinerovy klasifikace a vrátíme 0.
2. NetworkX spočítá automorfismy. U rigidního nehomogenního grafu vrátíme 1.
3. Každou podmínku x -> y a každý stabilizátor vrcholu reprezentujeme bitsetem
   automorfismů, které podmínku splňují.
4. U dvojice (x,y) stačí jeden zástupce její orbity. S může obsahovat jen vrcholy,
   které mají stejnou sousednost k x i y, aby šlo o částečný izomorfismus grafu.
5. Průnik podmínek pomocí celočíselných AND zjistí rozšiřitelnost. Nerozšiřitelné
   větve dále nerozvíjíme; redundantní podmínky nemohou být v minimální překážce.
6. Po dosažení prázdného průniku zkontrolujeme, že odstranění libovolné podmínky
   opět dává neprázdný průnik. Uložíme největší překážku a jejího svědka.

V nejhorším případě zůstává exponenciální hledání podmnožin a enumerace celé
automorfismové grupy. Není to polynomiální algoritmus. Vyhýbá se ale n^k
tabulkám a testování všech n! obecných permutací z draftu.

## Limity, paralelismus a GPU

Výchozí limit je 30 sekund a 100 000 automorfismů **na graf**. Limit je
kooperativní: jednotlivé interní hledání v NetworkX může běžet déle do další
kontroly. Při limitu je `rc` prázdné a ukládají se prokázané meze. Silnější
již uložená dolní mez se při opakování neztratí. Zkusit nedokončené grafy znovu:

```powershell
.venv\Scripts\python.exe main.py --mode catalog --max-n 9 --timeout 120 --max-automorphisms 500000 --retry-incomplete --workers 4 --plot-every 25000 --output results/catalog
```

Hodnota 0 u obou limitů znamená neomezený běh. Počet pracovníků nastav podle
CPU a paměti; každý proces má vlastní automorfismy a bitsety. Default je nejvýše
4 pracovníci. Při přenosu na druhý stroj přenes celý výstupní adresář až po
skončení zapisujícího procesu, včetně případných SQLite WAL souborů.

**GPU backend zatím není implementovaný ani měřený.** V tomto algoritmu jde
především o větvené hledání, izomorfismy a malé bitové průniky. Pouhé přepsání
do PyTorch/CUDA automaticky nepomůže; smysluplný GPU backend by potřeboval
dávkovat vhodnou část hledání. Současné zrychlení využívá bitsety, symetrie
a paralelní výpočet různých grafů na CPU.

Další rozumný krok pro větší symetrické grafy je backend s generátory grupy
(nauty/Traces nebo bliss) a operacemi se stabilizátory, aby se neukládaly všechny
automorfismy. Až po profilování takového backendu má smysl rozhodovat o GPU.
Pro velké Grassmannovy grafy bude vhodnější využít přímo známou geometrickou
akci a ověřené teoretické meze než obecný grafový brute-force.

## Ověřené výsledky a testy

Úplný experiment pro N = 1 až 9 dal:

| N | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| f(N) | 0 | 0 | 1 | 1 | 1 | 2 | 2 | 2 | 2 |

Zpracovalo se 288 266 grafů, všechny s přesným výsledkem. Mezi dalšími
spočítanými příklady jsou Petersen a KG(7,3) s rc = 3, Q4 a L(K4,4) s rc = 4
a Q5 a L(K5,5) rovněž s rc = 4. To jsou hodnoty jednotlivých grafů a dolní
meze pro f(N), nikoli přesná maxima pro N = 10, 16, 25, 32 či 35.

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Testy porovnávají všechny grafy do 6 vrcholů s nezávislým úplným výpočtem přes
částečná izomorfní zobrazení. Ověřují také známé příklady, komplementaci,
přejmenování vrcholů, svědka překážky, limity, přerušení/navázání, integritu
mezí a odmítnutí nesrovnatelných datasetů.

Konečný experiment může ukázat trend nebo najít kontrapříklad konkrétní mezi;
sám o sobě **nerozhodne asymptotickou otázku f(N) = Θ(log N)**. Proto je potřeba
spojit přesná malá maxima, hledání silných rodin a matematické horní meze.

Malé ukázky výsledků jsou v [examples/](examples/README.md). Kód a dokumentace
jsou pod [licencí MIT](LICENSE); první veřejná verze je připravená jako 0.1.0.
GitHub Actions má nastavené testy a skutečný paralelní běh s exporty na Windows
a Linuxu s Pythonem 3.12 a 3.13. Podmínky pro příspěvky a další směry vývoje
popisuje [CONTRIBUTING.md](CONTRIBUTING.md).
