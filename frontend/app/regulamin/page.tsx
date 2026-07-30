import type { Metadata } from "next";
import styles from "./regulamin.module.css";

export const metadata: Metadata = {
  title: "Regulamin — LegitScore",
  description: "Regulamin serwisu LegitScore.",
};

const CONTENT = `
<h1>Regulamin serwisu LegitScore</h1>
<p class="meta">legitscore.app · Wersja 1.0 · obowiązuje od [DATA WEJŚCIA W ŻYCIE]</p>

<div class="note">
  <strong>Najważniejsze:</strong> LegitScore dostarcza <strong>ocenę ryzyka autentyczności</strong> koszulki na podstawie zdjęć. <strong>Nie jest to certyfikat autentyczności, gwarancja ani ekspertyza rzeczoznawcza.</strong> Wynik ma charakter informacyjny i pomocniczy — ostateczną decyzję podejmujesz samodzielnie.
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
  <li><strong>Usługa</strong> — analiza przesłanych zdjęć koszulki i wygenerowanie raportu oceny ryzyka autentyczności.</li>
  <li><strong>Raport</strong> — wynik analizy przesyłany na wskazany adres e-mail, zawierający ocenę ryzyka i uzasadnienie.</li>
  <li><strong>Konsument</strong> — osoba fizyczna zawierająca umowę niezwiązaną bezpośrednio z jej działalnością gospodarczą lub zawodową.</li>
</ol>

<h2>§3. Rodzaj i zakres Usługi</h2>
<ol>
  <li>Usługa polega na automatycznej analizie przesłanych zdjęć (opcjonalnie wraz z linkiem do aukcji) i wygenerowaniu Raportu z <strong>oceną ryzyka autentyczności</strong> w kilku kategoriach, wraz z poziomem pewności.</li>
  <li>Analiza wykonywana jest z użyciem <strong>systemów sztucznej inteligencji</strong> i ma charakter <strong>probabilistyczny i informacyjny</strong>.</li>
  <li><strong>Usługa nie stanowi</strong>: certyfikatu autentyczności, gwarancji, ekspertyzy rzeczoznawczej, opinii biegłego ani porady prawnej. Raport nie jest dokumentem urzędowym.</li>
  <li>W przypadku niewystarczającej jakości lub kompletności zdjęć system może wskazać ograniczenia analizy lub odmówić wydania jednoznacznej oceny.</li>
  <li>Obecnie Usługa świadczona jest <strong>nieodpłatnie</strong> (wersja beta). Wprowadzenie odpłatności nastąpi po aktualizacji Regulaminu.</li>
</ol>

<h2>§4. Warunki korzystania i wymagania techniczne</h2>
<ol>
  <li>Do korzystania z Serwisu potrzebne są: urządzenie z dostępem do internetu, aktualna przeglądarka oraz aktywny adres e-mail.</li>
  <li>Korzystanie z Serwisu nie wymaga zakładania konta; Użytkownik podaje adres e-mail w celu otrzymania Raportu.</li>
  <li>Umowa o świadczenie Usługi zostaje zawarta z chwilą przesłania zdjęć wraz z akceptacją Regulaminu, a kończy się z chwilą dostarczenia Raportu.</li>
</ol>

<h2>§5. Obowiązki Użytkownika</h2>
<ol>
  <li>Użytkownik oświadcza, że posiada prawo do przesyłanych zdjęć i że ich udostępnienie nie narusza praw osób trzecich.</li>
  <li>Zabronione jest przesyłanie treści bezprawnych, w tym naruszających prawa autorskie, dobra osobiste lub zawierających dane osobowe osób trzecich bez podstawy.</li>
  <li>Użytkownik zobowiązuje się nie zakłócać działania Serwisu ani nie korzystać z niego w sposób sprzeczny z prawem lub Regulaminem.</li>
</ol>

<h2>§6. Prawa własności intelektualnej i licencja na zdjęcia</h2>
<ol>
  <li>Serwis, jego oprogramowanie, wygląd i treści stanowią własność Usługodawcy i są chronione prawem.</li>
  <li>Użytkownik zachowuje prawa do przesłanych zdjęć. Przesyłając je, udziela Usługodawcy niewyłącznej, nieodpłatnej licencji na ich przetwarzanie <strong>wyłącznie w celu wykonania Usługi</strong> (w tym przekazanie zewnętrznym dostawcom AI, zgodnie z <a href="/polityka-prywatnosci">Polityką prywatności</a>).</li>
  <li>Raport przeznaczony jest do własnego użytku Użytkownika.</li>
</ol>

<h2>§7. Charakter Usługi i ograniczenie odpowiedzialności</h2>
<ol>
  <li>Raport jest oceną ryzyka o charakterze pomocniczym. Usługodawca <strong>nie gwarantuje</strong> trafności ani kompletności oceny i nie ponosi odpowiedzialności za decyzje (w tym zakupowe) podjęte przez Użytkownika na podstawie Raportu.</li>
  <li>Powyższe ograniczenia nie wyłączają ani nie ograniczają praw Konsumenta wynikających z bezwzględnie obowiązujących przepisów prawa; wobec Konsumentów odpowiedzialność Usługodawcy kształtuje się zgodnie z tymi przepisami.</li>
  <li>Usługodawca nie odpowiada za przerwy w działaniu Serwisu wynikające z przyczyn od niego niezależnych ani za działanie usług zewnętrznych dostawców.</li>
</ol>

<h2>§8. Dane osobowe</h2>
<p>Zasady przetwarzania danych osobowych opisano w <a href="/polityka-prywatnosci">Polityce prywatności</a>.</p>

<h2>§9. Reklamacje</h2>
<ol>
  <li>Reklamacje dotyczące Usługi można składać na adres <a href="mailto:info@legitscore.app">info@legitscore.app</a>.</li>
  <li>Reklamacja powinna zawierać opis problemu oraz adres e-mail użyty przy korzystaniu z Usługi.</li>
  <li>Usługodawca rozpatrzy reklamację w terminie <strong>14 dni</strong> od jej otrzymania i poinformuje o wyniku na podany adres e-mail.</li>
</ol>

<h2>§10. Odstąpienie od umowy (Konsument)</h2>
<ol>
  <li>Konsumentowi co do zasady przysługuje prawo odstąpienia od umowy zawartej na odległość w terminie 14 dni.</li>
  <li>W przypadku Usługi wykonywanej niezwłocznie (natychmiastowa analiza i dostarczenie Raportu), rozpoczynając korzystanie z Usługi Użytkownik będący Konsumentem <strong>wyraża zgodę na jej wykonanie przed upływem terminu do odstąpienia</strong> i przyjmuje do wiadomości, że po pełnym wykonaniu Usługi prawo odstąpienia wygasa.</li>
  <li>Ponieważ Usługa jest obecnie nieodpłatna, odstąpienie nie wiąże się z żadnymi kosztami po stronie Konsumenta.</li>
</ol>

<h2>§11. Pozasądowe rozwiązywanie sporów (ADR)</h2>
<ol>
  <li>Konsument może skorzystać z pozasądowych sposobów rozpatrywania reklamacji i dochodzenia roszczeń, w szczególności zwracając się do: miejskiego lub powiatowego <strong>rzecznika konsumentów</strong>, <strong>Wojewódzkiego Inspektoratu Inspekcji Handlowej</strong> oraz organizacji konsumenckich.</li>
  <li>Informacje o pozasądowym rozwiązywaniu sporów dostępne są na stronie Urzędu Ochrony Konkurencji i Konsumentów (UOKiK): <a href="https://www.uokik.gov.pl">uokik.gov.pl</a>.</li>
  <li class="meta">Uwaga: unijna platforma ODR została zamknięta 20 lipca 2025 r. i nie jest już dostępna.</li>
</ol>

<h2>§12. Zmiany Regulaminu i postanowienia końcowe</h2>
<ol>
  <li>Usługodawca może zmienić Regulamin z ważnych przyczyn (zmiana przepisów, zakresu Usługi, wprowadzenie odpłatności). Aktualna wersja jest zawsze dostępna w Serwisie, z podaną datą obowiązywania.</li>
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
