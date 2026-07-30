import type { Metadata } from "next";
import styles from "./polityka-prywatnosci.module.css";

export const metadata: Metadata = {
  title: "Polityka prywatności — LegitScore",
  description: "Polityka prywatności serwisu LegitScore.",
};

const CONTENT = `
<h1>Polityka prywatności</h1>
<p class="meta">Serwis LegitScore (legitscore.app) · Wersja 1.0 · obowiązuje od [DATA WEJŚCIA W ŻYCIE]</p>

<div class="note">
  <strong>W skrócie:</strong> LegitScore analizuje przesłane przez Ciebie zdjęcia koszulek z użyciem zewnętrznych usług sztucznej inteligencji i przesyła wynik na podany adres e-mail. Poniżej wyjaśniamy, jakie dane zbieramy, po co, komu je powierzamy i jakie masz prawa.
</div>

<h2>1. Administrator danych</h2>
<p>Administratorem Twoich danych osobowych jest <strong>Dominik Jezierski</strong>, prowadzący jednoosobową działalność gospodarczą, NIP 7171819791, REGON 384289129, adres: Wilków 20, 24-313 Wilków, województwo lubelskie.</p>
<p>Kontakt w sprawach danych osobowych: <a href="mailto:info@legitscore.app">info@legitscore.app</a>.</p>

<h2>2. Jakie dane przetwarzamy</h2>
<ul>
  <li><strong>Zdjęcia koszulek</strong>, które przesyłasz do analizy (mogą zawierać widoczne tło i otoczenie — prosimy nie umieszczać na zdjęciach danych osób trzecich ani informacji, których nie chcesz udostępniać).</li>
  <li><strong>Adres e-mail</strong> — podawany w celu otrzymania raportu.</li>
  <li><strong>Opcjonalny link do aukcji</strong> (np. Vinted, Allegro, eBay) i powiązane metadane, jeśli je podasz.</li>
  <li><strong>Dane techniczne</strong> — adres IP, informacje o urządzeniu i przeglądarce, logi serwera.</li>
  <li><strong>Dane analityczne</strong> — zdarzenia korzystania z serwisu, zbierane za pomocą plików cookies (za Twoją zgodą).</li>
</ul>

<h2>3. Cele i podstawy prawne przetwarzania</h2>
<table>
  <tr><th>Cel</th><th>Podstawa prawna (RODO)</th></tr>
  <tr><td>Wykonanie usługi analizy i wysłanie raportu na e-mail</td><td>art. 6 ust. 1 lit. b (niezbędność do wykonania usługi) oraz lit. a (zgoda) — w zakresie przetwarzania przesłanych zdjęć</td></tr>
  <tr><td>Analityka i statystyki (cookies)</td><td>art. 6 ust. 1 lit. a (zgoda wyrażona w banerze cookies)</td></tr>
  <tr><td>Bezpieczeństwo serwisu, zapobieganie nadużyciom, dochodzenie/obrona roszczeń</td><td>art. 6 ust. 1 lit. f (prawnie uzasadniony interes administratora)</td></tr>
</table>
<p>Podanie danych jest dobrowolne, ale niezbędne do skorzystania z usługi — bez przesłania zdjęć i podania adresu e-mail nie możemy wykonać analizy i dostarczyć raportu.</p>

<h2>4. Analiza z użyciem sztucznej inteligencji (AI)</h2>
<p>Analiza zdjęć jest wykonywana <strong>automatycznie, z wykorzystaniem systemów sztucznej inteligencji</strong> dostarczanych przez podmioty zewnętrzne. Wynik ma charakter <strong>informacyjnej oceny ryzyka</strong> i nie stanowi urzędowego ani eksperckiego potwierdzenia autentyczności. Nie podejmujemy wobec Ciebie <strong>zautomatyzowanej decyzji wywołującej skutki prawne</strong> ani podobnie istotnej decyzji w rozumieniu art. 22 RODO — ostateczną decyzję (np. o zakupie) podejmujesz samodzielnie.</p>

<h2>5. Odbiorcy danych (podmioty przetwarzające)</h2>
<p>Aby wykonać usługę, powierzamy dane zaufanym dostawcom działającym w naszym imieniu:</p>
<table>
  <tr><th>Dostawca</th><th>Zakres</th><th>Dane</th></tr>
  <tr><td>Google (Gemini Vision API)</td><td>analiza zdjęć przez AI</td><td>zdjęcia, metadane</td></tr>
  <tr><td>Resend</td><td>wysyłka wiadomości e-mail z raportem</td><td>adres e-mail</td></tr>
  <tr><td>Google Analytics</td><td>analityka ruchu w serwisie</td><td>cookies, IP, zdarzenia</td></tr>
  <tr><td>PostHog</td><td>analityka produktowa (jeśli włączona)</td><td>zdarzenia, identyfikatory</td></tr>
  <tr><td>Cloudflare</td><td>infrastruktura, CDN, bezpieczeństwo</td><td>IP, logi</td></tr>
  <tr><td>Make.com</td><td>automatyzacja przepływu danych</td><td>dane przekazywane w procesie</td></tr>
  <tr><td>Placid.app</td><td>generowanie grafik do raportu</td><td>dane raportu</td></tr>
</table>

<h2>6. Przekazywanie danych poza EOG</h2>
<p>Niektórzy z powyższych dostawców mają siedzibę lub przetwarzają dane poza Europejskim Obszarem Gospodarczym (m.in. w USA). W takich przypadkach transfer odbywa się na podstawie odpowiednich zabezpieczeń, tj. <strong>standardowych klauzul umownych (SCC)</strong> zatwierdzonych przez Komisję Europejską lub <strong>decyzji o adekwatności</strong> (np. EU-US Data Privacy Framework). Możesz uzyskać kopię zabezpieczeń, kontaktując się z nami.</p>

<h2>7. Okres przechowywania</h2>
<ul>
  <li><strong>Zdjęcia i raporty:</strong> przez czas niezbędny do wykonania usługi i obsługi ewentualnych reklamacji, nie dłużej niż [np. 24 miesiące] lub do momentu cofnięcia zgody / żądania usunięcia.</li>
  <li><strong>Adres e-mail:</strong> do czasu wykonania usługi oraz obsługi reklamacji i roszczeń.</li>
  <li><strong>Dane techniczne / logi:</strong> przez okres niezbędny dla bezpieczeństwa, zwykle do [np. 12 miesięcy].</li>
  <li><strong>Dane analityczne (cookies):</strong> zgodnie z okresami ważności poszczególnych plików cookies i do czasu cofnięcia zgody.</li>
</ul>
<p class="meta">[Okresy do potwierdzenia z rzeczywistą konfiguracją systemu.]</p>

<h2>8. Twoje prawa</h2>
<p>Masz prawo do: dostępu do danych, ich sprostowania, usunięcia, ograniczenia przetwarzania, wniesienia sprzeciwu, przenoszenia danych oraz cofnięcia zgody w dowolnym momencie (bez wpływu na zgodność z prawem przetwarzania przed jej cofnięciem). Aby skorzystać z praw, napisz na <a href="mailto:info@legitscore.app">info@legitscore.app</a>.</p>
<p>Masz również prawo wnieść skargę do organu nadzorczego: <strong>Prezes Urzędu Ochrony Danych Osobowych (PUODO)</strong>, ul. Stawki 2, 00-193 Warszawa.</p>

<h2>9. Pliki cookies</h2>
<p>Serwis używa plików cookies:</p>
<ul>
  <li><strong>Niezbędne</strong> — konieczne do działania serwisu; nie wymagają zgody.</li>
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
