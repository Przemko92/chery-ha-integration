# Chery Europe — Home Assistant integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License][license-shield]](LICENSE)

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]

[![hacs][hacsbadge]][hacs]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

> 🇬🇧 English version below · 🇵🇱 Polska wersja poniżej

---

## 🇬🇧 English

### Disclaimer

> **⚠️ UNOFFICIAL software.** This project is **not affiliated with, endorsed by,
> or connected to Chery**, Chery Europe, Chery International, or any of their
> subsidiaries. It is an independent, community-driven integration built by
> reverse-engineering the same connected-car API used by the official mobile app.
> Provided **“as is”** — use at your own risk and only on **your own vehicle**.

### Description

`chery_europe` is a custom Home Assistant integration for Chery Europe
connected vehicles (e.g. Tiggo 9 PHEV). It exposes live telemetry, remote
commands, charging, GPS, and comfort features as Home Assistant entities.

Authentication uses **email + one-time code** (recommended; same flow as the
official app). Accounts registered with a **phone number** can sign in via SMS
instead. The vehicle remote-control **PIN** is collected during setup and stored
in integration **options**. By default entity actions omit the PIN and use the
stored value. Enable **Ask for PIN** (setup or Options) to require entering a PIN
that matches the stored value on each action. The PIN is **not** written to logs
or diagnostics.

### Features

**Telemetry & status**
- Battery, fuel, range, odometer, tyre pressure/temperature, charge status
- Door/window/trunk/engine/HV binary sensors
- Diagnostic vehicle metadata (nickname, model, colour, picture)
- **Restore last-known values** after a Home Assistant restart

**Remote control**
- Lock/unlock, climate (16–30 °C), front/rear glass heating
- Seat heating/ventilation, steering wheel heating
- Covers: trunk, windows
- Selects: sunroof (closed / tilt / open)
- Charging: start/stop, scheduled charging (time + duration entities)
- Buttons: locate, find car, **wake vehicle**, **refresh position**, **refresh full status**

**Operations**
- MQTT push (live updates when the vehicle is online)
- Adaptive polling (parked / charging / HV on) with configurable intervals
- **Automatic updates** switch to enable or disable background polling
- Diagnostic sensors: command result, wake result, position probe result
- Service `chery_europe.set_scheduled_charging` (time + duration only)
- Service `chery_europe.send_command` for advanced/scripted use
- Optional **blueprints** for failed- and successful-command alerts

### Requirements

- Home Assistant **2026.5.4** or newer (see `hacs.json`)
- Blueprints require Home Assistant **2024.10.0** or newer
- A Chery Europe account (same email or phone as the official app)
- Vehicle remote-control PIN (from the official app)
- Internet access from Home Assistant to the Chery Europe cloud

### Installation

#### HACS (recommended)

1. Install [HACS](https://hacs.xyz/) in Home Assistant.
2. Add this repository as a **Custom repository**:
   - HACS → ⋮ → Custom repositories
   - Repository: `https://github.com/Przemko92/chery-ha-integration`
   - Category: **Integration**
3. Install **Chery Europe** and restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Chery Europe**.

#### Manual installation

1. Copy `custom_components/chery_europe` into `config/custom_components/`.
2. Restart Home Assistant and add the integration.

### First login

> **⚠️ Logging in here signs out the official mobile app** on the same account
> (one active session). Prefer a **separate account with shared vehicle access**
> for Home Assistant, and keep your main account for the phone app.

1. Choose **email (recommended)** or **phone (SMS)** if the account has no email.
2. Enter the **email** or **phone + country code** registered in the Chery Europe app.
3. Receive a **one-time code** (email or SMS) and enter it in Home Assistant.
4. Enter the vehicle **remote-control PIN** twice to confirm (always stored).
   Optionally enable **Ask for PIN** to require matching confirmation on each action.
5. The integration discovers your vehicle and creates all entities.

If the session expires, use **Re-authenticate** on the integration card
(**“Send me a new code”** — no code is sent until you ask).

### Options

**Settings → Devices & Services → Chery Europe → ⋮ → Options**

| Option | Default | Description |
| ------ | ------- | ----------- |
| Vehicle PIN | — | Stored remote-control PIN (leave empty to clear) |
| Ask for PIN | off | Require entering the PIN on each action |
| Parked interval | 15 min | Poll interval when parked (`0` = off) |
| Charging interval | 2 min | Poll interval while charging |
| HV interval | 1 min | Poll interval while HV/engine is on |

Also enable **Automatic updates** on the device page to allow background polling.

### Daily use

- **Do not use the official app** on the same account as the integration —
  logging into Home Assistant **signs out the mobile app**, and using the app
  can disconnect the integration (new OTP may be needed). Prefer a **second
  account with shared access** for Home Assistant.
- Many values show `unknown` while the car is in **deep sleep**; restored
  values appear after a Home Assistant restart until fresh data arrives.
- Battery and odometer refresh reliably when the car is **driving or charging**.
  For an immediate reading while parked, use **Refresh full status** (briefly
  wakes HV via climate).
- Map position lives on the **device_tracker**, not on the Locate button
  (the button only records when it was pressed).

### Services

#### `chery_europe.set_scheduled_charging`

Set or update the charging schedule. Uses the PIN from integration options.

```yaml
action: chery_europe.set_scheduled_charging
data:
  start_time: "23:00:00"
  duration_hours: 6
  enabled: true  # optional; false disables the schedule
```

#### `chery_europe.send_command`

Low-level remote command (requires `vin` and `command_id`; `pin` is optional when
a PIN is stored in integration options).

```yaml
action: chery_europe.send_command
data:
  vin: "LVVDB21B0PD123456"
  command_id: "ve_1101"
  # pin: !secret chery_pin  # only needed if PIN is not stored in options
```

### Command result blueprints

The integration ships two blueprints under
`custom_components/chery_europe/blueprints/automation/`:

- `failed_command.yaml` — alert when a remote command fails
- `success_command.yaml` — alert when a remote command succeeds

After installing or updating the integration, restart Home Assistant.

**Settings → Automations → Create automation → From blueprint** → pick a
Chery Europe template and select the **Command result** sensor.

### Known limitations

- **One vehicle per account** — only the first vehicle from the cloud list is exposed.
- **Unofficial API** — Chery may change the backend without notice.
- **Deep sleep** — many commands and readings fail with “vehicle asleep” until the car wakes.
- **Simultaneous app use** — one session per account: HA login signs out the
  official app. Use a separate account with shared vehicle access if you need both.

### Security & privacy

- PIN is stored in integration options (encrypted by Home Assistant config storage).
- Tokens, VIN, PIN, login, and GPS are redacted from diagnostics.
- All traffic uses HTTPS to the Chery Europe cloud; MQTT uses mutual TLS.

### License

MIT — see [LICENSE](LICENSE).

---

## 🇵🇱 Polski

### Zastrzeżenie

> **⚠️ Oprogramowanie NIEOFICJALNE.** Ten projekt **nie jest powiązany,
> wspierany ani powiązany organizacyjnie z Chery**, Chery Europe, Chery
> International ani żadnym z ich podmiotów. To niezależna integracja społeczności, zbudowana przez reverse engineering tego samego API co oficjalna
> aplikacja mobilna. Dostarczana **„tak jak jest”** — używasz na własną
> odpowiedzialność i **wyłącznie na swoim pojeździe**.

### Opis

`chery_europe` to niestandardowa integracja Home Assistant dla pojazdów
Chery Europe (np. Tiggo 9 PHEV). Udostępnia telemetrię na żywo, polecenia
zdalne, ładowanie, GPS i funkcje komfortu jako encje Home Assistant.

Logowanie odbywa się przez **e-mail + kod jednorazowy** (zalecane; jak w
aplikacji). Konta zarejestrowane na **numer telefonu** mogą użyć logowania SMS.
**PIN** do zdalnego sterowania podajesz przy konfiguracji i jest zawsze
zapisywany w **opcjach integracji**. Domyślnie akcje encji pomijają PIN i
używają zapisanej wartości. Włącz **Pytaj o PIN** (przy setupie lub w Opcjach),
żeby przy każdej akcji wymagać PIN-u zgodnego z zapisanym.
PIN **nie** trafia do logów ani diagnostyki.

### Funkcje

**Telemetria i status**
- Bateria, paliwo, zasięg, przebieg, ciśnienie/temperatura opon, stan ładowania
- Binary sensory: drzwi, okna, silnik, HV itd.
- Metadane diagnostyczne pojazdu (nick, model, kolor, zdjęcie)
- **Przywracanie ostatnich wartości** po restarcie Home Assistant

**Sterowanie zdalne**
- Zamek, klimatyzacja (16–30 °C), ogrzewanie szyb
- Ogrzewanie/wentylacja foteli, ogrzewanie kierownicy
- Klapy: bagażnik, szyby, szyberdach
- Ładowanie: start/stop, ładowanie zaplanowane (encje czasu i czasu trwania)
- Przyciski: lokalizuj, znajdź auto, **wybudź auto**, **odśwież pozycję**, **odśwież pełny status**

**Operacje**
- Push MQTT (aktualizacje na żywo, gdy auto jest online)
- Adaptacyjny polling (postój / ładowanie / HV) z konfigurowalnymi interwałami
- Przełącznik **Automatyczne aktualizacje**
- Sensory diagnostyczne: wynik komendy, wybudzenia, odczytu pozycji
- Usługa `chery_europe.set_scheduled_charging` (tylko godzina i czas trwania)
- Usługa `chery_europe.send_command` do zaawansowanego użycia
- Opcjonalne **blueprinty** alertu o nieudanej i udanej komendzie

### Wymagania

- Home Assistant **2026.5.4** lub nowszy (patrz `hacs.json`)
- Blueprinty wymagają Home Assistant **2024.10.0** lub nowszego
- Konto Chery Europe (ten sam e-mail lub telefon co w aplikacji)
- PIN do zdalnego sterowania (z aplikacji)
- Dostęp do Internetu z Home Assistant do chmury Chery Europe

### Instalacja

#### HACS (zalecane)

1. Zainstaluj [HACS](https://hacs.xyz/).
2. Dodaj repozytorium jako **Custom repository**:
   - HACS → ⋮ → Custom repositories
   - Repozytorium: `https://github.com/Przemko92/chery-ha-integration`
   - Kategoria: **Integration**
3. Zainstaluj **Chery Europe** i uruchom ponownie Home Assistant.
4. **Ustawienia → Urządzenia i usługi → Dodaj integrację → Chery Europe**.

#### Instalacja ręczna

1. Skopiuj `custom_components/chery_europe` do `config/custom_components/`.
2. Uruchom ponownie Home Assistant i dodaj integrację.

### Pierwsze logowanie

> **⚠️ Logowanie tutaj wyloguje oficjalną aplikację mobilną** na tym samym
> koncie (jedna aktywna sesja). Zalecane jest **osobne konto z udostępnionym
> dostępem** do pojazdu dla Home Assistant, a główne konto zostaw pod telefon.

1. Wybierz **e-mail (zalecane)** albo **telefon (SMS)**, jeśli konto nie ma e-maila.
2. Podaj **e-mail** albo **numer + kierunkowy** z aplikacji Chery Europe.
3. Wpisz **kod jednorazowy** z e-maila lub SMS-a.
4. Wpisz **PIN** do zdalnego sterowania dwa razy (zawsze zapisywany). Opcjonalnie
   włącz **Pytaj o PIN**, żeby przy każdej akcji wymagać PIN-u zgodnego z zapisanym.
5. Integracja wykryje pojazd i utworzy encje.

Po wygaśnięciu sesji użyj **Ponownej autoryzacji** na karcie integracji
(**„Wyślij mi nowy kod”** — kod nie leci, dopóki o to nie poprosisz).

### Opcje

**Ustawienia → Urządzenia i usługi → Chery Europe → ⋮ → Opcje**

| Opcja | Domyślnie | Opis |
| ----- | --------- | ---- |
| PIN pojazdu | — | Zapisany PIN do poleceń (pusty = wyczyść) |
| Pytaj o PIN | wył. | Wymagaj PIN-u przy każdej akcji |
| Interwał na postoju | 15 min | Odświeżanie na postoju (`0` = wył.) |
| Interwał przy ładowaniu | 2 min | Odświeżanie podczas ładowania |
| Interwał przy HV | 1 min | Odświeżanie przy włączonym HV/silniku |

Włącz też **Automatyczne aktualizacje** na stronie urządzenia, żeby polling działał w tle.

### Codzienne użytkowanie

- **Nie używaj oficjalnej aplikacji** na tym samym koncie co integracja —
  logowanie do Home Assistant **wyloguje aplikację mobilną**, a użycie appki
  może rozłączyć integrację (może być potrzebny nowy OTP). Zalecane jest
  **drugie konto z udostępnionym dostępem** pod Home Assistant.
- Wiele wartości to `unknown`, gdy auto **śpi głęboko**; po restarcie HA
  widać ostatnie znane wartości do czasu świeżych danych.
- Bateria i przebieg odświeżają się wiarygodnie w **jeździe lub przy ładowaniu**.
  Na postoju użyj **Odśwież pełny status** (krótko budzi HV przez klimat).
- Pozycja na mapie jest na **device_tracker**, nie na przycisku Zlokalizuj
  (przycisk pokazuje tylko czas ostatniego naciśnięcia).

### Usługi

#### `chery_europe.set_scheduled_charging`

Ustawia plan ładowania. PIN bierze z opcji integracji.

```yaml
action: chery_europe.set_scheduled_charging
data:
  start_time: "23:00:00"
  duration_hours: 6
  enabled: true  # opcjonalnie; false wyłącza plan
```

#### `chery_europe.send_command`

Niskopoziomowa komenda (wymaga `vin` i `command_id`; `pin` opcjonalny, gdy
PIN jest zapisany w opcjach integracji).

```yaml
action: chery_europe.send_command
data:
  vin: "LVVDB21B0PD123456"
  command_id: "ve_1101"
  # pin: !secret chery_pin  # tylko gdy PIN nie jest zapisany w opcjach
```

### Blueprinty wyniku komendy

Integracja dołącza dwa blueprinty w
`custom_components/chery_europe/blueprints/automation/`:

- `failed_command.yaml` — alert przy nieudanej komendzie
- `success_command.yaml` — alert przy udanej komendzie

Po instalacji lub aktualizacji uruchom ponownie Home Assistant.

**Ustawienia → Automatyzacje → Utwórz automatyzację → Z blueprintu** → wybierz
szablon Chery Europe i wskaż sensor **Wynik komendy**.

### Znane ograniczenia

- **Jeden pojazd na konto** — tylko pierwszy pojazd z listy w chmurze.
- **Nieoficjalne API** — Chery może zmienić backend bez ostrzeżenia.
- **Głęboki sen** — wiele komend i odczytów pada, dopóki auto nie obudzi.
- **Równoległa aplikacja** — jedna sesja na konto: logowanie w HA wyloguje
  oficjalną app. Jeśli potrzebujesz obu, użyj osobnego konta z udostępnionym dostępem.

### Bezpieczeństwo i prywatność

- PIN jest w opcjach integracji (szyfrowane przez HA).
- Tokeny, VIN, PIN, login i GPS są redagowane w diagnostyce.
- Ruch idzie po HTTPS; MQTT używa mutual TLS.

### Licencja

MIT — zobacz [LICENSE](LICENSE).

[buymecoffee]: https://www.buymeacoffee.com/przemko92
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge

[maintainer]: https://github.com/Przemko92
[maintainer-shield]: https://img.shields.io/badge/maintainer-%40Przemko92-blue.svg?style=for-the-badge

[commits]: https://github.com/Przemko92/chery-ha-integration/commits/main
[commits-shield]: https://img.shields.io/github/commit-activity/y/Przemko92/chery-ha-integration.svg?style=for-the-badge

[hacs]: https://github.com/custom-components/hacs
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge


[releases]: https://github.com/Przemko92/chery-ha-integration/releases
[releases-shield]: https://img.shields.io/github/release/Przemko92/chery-ha-integration.svg?style=for-the-badge

[license-shield]: https://img.shields.io/github/license/Przemko92/chery-ha-integration.svg?style=for-the-badge
