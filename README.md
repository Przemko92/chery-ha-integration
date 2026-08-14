# Chery Europe — Home Assistant integration / Integracja z Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> 🇬🇧 English version below · 🇵🇱 Polska wersja poniżej

---

## 🇬🇧 English

### Description

`chery_europe` is a custom Home Assistant integration that connects to the
Chery Europe connected-car service and exposes vehicle data (battery, fuel,
range, tyre pressures, cabin temperature) and a small set of safe remote
commands (front windshield heating, rear window defrost, door lock/unlock,
HVAC) to Home Assistant.

The integration is implemented as a config-flow integration and uses cloud
polling. The PIN required for remote commands is **only** accepted at the
moment a command is sent — it is never stored on the entity, in the
config entry, in logs, or in diagnostics.

> **⚠️ Security warning — PIN handling**
>
> The Chery Europe remote-control PIN is sent to the cloud service together
> with each command. Treat it like a password: do not share it, do not
> hard-code it, and revoke it from the official Chery Europe app if you
> suspect it has been compromised. This integration never persists the PIN
> and does not log it.

### Features

- 9 vehicle sensors (battery, fuel, range, 4× tyre pressure, interior & exterior temperature)
- 2 safe remote switches (front windshield heating, rear window defrost)
- 1 lock entity (doors) with PIN-protected lock/unlock
- 1 climate entity (HVAC: off / heat / auto, 16–30 °C)
- 1 service (`chery_europe.send_command`) for advanced / scripted use
- Diagnostics endpoint with automatic redaction of tokens, VIN, PIN, and account data

### Requirements

- Home Assistant **2024.1.0** or newer
- A valid Chery Europe account (the same login you use in the official app)
- The vehicle's remote-control PIN (configured in the Chery Europe app)
- Internet access from your Home Assistant instance to the Chery Europe cloud

### Installation

#### HACS (recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed in your Home Assistant.
2. Add this repository as a **Custom repository** in HACS:
   - HACS → ⋮ → Custom repositories
   - Repository: `https://github.com/Przemko92/home-assistant-chery-europe`
   - Category: **Integration**
3. Install the **Chery Europe** integration from HACS.
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration → Chery Europe**.

#### Manual installation

1. Copy the `custom_components/chery_europe` directory into the
   `config/custom_components/` directory of your Home Assistant configuration.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration → Chery Europe**.

### Configuration

Configuration is done entirely through the UI (config flow).

1. **Settings → Devices & Services → Add Integration → Chery Europe**
2. Enter your Chery Europe **login** and **password**.
3. The integration will sign in, fetch your vehicles and create the device
   and entities for the first vehicle on the account.

![Configuration flow — placeholder](docs/images/config-flow.png)
> 📷 Screenshot placeholder — the configuration flow screenshot will be
> added in a future release.

### Entities

| Platform | Entity (default name)              | Description                                 |
| -------- | ---------------------------------- | ------------------------------------------- |
| sensor   | Battery level                      | High-voltage battery state of charge (%)    |
| sensor   | Fuel level                         | Fuel level (%)                              |
| sensor   | Range                              | Estimated range in km                       |
| sensor   | Front left tyre pressure           | in bar                                      |
| sensor   | Front right tyre pressure          | in bar                                      |
| sensor   | Rear left tyre pressure            | in bar                                      |
| sensor   | Rear right tyre pressure           | in bar                                      |
| sensor   | Interior temperature               | cabin temperature in °C                     |
| sensor   | Exterior temperature               | ambient temperature in °C                   |
| switch   | Front windshield heating           | safe toggle (command `ve_1103`)             |
| switch   | Rear window defrost                | safe toggle (command `ve_1135`)             |
| lock     | Doors                              | lock / unlock (command `ve_1105`)           |
| climate  | HVAC                               | off / heat / auto, 16–30 °C (command `ve_1104`) |

> Only safe commands are exposed as entities. Other remote actions
> (horn, trunk, engine start, window, sunroof, …) are **not** included in
> this MVP and can be invoked through the `chery_europe.send_command` service
> if you really need them.

### Services

#### `chery_europe.send_command`

Send a raw remote command to a vehicle. Used internally by the lock, climate
and switch entities, but also exposed for advanced users.

| Field        | Required | Description                                                       |
| ------------ | -------- | ----------------------------------------------------------------- |
| `vin`        | yes      | Target vehicle identification number                              |
| `command_id` | yes      | Chery Europe command identifier (e.g. `ve_1101` for horn)          |
| `pin`        | yes      | Remote-control PIN. Sent to the cloud, **not** stored by HA.      |
| `action`     | no       | Optional free-form action, e.g. `lock` / `unlock` / `temperature` |
| `temperature`| no       | Optional target temperature for HVAC commands                      |
| `enabled`    | no       | Optional boolean for HVAC on/off                                   |
| `hvac_mode`  | no       | Optional HVAC mode string                                         |

Example (YAML action in `automations.yaml`):

```yaml
service: chery_europe.send_command
data:
  vin: "LVVDB21B0PD123456"
  command_id: "ve_1101"
  pin: !secret chery_pin
```

### Known limitations

- **Polling only.** Data is refreshed every 15 minutes by the coordinator
  — there is no push / WebSocket channel yet.
- **One vehicle per account.** Only the first vehicle returned by the
  Chery Europe cloud is exposed. Multi-vehicle support is on the roadmap.
- **Auth strategy is reconstructed, not verified.** The SM4-ECB login
  (key `mHU80av2zFtf4OY6`), SHA-256 request signing (`SIGN_SECRET`), and
  `defaultEnv` bootstrap are derived from public Omoda/Jaecoo integrations
  that target the same Chery TSP backend. The code is structurally complete
  and unit-tested, but real-account validation against the live Chery Europe
  service is required before authentication can be declared fully functional.
- **Diagnostics are redacted.** Vehicle VIN, account login, tokens, PIN and
  location data are removed from the diagnostics download by design.
- **No fan / swing / preset modes** in the climate entity — only off,
  heat and auto, with a single target temperature (16–30 °C).

### Security & privacy

- The integration never stores or logs the PIN.
- Tokens are stored in the config-entry data and reused until the service asks for re-authentication.
- Diagnostics automatically redact tokens, VIN, PIN, login and location.
- All command traffic is over HTTPS to the Chery Europe cloud.

### Changelog

#### 0.1.0 — Initial release (MVP)

- Config-flow integration with login + password.
- 9 sensors, 2 safe switches, 1 lock, 1 climate.
- `chery_europe.send_command` service.
- Diagnostics endpoint with redaction.
- English and Polish translations.

### License

MIT — see [LICENSE](LICENSE).

---

## 🇵🇱 Polski

### Opis

`chery_europe` to niestandardowa integracja z Home Assistant, która
łączy się z usługą Chery Europe dla samochodów podłączonych i udostępnia
w Home Assistant dane pojazdu (akumulator, paliwo, zasięg, ciśnienie
opon, temperatura w kabinie) oraz niewielki zestaw bezpiecznych poleceń
zdalnych (podgrzewanie przedniej szyby, ogrzewanie tylnej szyby,
zamykanie / otwieranie drzwi, klimatyzacja).

Integracja korzysta z konfiguracji przez UI (config flow) i działa w
trybie odpytywania chmury (`cloud_polling`). PIN wymagany do poleceń
zdalnych jest przyjmowany **wyłącznie** w momencie wysłania polecenia —
nigdy nie jest zapisywany na encji, w konfiguracji, w logach ani w
diagnostyce.

> **⚠️ Ostrzeżenie bezpieczeństwa — PIN**
>
> PIN do zdalnego sterowania Chery Europe jest wysyłany do chmury
> wraz z każdym poleceniem. Traktuj go jak hasło: nie udostępniaj go,
> nie zapisuj na stałe w konfiguracji i unieważnij go w oficjalnej
> aplikacji Chery Europe, jeśli podejrzewasz, że został ujawniony.
> Integracja nigdy nie zapisuje PIN-u i nie loguje go.

### Funkcje

- 9 czujników pojazdu (akumulator, paliwo, zasięg, 4× ciśnienie opon, temperatura wewnątrz i na zewnątrz)
- 2 bezpieczne przełączniki zdalne (podgrzewanie przedniej szyby, ogrzewanie tylnej szyby)
- 1 encja zamka (drzwi) z blokowaniem/odblokowaniem chronionym PIN-em
- 1 encja klimatyzacji (HVAC: off / heat / auto, 16–30 °C)
- 1 usługa (`chery_europe.send_command`) do zaawansowanego / skryptowego użycia
- Punkt końcowy diagnostyki z automatyczną redakcją tokenów, VIN-u, PIN-u i danych konta

### Wymagania

- Home Assistant **2024.1.0** lub nowszy
- Aktywne konto Chery Europe (takie samo jak w oficjalnej aplikacji)
- PIN do zdalnego sterowania pojazdem (ustawiany w aplikacji Chery Europe)
- Dostęp do Internetu z instancji Home Assistant do chmury Chery Europe

### Instalacja

#### HACS (zalecane)

1. Upewnij się, że masz zainstalowany [HACS](https://hacs.xyz/).
2. Dodaj to repozytorium jako **Custom repository** w HACS:
   - HACS → ⋮ → Custom repositories
   - Repozytorium: `https://github.com/Przemko92/home-assistant-chery-europe`
   - Kategoria: **Integration**
3. Zainstaluj integrację **Chery Europe** z HACS.
4. Uruchom ponownie Home Assistant.
5. Przejdź do **Ustawienia → Urządzenia i usługi → Dodaj integrację → Chery Europe**.

#### Instalacja ręczna

1. Skopiuj katalog `custom_components/chery_europe` do katalogu
   `config/custom_components/` w konfiguracji Home Assistant.
2. Uruchom ponownie Home Assistant.
3. Przejdź do **Ustawienia → Urządzenia i usługi → Dodaj integrację → Chery Europe**.

### Konfiguracja

Konfiguracja odbywa się w całości przez UI (config flow).

1. **Ustawienia → Urządzenia i usługi → Dodaj integrację → Chery Europe**
2. Wprowadź swój **login** i **hasło** do Chery Europe.
3. Integracja zaloguje się, pobierze listę Twoich pojazdów i utworzy
   urządzenie oraz encje dla pierwszego pojazdu na koncie.

![Configuration flow — placeholder](docs/images/config-flow.png)
> 📷 Miejsce na zrzut ekranu — zrzut ekranu config flow zostanie
> dodany w kolejnej wersji.

### Encje

| Platforma | Encja (domyślna nazwa)            | Opis                                          |
| --------- | --------------------------------- | --------------------------------------------- |
| sensor    | Battery level                     | Stan naładowania akumulatora HV (%)           |
| sensor    | Fuel level                        | Poziom paliwa (%)                             |
| sensor    | Range                             | Szacowany zasięg w km                         |
| sensor    | Front left tyre pressure          | w barach                                      |
| sensor    | Front right tyre pressure         | w barach                                      |
| sensor    | Rear left tyre pressure           | w barach                                      |
| sensor    | Rear right tyre pressure          | w barach                                      |
| sensor    | Interior temperature              | temperatura w kabinie w °C                    |
| sensor    | Exterior temperature              | temperatura zewnętrzna w °C                  |
| switch    | Front windshield heating          | bezpieczny przełącznik (komenda `ve_1103`)    |
| switch    | Rear window defrost               | bezpieczny przełącznik (komenda `ve_1135`)    |
| lock      | Doors                             | zamykanie / otwieranie (komenda `ve_1105`)    |
| climate   | HVAC                              | off / heat / auto, 16–30 °C (komenda `ve_1104`) |

> Jako encje udostępniane są wyłącznie bezpieczne komendy. Pozostałe
> akcje zdalne (klakson, bagażnik, rozruch silnika, szyby, szyberdach …)
> **nie są** częścią tego MVP i można je w razie potrzeby wywołać
> przez usługę `chery_europe.send_command`.

### Usługi

#### `chery_europe.send_command`

Wysyła surowe polecenie zdalne do pojazdu. Używane wewnętrznie przez
encje zamka, klimatyzacji i przełączników, ale też dostępne dla
zaawansowanych użytkowników.

| Pole        | Wymagane | Opis                                                                  |
| ----------- | -------- | --------------------------------------------------------------------- |
| `vin`       | tak      | Numer VIN pojazdu docelowego                                          |
| `command_id`| tak      | Identyfikator komendy Chery Europe (np. `ve_1101` dla klaksonu)       |
| `pin`       | tak      | PIN do zdalnego sterowania. Wysyłany do chmury, **nie** zapisywany.   |
| `action`    | nie      | Opcjonalna akcja, np. `lock` / `unlock` / `temperature`               |
| `temperature`| nie     | Opcjonalna temperatura docelowa dla komend HVAC                       |
| `enabled`   | nie      | Opcjonalna wartość logiczna włączenia HVAC                            |
| `hvac_mode` | nie      | Opcjonalny tryb HVAC jako tekst                                       |

Przykład (akcja YAML w `automations.yaml`):

```yaml
service: chery_europe.send_command
data:
  vin: "LVVDB21B0PD123456"
  command_id: "ve_1101"
  pin: !secret chery_pin
```

### Znane ograniczenia

- **Tylko odpytywanie.** Dane są odświeżane co 15 minut przez koordynatora
  — brak kanału push / WebSocket.
- **Jeden pojazd na konto.** Udostępniany jest tylko pierwszy pojazd
  zwrócony przez chmurę Chery Europe. Obsługa wielu pojazdów jest
  w planach.
- **Strategia autoryzacji jest zrekonstruowana, niezweryfikowana.** Logowanie
  SM4-ECB (klucz `mHU80av2zFtf4OY6`), podpisywanie requestów SHA-256
  (`SIGN_SECRET`) oraz bootstrap `defaultEnv` pochodzą z publicznych
  integracji Omoda/Jaecoo obsługujących ten sam backend Chery TSP. Kod jest
  strukturalnie kompletny i pokryty testami jednostkowymi, ale wymagana jest
  walidacja na rzeczywistym koncie wobec działającej usługi Chery Europe,
  zanim autoryzację uzna się za w pełni funkcjonalną.
- **Diagnostyka jest redagowana.** VIN, login, tokeny, PIN i dane
  lokalizacyjne są celowo usuwane z pobranego pliku diagnostycznego.
- **Brak trybów wentylatora / nawiewu / presetów** w encji klimatyzacji —
  dostępne są tylko off, heat i auto z jedną temperaturą docelową
  (16–30 °C).

### Bezpieczeństwo i prywatność

- Integracja nigdy nie zapisuje i nie loguje PIN-u.
- Tokeny są przechowywane w danych wpisu konfiguracyjnego i używane do
  momentu, gdy usługa wymaga ponownej autoryzacji.
- Diagnostyka automatycznie redaguje tokeny, VIN, PIN, login i lokalizację.
- Cały ruch poleceń odbywa się po HTTPS do chmury Chery Europe.

### Lista zmian

#### 0.1.0 — Pierwsze wydanie (MVP)

- Integracja z config flow (login + hasło).
- 9 czujników, 2 bezpieczne przełączniki, 1 zamek, 1 klimatyzacja.
- Usługa `chery_europe.send_command`.
- Punkt diagnostyki z redakcją danych wrażliwych.
- Tłumaczenia angielskie i polskie.

### Licencja

MIT — zobacz [LICENSE](LICENSE).
