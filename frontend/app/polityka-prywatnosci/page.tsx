import type { Metadata } from "next";
import styles from "./polityka-prywatnosci.module.css";

export const metadata: Metadata = {
  title: "Polityka prywatności — LegitScore",
  description: "Polityka prywatności serwisu LegitScore.",
};

const CONTENT = `
<h1>Polityka prywatności</h1>
<p class="meta">Serwis LegitScore (legitscore.app) · Wersja 2.1 · obowiązuje od 2 września 2026</p>

<div class="note">
  <strong>W skrócie:</strong> LegitScore wymaga założenia Konta (e-mail i hasło, albo logowanie przez Google/Facebook) i zalogowania się przed uruchomieniem analizy przesłanych zdjęć koszulek. Analiza jest wykonywana z użyciem zewnętrznych usług sztucznej inteligencji. Poniżej wyjaśniamy, jakie dane zbieramy, po co, komu je powierzamy i jakie masz prawa.
</div>

<h2>1. Administrator danych</h2>
<p>Administratorem Twoich danych osobowych jest <strong>Dominik Jezierski</strong>, prowadzący jednoosobową działalność gospodarczą, NIP 7171819791, REGON 384289129, adres: Wilków 20, 24-313 Wilków, województwo lubelskie.</p>
<p>Kontakt w sprawach danych osobowych: <a href="mailto:info@legitscore.app">info@legitscore.app</a>.</p>

<h2>2. Jakie dane przetwarzamy</h2>
<ul>
  <li><strong>Dane Konta</strong> — adres e-mail oraz hasło (przechowywane wyłącznie w formie zahaszowanej, nigdy jawnym tekstem), jeśli zakładasz konto e-mailem; status potwierdzenia adresu e-mail.</li>
  <li><strong>Dane z logowania Google / Facebook</strong> — jeśli logujesz się przez jeden z tych dostawców, otrzymujemy od niego Twój adres e-mail (zweryfikowany przez dostawcę) oraz unikalny identyfikator Twojego konta u tego dostawcy. Nie otrzymujemy ani nie przechowujemy Twojego hasła do Google/Facebooka.</li>
  <li><strong>Zdjęcia koszulek</strong>, które przesyłasz do analizy (mogą zawierać widoczne tło i otoczenie — prosimy nie umieszczać na zdjęciach danych osób trzecich ani informacji, których nie chcesz udostępniać).</li>
  <li><strong>Historia analiz i Kolekcja</strong> — lista Twoich analiz oraz koszulek dodanych do kolekcji, powiązana z Twoim Kontem.</li>
  <li><strong>Opcjonalny link do aukcji</strong> (np. Vinted, eBay, Kleinanzeigen) i powiązane metadane, jeśli je podasz.</li>
  <li><strong>Dane techniczne</strong> — adres IP, informacje o urządzeniu i przeglądarce, logi serwera, w tym w związku z logowaniem (np. w celu wykrywania nadużyć).</li>
  <li><strong>Dane analityczne</strong> — zdarzenia korzystania z serwisu, zbierane za pomocą plików cookies (za Twoją zgodą).</li>
</ul>

<h2>3. Cele i podstawy prawne przetwarzania</h2>
<table>
  <tr><th>Cel</th><th>Podstawa prawna (RODO)</th></tr>
  <tr><td>Założenie i obsługa Konta, w tym logowanie przez Google/Facebook, uwierzytelnianie i zabezpieczenie dostępu</td><td>art. 6 ust. 1 lit. b (niezbędność do wykonania umowy o świadczenie usług drogą elektroniczną)</td></tr>
  <tr><td>Wykonanie usługi analizy i udostępnienie Raportu</td><td>art. 6 ust. 1 lit. b oraz lit. a (zgoda) — w zakresie przetwarzania przesłanych zdjęć</td></tr>
  <tr><td>Wysyłka wiadomości e-mail związanych z Kontem (powitalna, potwierdzenie adresu e-mail, reset hasła)</td><td>art. 6 ust. 1 lit. b oraz lit. f (prawnie uzasadniony interes — bezpieczeństwo Konta)</td></tr>
  <tr><td>Wysyłka materiałów promocyjnych i marketingowych LegitScore (np. kody promocyjne, informacje o nowych funkcjach) na adres e-mail Konta</td><td>art. 6 ust. 1 lit. a (zgoda wyrażona przy zakładaniu Konta — zob. <a href="/regulamin">Regulamin</a>); zgodę można wycofać w każdej chwili bez wpływu na możliwość korzystania z Konta</td></tr>
  <tr><td>Analityka i statystyki (cookies)</td><td>art. 6 ust. 1 lit. a (zgoda wyrażona w banerze cookies)</td></tr>
  <tr><td>Bezpieczeństwo serwisu, zapobieganie nadużyciom (w tym wielokrotnemu zakładaniu Kont), dochodzenie/obrona roszczeń</td><td>art. 6 ust. 1 lit. f (prawnie uzasadniony interes administratora)</td></tr>
</table>
<p>Podanie danych jest dobrowolne, ale niezbędne do skorzystania z usługi — bez założenia Konta, zalogowania się oraz przesłania zdjęć nie możemy wykonać analizy i udostępnić Raportu.</p>

<h2>4. Analiza z użyciem sztucznej inteligencji (AI)</h2>
<p>Analiza zdjęć jest wykonywana <strong>automatycznie, z wykorzystaniem systemów sztucznej inteligencji</strong> dostarczanych przez podmioty zewnętrzne. Wynik ma charakter <strong>informacyjnej oceny ryzyka</strong> i — jak każdy wynik systemu AI — może zawierać błędy; nie stanowi urzędowego ani eksperckiego potwierdzenia autentyczności (zob. <a href="/regulamin">Regulamin</a> w zakresie charakteru Usługi i odpowiedzialności). Nie podejmujemy wobec Ciebie <strong>zautomatyzowanej decyzji wywołującej skutki prawne</strong> ani podobnie istotnej decyzji w rozumieniu art. 22 RODO — ostateczną decyzję (np. o zakupie) podejmujesz samodzielnie.</p>

<h2>5. Odbiorcy danych (podmioty przetwarzające)</h2>
<p>Aby wykonać usługę, powierzamy dane zaufanym dostawcom działającym w naszym imieniu:</p>
<table>
  <tr><th>Dostawca</th><th>Zakres</th><th>Dane</th></tr>
  <tr><td>Railway</td><td>hosting bazy danych i aplikacji backendowej (serwera)</td><td>dane Konta, zdjęcia, raporty, logi</td></tr>
  <tr><td>Vercel</td><td>hosting aplikacji frontendowej (strony)</td><td>logi żądań, dane techniczne</td></tr>
  <tr><td>Google (Gemini Vision API)</td><td>analiza zdjęć przez AI</td><td>zdjęcia, metadane</td></tr>
  <tr><td>Resend</td><td>wysyłka wiadomości e-mail (powitalnej, weryfikacyjnej, resetu hasła, raportu)</td><td>adres e-mail</td></tr>
  <tr><td>Google Analytics</td><td>analityka ruchu w serwisie</td><td>cookies, IP, zdarzenia</td></tr>
  <tr><td>PostHog</td><td>analityka produktowa (jeśli włączona)</td><td>zdarzenia, identyfikatory</td></tr>
  <tr><td>Cloudflare</td><td>infrastruktura, CDN, bezpieczeństwo</td><td>IP, logi</td></tr>
  <tr><td>Make.com</td><td>automatyzacja przepływu danych</td><td>dane przekazywane w procesie</td></tr>
  <tr><td>Placid.app</td><td>generowanie grafik do raportu</td><td>dane raportu</td></tr>
</table>
<p>Dodatkowo, jeśli logujesz się przez <strong>Google</strong> lub <strong>Facebook (Meta)</strong>, te podmioty działają jako niezależni administratorzy w zakresie samego procesu logowania na ich platformie — otrzymujemy od nich wyłącznie Twój zweryfikowany adres e-mail i identyfikator konta, na zasadach opisanych w ich własnych politykach prywatności.</p>

<h2>6. Przekazywanie danych poza EOG</h2>
<p>Niektórzy z powyższych dostawców mają siedzibę lub przetwarzają dane poza Europejskim Obszarem Gospodarczym (m.in. w USA). W takich przypadkach transfer odbywa się na podstawie odpowiednich zabezpieczeń, tj. <strong>standardowych klauzul umownych (SCC)</strong> zatwierdzonych przez Komisję Europejską lub <strong>decyzji o adekwatności</strong> (np. EU-US Data Privacy Framework). Możesz uzyskać kopię zabezpieczeń, kontaktując się z nami.</p>

<h2>7. Okres przechowywania</h2>
<ul>
  <li><strong>Dane Konta</strong> (e-mail, hasło, dane logowania OAuth): do czasu usunięcia Konta. Konto możesz usunąć samodzielnie w każdej chwili w ustawieniach Konta w Serwisie — usunięcie jest natychmiastowe i obejmuje dane Konta oraz powiązaną Kolekcję.</li>
  <li><strong>Zdjęcia i Raporty:</strong> przez czas niezbędny do wykonania usługi i obsługi ewentualnych reklamacji, nie dłużej niż 24 miesiące lub do momentu usunięcia Konta / cofnięcia zgody / żądania usunięcia.</li>
  <li><strong>Dane techniczne / logi:</strong> przez okres niezbędny dla bezpieczeństwa, zwykle do 12 miesięcy.</li>
  <li><strong>Dane analityczne (cookies):</strong> zgodnie z okresami ważności poszczególnych plików cookies i do czasu cofnięcia zgody.</li>
</ul>
<p class="meta">[Okresy do potwierdzenia z rzeczywistą konfiguracją systemu.]</p>

<h2>8. Twoje prawa</h2>
<p>Masz prawo do: dostępu do danych, ich sprostowania, usunięcia, ograniczenia przetwarzania, wniesienia sprzeciwu, przenoszenia danych oraz cofnięcia zgody w dowolnym momencie (bez wpływu na zgodność z prawem przetwarzania przed jej cofnięciem). Usunięcie Konta i danych możesz zrealizować samodzielnie w ustawieniach Konta, a dostęp do swoich danych (eksport) pobrać bezpośrednio z Serwisu. Aby skorzystać z pozostałych praw, napisz na <a href="mailto:info@legitscore.app">info@legitscore.app</a>.</p>
<p>Masz również prawo wnieść skargę do organu nadzorczego: <strong>Prezes Urzędu Ochrony Danych Osobowych (PUODO)</strong>, ul. Stawki 2, 00-193 Warszawa.</p>

<h2>9. Pliki cookies</h2>
<p>Serwis używa plików cookies:</p>
<ul>
  <li><strong>Niezbędne</strong> — konieczne do działania serwisu (w tym utrzymania sesji zalogowanego Użytkownika); nie wymagają zgody.</li>
  <li><strong>Analityczne</strong> (Google Analytics, ewentualnie PostHog) — ładowane wyłącznie po wyrażeniu zgody w banerze cookies. Zgodę możesz w każdej chwili wycofać, zmieniając ustawienia cookies lub usuwając je w przeglądarce.</li>
</ul>

<h2>10. Zmiany polityki</h2>
<p>Możemy aktualizować niniejszą Politykę, np. w związku ze zmianami w usłudze lub przepisach. Aktualna wersja jest zawsze dostępna w serwisie, z podaną datą obowiązywania.</p>

<footer>
  LegitScore · legitscore.app · kontakt: info@legitscore.app<br>
  Dokument informacyjny — nie stanowi porady prawnej. Zalecany przegląd przez radcę prawnego / adwokata przed publikacją.
</footer>
`;

export default function PolitykaPrywatnosciPage() {
  return (
    <div className={styles.paper} dangerouslySetInnerHTML={{ __html: CONTENT }} />
  );
}
