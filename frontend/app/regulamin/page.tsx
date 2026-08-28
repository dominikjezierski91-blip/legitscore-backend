import type { Metadata } from "next";
import styles from "./regulamin.module.css";

export const metadata: Metadata = {
  title: "Regulamin — LegitScore",
  description: "Regulamin serwisu LegitScore.",
};

const CONTENT = `
<h1>Regulamin serwisu LegitScore</h1>
<p class="meta">legitscore.app · Wersja 2.0 · obowiązuje od 27 sierpnia 2026</p>

<div class="note">
  <strong>Najważniejsze:</strong> LegitScore dostarcza <strong>ocenę ryzyka autentyczności</strong> koszulki na podstawie zdjęć, wykonywaną przez systemy sztucznej inteligencji. <strong>Nie jest to certyfikat autentyczności, gwarancja ani ekspertyza rzeczoznawcza — i może zawierać błędy.</strong> Wynik ma charakter informacyjny i pomocniczy — ostateczną decyzję (w tym zakupową lub sprzedażową) podejmujesz wyłącznie samodzielnie, na własne ryzyko. Skorzystanie z Usługi wymaga założenia Konta i zalogowania się.
</div>

<h2>§1. Postanowienia ogólne</h2>
<ol>
  <li>Niniejszy Regulamin określa zasady korzystania z serwisu internetowego LegitScore, dostępnego pod adresem legitscore.app (dalej „Serwis").</li>
  <li>Usługodawcą jest Dominik Jezierski, prowadzący jednoosobową działalność gospodarczą, NIP 7171819791, REGON 384289129, adres: Wilków 20, 24-313 Wilków (dalej „Usługodawca").</li>
  <li>Kontakt z Usługodawcą: <a href="mailto:info@legitscore.app">info@legitscore.app</a>.</li>
  <li>Regulamin jest regulaminem, o którym mowa w art. 8 ustawy o świadczeniu usług drogą elektroniczną.</li>
</ol>

<h2>§2. Definicje</h2>
<ol>
  <li><strong>Użytkownik</strong> — osoba korzystająca z Serwisu.</li>
  <li><strong>Konto</strong> — indywidualny profil Użytkownika w Serwisie, założony przy użyciu adresu e-mail i hasła albo poprzez logowanie za pośrednictwem zewnętrznego dostawcy tożsamości (Google lub Facebook), niezbędny do uruchomienia Analizy.</li>
  <li><strong>Usługa</strong> — analiza przesłanych zdjęć koszulki i wygenerowanie Raportu oceny ryzyka autentyczności, dostępna po zalogowaniu na Konto.</li>
  <li><strong>Raport</strong> — wynik Analizy, dostępny w Serwisie i do pobrania w formacie PDF, zawierający ocenę ryzyka i uzasadnienie.</li>
  <li><strong>Konsument</strong> — osoba fizyczna zawierająca umowę niezwiązaną bezpośrednio z jej działalnością gospodarczą lub zawodową.</li>
</ol>

<h2>§3. Rodzaj i zakres Usługi</h2>
<ol>
  <li>Usługa polega na automatycznej analizie przesłanych zdjęć (opcjonalnie wraz z linkiem do aukcji) i wygenerowaniu Raportu z <strong>oceną ryzyka autentyczności</strong> w kilku kategoriach, wraz z poziomem pewności.</li>
  <li>Analiza wykonywana jest <strong>wyłącznie z użyciem systemów sztucznej inteligencji</strong> i ma charakter <strong>probabilistyczny i informacyjny</strong>. Systemy sztucznej inteligencji, ze swojej natury, mogą się mylić — mogą ocenić koszulkę oryginalną jako podrobioną lub odwrotnie. Jest to znana i akceptowana cecha tego rodzaju technologii, a nie wada Usługi.</li>
  <li><strong>Usługa nie stanowi</strong>: certyfikatu autentyczności, gwarancji, ekspertyzy rzeczoznawczej, opinii biegłego ani porady prawnej. Raport nie jest dokumentem urzędowym i nie ma mocy dowodowej w postępowaniach sądowych ani administracyjnych.</li>
  <li>W przypadku niewystarczającej jakości lub kompletności zdjęć system może wskazać ograniczenia analizy lub odmówić wydania jednoznacznej oceny.</li>
  <li>Uruchomienie Analizy wymaga zalogowania na Konto (zob. §4). Przesłanie zdjęć może nastąpić przed zalogowaniem, natomiast sama Analiza rozpoczyna się dopiero po zalogowaniu.</li>
  <li>Obecnie pierwsza i kolejne Analizy są <strong>nieodpłatne</strong> (wersja beta). Usługodawca zamierza docelowo wprowadzić model, w którym pierwsza Analiza pozostanie darmowa dla zalogowanego Użytkownika, a kolejne mogą być odpłatne zgodnie z cennikiem publikowanym w Serwisie. Wprowadzenie odpłatności nastąpi wyłącznie po uprzedniej aktualizacji Regulaminu i publikacji cennika, z odpowiednim wyprzedzeniem, i nie będzie dotyczyć Usług już wykonanych ani rozpoczętych przed tą zmianą.</li>
</ol>

<h2>§4. Konto Użytkownika i logowanie</h2>
<ol>
  <li>Założenie Konta wymaga podania adresu e-mail i ustawienia hasła, albo zalogowania się za pośrednictwem konta Google lub Facebook (logowanie OAuth) — w tym drugim przypadku Konto zakładane jest automatycznie z wykorzystaniem adresu e-mail zweryfikowanego przez odpowiedniego dostawcę.</li>
  <li>Z Serwisu mogą korzystać osoby, które ukończyły 18 lat i posiadają pełną zdolność do czynności prawnych, albo osoby niepełnoletnie za zgodą przedstawiciela ustawowego.</li>
  <li>Użytkownik zobowiązany jest zachować w poufności dane dostępowe do Konta i ponosi odpowiedzialność za działania podejmowane przy ich użyciu, chyba że utrata poufności nastąpiła z przyczyn leżących po stronie Usługodawcy.</li>
  <li>Adres e-mail podany przy rejestracji może wymagać potwierdzenia poprzez kliknięcie linku weryfikacyjnego. Brak potwierdzenia adresu e-mail nie ogranicza obecnie możliwości korzystania z Serwisu, może jednak stanowić warunek korzystania z wybranych funkcji w przyszłości (np. limitów darmowych Analiz), o czym Użytkownik zostanie poinformowany.</li>
  <li>Logowanie za pośrednictwem Google lub Facebook podlega dodatkowo regulaminom i politykom prywatności tych dostawców, niezależnym od Usługodawcy.</li>
  <li>Użytkownik może w każdej chwili usunąć swoje Konto samodzielnie, w ustawieniach Konta w Serwisie, albo poprzez zgłoszenie takiego żądania na adres <a href="mailto:info@legitscore.app">info@legitscore.app</a>. Usunięcie Konta jest nieodwracalne i wiąże się z utratą dostępu do Kolekcji i Historii analiz powiązanych z Kontem.</li>
  <li>Usługodawca może zawiesić lub usunąć Konto Użytkownika naruszającego Regulamin lub obowiązujące przepisy prawa, po uprzedniej próbie wyjaśnienia sytuacji, chyba że charakter naruszenia uzasadnia natychmiastowe działanie.</li>
</ol>

<h2>§5. Warunki techniczne</h2>
<ol>
  <li>Do korzystania z Serwisu potrzebne są: urządzenie z dostępem do internetu, aktualna przeglądarka oraz aktywny adres e-mail.</li>
  <li>Umowa o świadczenie Usługi zostaje zawarta z chwilą uruchomienia Analizy (zalogowanym Użytkownikiem) i kończy się z chwilą udostępnienia Raportu.</li>
</ol>

<h2>§6. Obowiązki Użytkownika</h2>
<ol>
  <li>Użytkownik oświadcza, że posiada prawo do przesyłanych zdjęć i że ich udostępnienie nie narusza praw osób trzecich.</li>
  <li>Zabronione jest przesyłanie treści bezprawnych, w tym naruszających prawa autorskie, dobra osobiste lub zawierających dane osobowe osób trzecich bez podstawy.</li>
  <li>Użytkownik zobowiązuje się nie zakłócać działania Serwisu ani nie korzystać z niego w sposób sprzeczny z prawem lub Regulaminem, w tym nie zakładać wielu Kont w celu obejścia limitów Usługi.</li>
</ol>

<h2>§7. Prawa własności intelektualnej i licencja na zdjęcia</h2>
<ol>
  <li>Serwis, jego oprogramowanie, wygląd i treści stanowią własność Usługodawcy i są chronione prawem.</li>
  <li>Użytkownik zachowuje prawa do przesłanych zdjęć. Przesyłając je, udziela Usługodawcy niewyłącznej, nieodpłatnej licencji na ich przetwarzanie <strong>wyłącznie w celu wykonania Usługi</strong> (w tym przekazanie zewnętrznym dostawcom AI, zgodnie z <a href="/polityka-prywatnosci">Polityką prywatności</a>).</li>
  <li>Raport przeznaczony jest do własnego użytku Użytkownika.</li>
</ol>

<h2>§8. Charakter Usługi i ograniczenie odpowiedzialności</h2>
<ol>
  <li>Raport ma charakter wyłącznie pomocniczy i informacyjny. Usługodawca <strong>nie gwarantuje</strong> trafności, kompletności ani bezbłędności oceny wygenerowanej przez systemy sztucznej inteligencji.</li>
  <li>Usługodawca nie ponosi odpowiedzialności za decyzje podjęte przez Użytkownika na podstawie Raportu, w tym w szczególności za decyzje zakupowe, sprzedażowe lub inwestycyjne dotyczące koszulki będącej przedmiotem Analizy, ani za jakiekolwiek szkody majątkowe lub niemajątkowe wynikające z rozbieżności między oceną zawartą w Raporcie a rzeczywistym stanem rzeczy.</li>
  <li>W najszerszym zakresie dopuszczalnym przez bezwzględnie obowiązujące przepisy prawa, łączna odpowiedzialność Usługodawcy wobec danego Użytkownika z tytułu wykonania lub niewykonania Usługi ograniczona jest do wysokości kwoty faktycznie zapłaconej przez tego Użytkownika za daną Usługę, a w przypadku Usług świadczonych nieodpłatnie — odpowiedzialność ta jest wyłączona. Ograniczenie to nie dotyczy szkód wyrządzonych Użytkownikowi z winy umyślnej.</li>
  <li>Powyższe ograniczenia nie wyłączają ani nie ograniczają praw Konsumenta wynikających z bezwzględnie obowiązujących przepisów prawa, w tym przepisów o rękojmi i niezgodności usługi cyfrowej z umową; wobec Konsumentów odpowiedzialność Usługodawcy kształtuje się zgodnie z tymi przepisami, z uwzględnieniem ograniczenia z ust. 3 w zakresie, w jakim przepisy te na to pozwalają.</li>
  <li>Usługodawca nie odpowiada za przerwy w działaniu Serwisu wynikające z przyczyn od niego niezależnych ani za działanie usług zewnętrznych dostawców (w tym dostawców systemów AI, hostingu, poczty elektronicznej oraz logowania Google/Facebook).</li>
</ol>

<h2>§9. Dane osobowe</h2>
<p>Zasady przetwarzania danych osobowych, w tym danych Konta i danych otrzymywanych od Google/Facebook przy logowaniu, opisano w <a href="/polityka-prywatnosci">Polityce prywatności</a>.</p>

<h2>§10. Reklamacje</h2>
<ol>
  <li>Reklamacje dotyczące Usługi można składać na adres <a href="mailto:info@legitscore.app">info@legitscore.app</a>.</li>
  <li>Reklamacja powinna zawierać opis problemu oraz adres e-mail powiązany z Kontem, którego dotyczy zgłoszenie.</li>
  <li>Usługodawca rozpatrzy reklamację w terminie <strong>14 dni</strong> od jej otrzymania i poinformuje o wyniku na podany adres e-mail.</li>
</ol>

<h2>§11. Odstąpienie od umowy (Konsument)</h2>
<ol>
  <li>Konsumentowi co do zasady przysługuje prawo odstąpienia od umowy zawartej na odległość w terminie 14 dni.</li>
  <li>W przypadku Usługi wykonywanej niezwłocznie (natychmiastowa analiza i udostępnienie Raportu), uruchamiając Analizę Użytkownik będący Konsumentem <strong>wyraża zgodę na jej wykonanie przed upływem terminu do odstąpienia</strong> i przyjmuje do wiadomości, że po pełnym wykonaniu Usługi prawo odstąpienia wygasa.</li>
  <li>Dopóki Usługa jest nieodpłatna, odstąpienie nie wiąże się z żadnymi kosztami po stronie Konsumenta. Po ewentualnym wprowadzeniu odpłatności zasady odstąpienia od umów odpłatnych zostaną opisane w zaktualizowanym Regulaminie zgodnie z obowiązującymi przepisami o prawach konsumenta.</li>
</ol>

<h2>§12. Pozasądowe rozwiązywanie sporów (ADR)</h2>
<ol>
  <li>Konsument może skorzystać z pozasądowych sposobów rozpatrywania reklamacji i dochodzenia roszczeń, w szczególności zwracając się do: miejskiego lub powiatowego <strong>rzecznika konsumentów</strong>, <strong>Wojewódzkiego Inspektoratu Inspekcji Handlowej</strong> oraz organizacji konsumenckich.</li>
  <li>Informacje o pozasądowym rozwiązywaniu sporów dostępne są na stronie Urzędu Ochrony Konkurencji i Konsumentów (UOKiK): <a href="https://www.uokik.gov.pl">uokik.gov.pl</a>.</li>
  <li class="meta">Uwaga: unijna platforma ODR została zamknięta 20 lipca 2025 r. i nie jest już dostępna.</li>
</ol>

<h2>§13. Zmiany Regulaminu i postanowienia końcowe</h2>
<ol>
  <li>Usługodawca może zmienić Regulamin z ważnych przyczyn (zmiana przepisów, zakresu Usługi, wprowadzenie lub zmiana odpłatności). Aktualna wersja jest zawsze dostępna w Serwisie, z podaną datą obowiązywania. Zmiany wprowadzające lub zmieniające odpłatność nie mają zastosowania do Usług już wykonanych ani rozpoczętych przed ich wejściem w życie.</li>
  <li>W sprawach nieuregulowanych stosuje się prawo polskie oraz właściwe przepisy powszechnie obowiązujące.</li>
  <li>Regulamin jest dostępny nieodpłatnie w Serwisie w formie umożliwiającej jego pobranie i wydruk.</li>
</ol>

<footer>
  LegitScore · legitscore.app · kontakt: info@legitscore.app<br>
  Dokument nie stanowi porady prawnej. Zalecany przegląd przez radcę prawnego / adwokata przed publikacją.
</footer>
`;

export default function RegulaminPage() {
  return (
    <div className={styles.paper} dangerouslySetInnerHTML={{ __html: CONTENT }} />
  );
}
