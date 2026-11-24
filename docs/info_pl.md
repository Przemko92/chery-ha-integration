# Encje integracji Chery Europe (0.7.0b2)

Dokument opisuje **102 encje**, które integracja tworzy dla samochodu (testowane na Tiggo 7/8, Home Assistant 2026.11.2, kod 0.7.0b2 — PR #41).
Wszystkie encje są zgrupowane pod jednym urządzeniem. W identyfikatorach przedrostek zastąpiono gwiazdką: `*` = nazwa obszaru i urządzenia (`wspolne_tiggo` to tylko przykład).

> **Wersja.** Opis dotyczy 0.7.0b2 (PR #41, `d4ee028e`). W gałęzi `master` (0.6.1) nie ma jeszcze encji planu wyjazdu (`*_wyjazd_*`), więc sekcja „Plany wyjazdu” i część przycisków jej nie dotyczy.

## Jak czytać

- **Encja** — identyfikator używany w automatyzacjach (`entity_id`). `*` zastępuje nazwę obszaru i urządzenia — wstaw swoją, np. `switch.wspolne_tiggo_ladowanie_plan`.
- **Co to znaczy** — co dana encja pokazuje albo co robi po wywołaniu.
- **Wartości** — jednostka albo lista dopuszczalnych stanów.
- **Uwagi** — ograniczenia: PIN, kategorie ukryte w UI, zależności.

Encje z kategorii *konfiguracja* i *diagnostyka* Home Assistant domyślnie ukrywa na karcie urządzenia (widać je po włączeniu „Pokaż ukryte” / w narzędziach deweloperskich).

## Sensory — dane z auta (41)

Wartości liczbowe i tekstowe. Większość pojawia się w UI, sensory z kategorii konfiguracja/diagnostyka są domyślnie ukryte.

| Encja | Co to znaczy | Wartości | Uwagi |
|---|---|---|---|
| `sensor.*_alarmy`<br>Alarmy | Liczba aktywnych alarmów/ostrzeżeń auta. Atrybuty: `count`, `warnings`, `categories`, lista `alerts`. |  | atrybuty: alerts[] |
| `sensor.*_alarmy_tresc`<br>Alarmy treść | Treści alarmów w jednym miejscu — do wyświetlenia lub wysłania powiadomieniem. |  | atrybuty: alerts[] |
| `sensor.*_bateria_napiecie`<br>Bateria napięcie | Napięcie baterii trakcyjnej (wysokonapięciowej). | V | rośnie przy ładowaniu i rekuperacji |
| `sensor.*_bateria_poziom`<br>Bateria poziom | Poziom naładowania baterii trakcyjnej w procentach. Główny wskaźnik SoC. | % | 0–100 % |
| `sensor.*_bateria_prad`<br>Bateria prąd | Prąd baterii trakcyjnej; wartość ujemna = pobór, dodatnia = ładowanie/oddawanie. | A |  |
| `sensor.*_diagnostyka_ostatnie_pobranie`<br>Diagnostyka ostatnie pobranie | Kiedy HA dostał ostatnie świeże dane z chmury Chery. |  | starsza data = auto śpi / brak połączenia |
| `sensor.*_diagnostyka_wynik_komendy`<br>Diagnostyka wynik komendy | Wynik ostatniej wysłanej komendy (np. potwierdzenie z chmury, błąd, timeout). |  | kategoria: diagnostyka |
| `sensor.*_diagnostyka_wynik_pozycji`<br>Diagnostyka wynik pozycji | Wynik sondowania, czy auto już odpowiada po wybudzeniu. |  | kategoria: diagnostyka |
| `sensor.*_diagnostyka_wynik_wybudzenia`<br>Diagnostyka wynik wybudzenia | Wynik ostatniej próby wybudzenia auta z głębokiego snu. |  | kategoria: diagnostyka |
| `sensor.*_energia_zuzycie`<br>Energia zużycie | Średnie zużycie energii z komputera pokładowego. | kWh/100 km | kWh/100 km |
| `sensor.*_klimatyzacja_temperatura_maks`<br>Klimatyzacja temperatura maks. | Górny limit temperatury klimatyzacji. | °C | kategoria: konfiguracja |
| `sensor.*_klimatyzacja_temperatura_min`<br>Klimatyzacja temperatura min. | Dolny limit temperatury, jaki przyjmuje klimatyzacja tego auta. | °C | kategoria: konfiguracja |
| `sensor.*_kolo_przednie_lewe_cisnienie`<br>Koło przednie lewe ciśnienie | Ciśnienie w kole przednim lewym z czujników TPMS. | bar | bar/kPa wg ustawień HA |
| `sensor.*_kolo_przednie_lewe_temperatura`<br>Koło przednie lewe temperatura | Temperatura czujnika w kole przednim lewym. | °C | °C |
| `sensor.*_kolo_przednie_prawe_cisnienie`<br>Koło przednie prawe ciśnienie | Ciśnienie w kole przednim prawym. | bar | TPMS |
| `sensor.*_kolo_przednie_prawe_temperatura`<br>Koło przednie prawe temperatura | Temperatura czujnika w kole przednim prawym. | °C | °C |
| `sensor.*_kolo_tylne_lewe_cisnienie`<br>Koło tylne lewe ciśnienie | Ciśnienie w kole tylnym lewym. | bar | TPMS |
| `sensor.*_kolo_tylne_lewe_temperatura`<br>Koło tylne lewe temperatura | Temperatura czujnika w kole tylnym lewym. | °C | °C |
| `sensor.*_kolo_tylne_prawe_cisnienie`<br>Koło tylne prawe ciśnienie | Ciśnienie w kole tylnym prawym. | bar | TPMS |
| `sensor.*_kolo_tylne_prawe_temperatura`<br>Koło tylne prawe temperatura | Temperatura czujnika w kole tylnym prawym. | °C | °C |
| `sensor.*_ladowanie_moc`<br>Ładowanie moc | Moc, z jaką auto ładuje się w tej chwili. | kW | 0 kW = nie ładuje |
| `sensor.*_ladowanie_pozostaly_czas`<br>Ładowanie pozostały czas | Ile zostało do końca bieżącego ładowania. | min | minuty |
| `sensor.*_ladowanie_stan`<br>Ładowanie stan | Stan ładowania: nie ładuje / ładuje / ładowanie zakończone. | not_charging, charging, charge_complete | tekst |
| `sensor.*_ladowanie_stan_zaplanowany`<br>Ładowanie stan zaplanowany | Stan ładowania z planu (harmonogramu w aucie): wyłączony / aktywny / trwa. | off, enabled, running | off / enabled / running |
| `sensor.*_paliwo_poziom`<br>Paliwo poziom | Poziom paliwa w zbiorniku. | % | % |
| `sensor.*_paliwo_spalanie`<br>Paliwo spalanie | Średnie spalanie z komputera pokładowego. | L/100 km | L/100 km |
| `sensor.*_pojazd_kolor`<br>Pojazd kolor | Kolor nadwozia z API. |  | kategoria: konfiguracja |
| `sensor.*_pojazd_model`<br>Pojazd model | Pełna nazwa/model auta z API. |  | kategoria: konfiguracja |
| `sensor.*_pojazd_nazwa`<br>Pojazd nazwa | Nazwa auta nadana w aplikacji Chery. |  | kategoria: konfiguracja |
| `sensor.*_pojazd_predkosc`<br>Pojazd prędkość | Prędkość z ostatniego odczytu z auta. | km/h | km/h |
| `sensor.*_pojazd_zdjecie`<br>Pojazd zdjęcie | Adres obrazka auta zwracany przez API (do kart w dashboardzie). |  | kategoria: konfiguracja |
| `sensor.*_przebieg_elektryczny`<br>Przebieg elektryczny | Część przebiegu przejechana na prądzie. | km | km |
| `sensor.*_przebieg_laczny`<br>Przebieg łączny | Przebieg całkowity auta. | km | km |
| `sensor.*_temperatura_zewnetrzna`<br>Temperatura zewnętrzna | Temperatura zewnętrzna mierzona przez auto. | °C | °C |
| `sensor.*_wiadomosci`<br>Wiadomości | Liczba wiadomości w lokalnej historii pobranej z chmury. Atrybuty: ostatnie wiadomości z tytułem i treścią. |  | atrybuty: messages[] |
| `sensor.*_wiadomosci_nieprzeczytane`<br>Wiadomości nieprzeczytane | Czy w skrzynce są nieprzeczytane wiadomości (on/off) + ich liczba i lista w atrybutach. |  | atrybuty: unread_count, unread[] |
| `sensor.*_wyjazd_nastepny`<br>Wyjazd następny | Najbliższy wyjazd wynikający z planów — znacznik czasu, wygodny do wyzwalaczy automatyzacji. |  | timestamp |
| `sensor.*_wyjazd_plany`<br>Wyjazd plany | Liczba planów wyjazdu zapisanych w aucie (maks. 5). W atrybutach `plans` pełna lista: nazwa, godzina, dni, temperatura, włączony. |  | atrybuty: plans, polled_at |
| `sensor.*_zasieg_elektryczny`<br>Zasięg elektryczny | Zasięg wyłącznie na napędzie elektrycznym. | km | km |
| `sensor.*_zasieg_laczny`<br>Zasięg łączny | Zasięg łączny według komputera auta (prąd + paliwo). | km | km |
| `sensor.*_zasieg_paliwo`<br>Zasięg paliwo | Zasięg wyłącznie na paliwie. | km | km |

## Sensory binarne — stany tak/nie (24)

on/off: otwarte, trwa, wykryto.

| Encja | Co to znaczy | Wartości | Uwagi |
|---|---|---|---|
| `binary_sensor.*_bateria_wysokie_napiecie`<br>Bateria wysokie napięcie | Układ wysokiego napięcia jest aktywny (auto „żyje” elektrycznie). |  |  |
| `binary_sensor.*_drzwi_przednie_lewe`<br>Drzwi przednie lewe | Drzwi przednie lewe są otwarte. |  |  |
| `binary_sensor.*_drzwi_przednie_prawe`<br>Drzwi przednie prawe | Drzwi przednie prawe są otwarte. |  |  |
| `binary_sensor.*_drzwi_tylne_lewe`<br>Drzwi tylne lewe | Drzwi tylne lewe są otwarte. |  |  |
| `binary_sensor.*_drzwi_tylne_prawe`<br>Drzwi tylne prawe | Drzwi tylne prawe są otwarte. |  |  |
| `binary_sensor.*_klimatyzacja_oczyszczanie_powietrza`<br>Klimatyzacja oczyszczanie powietrza | Oczyszczanie powietrza w kabinie jest włączone. |  |  |
| `binary_sensor.*_kolo_przednie_lewe_ostrzezenie`<br>Koło przednie lewe | Ostrzeżenie TPMS dla koła przedniego lewego (ciśnienie poza normą). |  |  |
| `binary_sensor.*_kolo_przednie_prawe_ostrzezenie`<br>Koło przednie prawe | Ostrzeżenie TPMS dla koła przedniego prawego. |  |  |
| `binary_sensor.*_kolo_tylne_lewe_ostrzezenie`<br>Koło tylne lewe | Ostrzeżenie TPMS dla koła tylnego lewego. |  |  |
| `binary_sensor.*_kolo_tylne_prawe_ostrzezenie`<br>Koło tylne prawe | Ostrzeżenie TPMS dla koła tylnego prawego. |  |  |
| `binary_sensor.*_ladowanie_kabel_podlaczony`<br>Ładowanie kabel podłączony | Kabel ładowania (AC) jest podłączony do auta. |  |  |
| `binary_sensor.*_ladowanie_plan`<br>Ładowanie plan | Ładowanie według planu z harmonogramu jest aktywne. |  | to ten sam przełącznik-plan co `switch ... ladowanie plan` |
| `binary_sensor.*_ladowanie_szybka_ladowarka`<br>Ładowanie szybka ładowarka | Podłączona jest szybka ładowarka DC. |  |  |
| `binary_sensor.*_ladowanie_trwa`<br>Ładowanie trwa | Trwa ładowanie baterii. |  |  |
| `binary_sensor.*_maska`<br>Maska | Maska jest otwarta. |  |  |
| `binary_sensor.*_niski_stan_naladowania_baterii`<br>Niski stan naładowania baterii | Niski poziom naładowania baterii — auto zgłasza ostrzeżenie. |  |  |
| `binary_sensor.*_ostrzezenie_instalacji_elektrycznej`<br>Ostrzeżenie instalacji elektrycznej | Ostrzeżenie układu elektrycznego / usterka napędu elektrycznego. |  |  |
| `binary_sensor.*_pojazd_online`<br>Pojazd online | Auto odpowiada na zapytania (nie jest w głębokim śnie). |  | off = dane mogą być nieaktualne |
| `binary_sensor.*_pojazd_silnik`<br>Pojazd silnik | Silnik spalinowy pracuje. |  |  |
| `binary_sensor.*_serwis_oleju`<br>Serwis oleju | Przyszedł termin serwisu oleju. |  |  |
| `binary_sensor.*_szyba_przednia_lewa`<br>Szyba przednia lewa | Szyba przednia lewa jest otwarta/uchylona. |  |  |
| `binary_sensor.*_szyba_przednia_prawa`<br>Szyba przednia prawa | Szyba przednia prawa jest otwarta/uchylona. |  |  |
| `binary_sensor.*_szyba_tylna_lewa`<br>Szyba tylna lewa | Szyba tylna lewa jest otwarta/uchylona. |  |  |
| `binary_sensor.*_szyba_tylna_prawa`<br>Szyba tylna prawa | Szyba tylna prawa jest otwarta/uchylona. |  |  |

## Przełączniki — sterowanie i plany (16)

Każde przełączenie wysyła komendę do auta (PIN z opcji integracji).

| Encja | Co to znaczy | Wartości | Uwagi |
|---|---|---|---|
| `switch.*_aktualizacje_automatyczne`<br>Aktualizacje automatyczne | Czy integracja ma sama odpytywać chmurę według harmonogramu (normalny/czuwanie/ładowanie). | wł. / wył. | wyłączenie = dane tylko po ręcznym odświeżeniu |
| `switch.*_kierownica_ogrzewanie`<br>Kierownica ogrzewanie | Włącza podgrzewanie kierownicy. | wł. / wył. |  |
| `switch.*_klimatyzacja_klimatyzacja_hi`<br>Klimatyzacja HI | Grzanie „wszystkiego naraz” — szyby, kierownica, fotele. | wł. / wył. | skrót producenta |
| `switch.*_klimatyzacja_lo`<br>Klimatyzacja LO | Chłodzenie/wentylacja „wszystkiego naraz”. | wł. / wył. | skrót producenta |
| `switch.*_klimatyzacja_oczyszczanie_powietrza`<br>Klimatyzacja oczyszczanie powietrza | Włącza oczyszczanie powietrza w kabinie. | wł. / wył. |  |
| `switch.*_ladowanie_plan`<br>Ładowanie plan | Włącza/wyłącza plan ładowania zapisany w aucie. | wł. / wył. | razem z `time ... godzina startu` i `number ... czas trwania` |
| `switch.*_szyba_przednia_odmrazanie`<br>Szyba przednia odmrażanie | Włącza odmrażanie przedniej szyby (nadmuch + grzanie). | wł. / wył. |  |
| `switch.*_szyba_przednia_ogrzewanie`<br>Szyba przednia ogrzewanie | Włącza grzanie przedniej szyby (elektryczne). | wł. / wył. | komenda do auta, wymaga PIN z opcji |
| `switch.*_wyjazd_plan`<br>Wyjazd plan | Główny włącznik planu wyjazdu (klimatyzacja/przygotowanie kabiny przed jazdą). | wł. / wył. | maks. 5 planów, nazwa do 10 znaków, min. 20 min odstępu |
| `switch.*_wyjazd_plan_czwartek`<br>Wyjazd plan czwartek | Plan wyjazdu aktywny w czwartek. | wł. / wył. |  |
| `switch.*_wyjazd_plan_niedziela`<br>Wyjazd plan niedziela | Plan wyjazdu aktywny w niedzielę. | wł. / wył. |  |
| `switch.*_wyjazd_plan_piatek`<br>Wyjazd plan piątek | Plan wyjazdu aktywny w piątek. | wł. / wył. |  |
| `switch.*_wyjazd_plan_poniedzialek`<br>Wyjazd plan poniedziałek | Plan wyjazdu aktywny w poniedziałek. | wł. / wył. |  |
| `switch.*_wyjazd_plan_sobota`<br>Wyjazd plan sobota | Plan wyjazdu aktywny w sobotę. | wł. / wył. |  |
| `switch.*_wyjazd_plan_sroda`<br>Wyjazd plan środa | Plan wyjazdu aktywny w środę. | wł. / wył. |  |
| `switch.*_wyjazd_plan_wtorek`<br>Wyjazd plan wtorek | Plan wyjazdu aktywny we wtorek. | wł. / wył. |  |

## Wybory — szyby, szyberdach, fotele (8)

Lista dozwolonych wartości zamiast suwaka.

| Encja | Co to znaczy | Wartości | Uwagi |
|---|---|---|---|
| `select.*_fotel_kierowcy_ogrzewanie`<br>Fotel kierowcy ogrzewanie | Podgrzewanie fotela kierowcy: wył. / słabo / średnio / mocno. | off / low / medium / high |  |
| `select.*_fotel_kierowcy_wentylacja`<br>Fotel kierowcy wentylacja | Wentylacja fotela kierowcy w 4 stopniach. | off / low / medium / high |  |
| `select.*_fotel_pasazera_ogrzewanie`<br>Fotel pasażera ogrzewanie | Podgrzewanie fotela pasażera w 4 stopniach. | off / low / medium / high |  |
| `select.*_fotel_pasazera_wentylacja`<br>Fotel pasażera wentylacja | Wentylacja fotela pasażera w 4 stopniach. | off / low / medium / high |  |
| `select.*_fotel_tylny_lewy_ogrzewanie`<br>Fotel tylny lewy ogrzewanie | Podgrzewanie tylnego lewego fotela w 4 stopniach. | off / low / medium / high |  |
| `select.*_fotel_tylny_prawy_ogrzewanie`<br>Fotel tylny prawy ogrzewanie | Podgrzewanie tylnego prawego fotela w 4 stopniach. | off / low / medium / high |  |
| `select.*_szyberdach`<br>Szyberdach pozycja | Szyberdach: zamknięty / uchylony (tilt) / otwarty. | closed / tilt / open |  |
| `select.*_szyby`<br>Szyby wszystkie | Wszystkie szyby naraz: zamknięte / uchylone / otwarte. | closed / vent / open |  |

## Klimatyzacja (1)

| Encja | Co to znaczy | Wartości | Uwagi |
|---|---|---|---|
| `climate.*_klimatyzacja`<br>Klimatyzacja | Klimatyzacja: włącz/wyłącz i temperatura zadana. |  | zakres temperatur biorą się z sensorów climate_min/max |

## Zamki (1)

| Encja | Co to znaczy | Wartości | Uwagi |
|---|---|---|---|
| `lock.*_drzwi`<br>Drzwi zamek | Zamki drzwi — zamykanie i otwieranie centralne. | zamknięte / otwarte | wymaga PIN |

## Bagażnik (1)

| Encja | Co to znaczy | Wartości | Uwagi |
|---|---|---|---|
| `cover.*_bagaznik`<br>Bagażnik | Bagażnik — otwórz/zamknij. | zamknięty / otwarty | wymaga PIN |

## Godziny planów (2)

Encje konfiguracyjne — zapisują godzinę do planu w aucie.

| Encja | Co to znaczy | Wartości | Uwagi |
|---|---|---|---|
| `time.*_ladowanie_godzina_startu`<br>Ładowanie godzina startu | Godzina rozpoczęcia planowanego ładowania (plan w aucie). |  | kategoria: konfiguracja |
| `time.*_wyjazd_godzina`<br>Wyjazd godzina | Godzina wyjazdu używana przez plan wyjazdu. |  | kategoria: konfiguracja |

## Czas trwania ładowania (1)

| Encja | Co to znaczy | Wartości | Uwagi |
|---|---|---|---|
| `number.*_ladowanie_czas_trwania`<br>Ładowanie czas trwania | Jak długo ma trwać planowane ładowanie: 1–24 h, krok 15 min (0,25 h). |  | minimum to 1 h — krótszy czas auto odrzuca |

## Przyciski — akcje jednorazowe (6)

Nie mają stanu; wywołują komendę.

| Encja | Co to znaczy | Wartości | Uwagi |
|---|---|---|---|
| `button.*_diagnostyka_odswiez_status`<br>Diagnostyka odśwież status | Wymusza pełne odświeżenie stanu auta z chmury. | akcja jednorazowa |  |
| `button.*_pojazd_wybudz`<br>Pojazd wybudź | Wybudza auto z głębokiego snu, żeby zaczęło odpowiadać. | akcja jednorazowa |  |
| `button.*_pojazd_znajdz`<br>Pojazd znajdź | Uruchamia sygnalizację lokalizującą auto (światła/klakson). | akcja jednorazowa |  |
| `button.*_pozycja_odswiez`<br>Pozycja odśwież | Odświeża pozycję GPS. | akcja jednorazowa |  |
| `button.*_pozycja_zlokalizuj`<br>Pozycja zlokalizuj | Prosi auto o podanie lokalizacji (może je wybudzić). | akcja jednorazowa |  |
| `button.*_wiadomosc_przeczytana`<br>Wiadomość przeczytana | Oznacza wiadomość jako przeczytaną (w polach usługi podaje się identyfikator wiadomości). | akcja jednorazowa |  |

## Pozycja auta (1)

| Encja | Co to znaczy | Wartości | Uwagi |
|---|---|---|---|
| `device_tracker.*_pozycja`<br>Pozycja | Pozycja GPS auta. Odświeżana przyciskiem „Pozycja odśwież”. | GPS | kategoria: diagnostyka |

## Usługi (dla automatyzacji)

Encje pokrywają stany i proste przełączenia. Rzeczy, których nie da się oddać jednym przełącznikiem, są usługami:

| Usługa | Do czego |
|---|---|
| `chery_europe.send_command` | Wyślij dowolną komendę do auta (te same identyfikatory, co w aplikacji). |
| `chery_europe.set_scheduled_charging` | Ustaw plan ładowania: włącz/wyłącz, godzina startu, czas trwania (min. 60 min). |
| `chery_europe.set_prepare_plan` | Utwórz lub zmień plan wyjazdu: nazwa (≤10 znaków), godzina, dni tygodnia, temperatura, włączony. |
| `chery_europe.cancel_prepare_plan` | Wyłącz plan wyjazdu (auto wymaga wyłączenia, nie usunięcia). |
| `chery_europe.list_prepare_plans` | Odczytaj plany wyjazdu zapisane w aucie (zwraca je w odpowiedzi usługi). |
| `chery_europe.get_messages` | Pobierz stronę historii wiadomości z lokalnej kopii (bez pytania chmury). |

## Praktyczne uwagi

- **Auto śpi.** Gdy `binary_sensor ... pojazd online` jest `off`, dane są z ostatniego udanego odczytu — dlatego `sensor ... ostatnie pobranie` bywa starsze. Przycisk „Pojazd wybudź” budzi auto na żądanie.
- **Komendy wymagają PIN-u** zapisanego w opcjach integracji (można go też podać w polach usługi).
- **Próg ładowania to 60 min** — auto odrzuca krótszy czas; encja `number ... czas trwania` ma zakres 1–24 h i krok 15 min.
- **Plan wyjazdu** to jeden plan na dobę: główny przełącznik + przełączniki dni tygodnia + godzina. Limity auta: 5 planów, nazwa do 10 znaków, minimum 20 min między wyjazdami.
- **Historia wiadomości** trzymana jest lokalnie w HA (usługa `get_messages` nie pyta chmury), więc działa też przy śpiącym aucie.
