# Chery Europe — Home Assistant integration / Integracja z Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

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

Authentication uses **email + one-time code** (the same flow as the official app).
The vehicle remote-control **PIN** is collected during setup and stored in
integration **options** so entity actions work without re-entering it each time.
The PIN is **not** written to logs or diagnostics.

### Features

**Telemetry & status**
- Battery, fuel, range, odometer, tyre pressure/temperature, charge status
- Door/window/trunk/engine/HV binary sensors
- Diagnostic vehicle metadata (nickname, model, colour, picture)
- **Restore last-known values** after a Home Assistant restart

**Remote control**
- Lock/unlock, climate (16–30 °C), front/rear glass heating
- Seat heating/ventilation, steering wheel heating
- Covers: trunk, windows, sunroof
- Charging: start/stop, scheduled charging (time + duration entities)
- Buttons: locate, find car, **wake vehicle**, **refresh position**, **refresh full status**

**Operations**
- MQTT push (live updates when the vehicle is online)
- Adaptive polling (parked / charging / HV on) with configurable intervals
- **Automatic updates** switch to enable or disable background polling
- Diagnostic sensors: command result, wake result, position probe result
- Service `chery_europe.set_scheduled_charging` (time + duration only)
- Service `chery_europe.send_command` for advanced/scripted use
- Optional **blueprint** for failed-command alerts (EN + PL)

### Requirements

- Home Assistant **2024.10.0** or newer (blueprint import)
- A Chery Europe account (same email as the official app)
- Vehicle remote-control PIN (from the official app)
- Internet access from Home Assistant to the Chery Europe cloud

### Installation

#### HACS (recommended)

1. Install [HACS](https://hacs.xyz/) in Home Assistant.
2. Add this repository as a **Custom repository**:
   - HACS → ⋮ → Custom repositories
   - Repository: `https://github.com/Przemko92/home-assistant-chery-europe`
   - Category: **Integration**
3. Install **Chery Europe** and restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Chery Europe**.

#### Manual installation

1. Copy `custom_components/chery_europe` into `config/custom_components/`.
2. Optionally copy `blueprints/automation/chery_europe/` into `config/blueprints/automation/`.
3. Restart Home Assistant and add the integration.

### First login

1. Enter the **email** registered in the Chery Europe app.
2. Receive a **one-time code** by email and enter it in Home Assistant.
3. Enter the vehicle **remote-control PIN** (used for lock, climate, charging, etc.).
4. The integration discovers your vehicle and creates all entities.

If the session expires, use **Re-authenticate** on the integration card
(**“Send me a new code”** — no code is sent until you ask).

### Options

**Settings → Devices & Services → Chery Europe → ⋮ → Options**

| Option | Default | Description |
| ------ | ------- | ----------- |
| Vehicle PIN | — | Remote-control PIN for commands |
| Parked interval | 15 min | Poll interval when parked (`0` = off) |
| Charging interval | 2 min | Poll interval while charging |
| HV interval | 1 min | Poll interval while HV/engine is on |

Also enable **Automatic updates** on the device page to allow background polling.

### Daily use

- **Do not use the official app** at the same time as the integration on the
  same account — they can disconnect each other and may require a new OTP.
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
```

#### `chery_europe.send_command`

Low-level remote command (requires `vin`, `command_id`, and `pin`).

```yaml
action: chery_europe.send_command
data:
  vin: "LVVDB21B0PD123456"
  command_id: "ve_1101"
  pin: !secret chery_pin
```

### Failed-command blueprint

Import from the repository:

- English: `blueprints/automation/chery_europe/failed_command.yaml`
- Polish: `blueprints/automation/chery_europe/komenda_nieudana.yaml`

**Settings → Automations → Create automation → From blueprint** → pick the
Chery Europe template and select the **Command result** sensor.

### Known limitations

- **One vehicle per account** — only the first vehicle from the cloud list is exposed.
- **Unofficial API** — Chery may change the backend without notice.
- **Deep sleep** — many commands and readings fail with “vehicle asleep” until the car wakes.
- **Simultaneous app use** — the official app and this integration share one session.

### Security & privacy

- PIN is stored in integration options (encrypted by Home Assistant config storage).
- Tokens, VIN, PIN, login, and GPS are redacted from diagnostics.
- All traffic uses HTTPS to the Chery Europe cloud; MQTT uses mutual TLS.

### Changelog

#### 0.2.0

- MQTT push, adaptive polling, configurable poll intervals
- Charging + scheduled charging (entities, service, blueprint)
- Comfort switches, covers, GPS device tracker, operational buttons
- Restore sensors after restart, command/wake/probe status sensors
- Email OTP login, PIN in options, diagnostics redaction

#### 0.1.0

- Initial MVP: sensors, safe switches, lock, climate, `send_command`

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

Logowanie odbywa się przez **e-mail + kod jednorazowy** (jak w aplikacji).
**PIN** do zdalnego sterowania podajesz przy konfiguracji i trafia do
**opcji integracji**, żeby encje działały bez wpisywania PIN-u przy każdej
akcji. PIN **nie** trafia do logów ani diagnostyki.

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
- Opcjonalny **blueprint** alertu o nieudanej komendzie (PL + EN)

### Wymagania

- Home Assistant **2024.10.0** lub nowszy (import blueprintu)
- Konto Chery Europe (ten sam e-mail co w aplikacji)
- PIN do zdalnego sterowania (z aplikacji)
- Dostęp do Internetu z Home Assistant do chmury Chery Europe

### Instalacja

#### HACS (zalecane)

1. Zainstaluj [HACS](https://hacs.xyz/).
2. Dodaj repozytorium jako **Custom repository**:
   - HACS → ⋮ → Custom repositories
   - Repozytorium: `https://github.com/Przemko92/home-assistant-chery-europe`
   - Kategoria: **Integration**
3. Zainstaluj **Chery Europe** i uruchom ponownie Home Assistant.
4. **Ustawienia → Urządzenia i usługi → Dodaj integrację → Chery Europe**.

#### Instalacja ręczna

1. Skopiuj `custom_components/chery_europe` do `config/custom_components/`.
2. Opcjonalnie skopiuj `blueprints/automation/chery_europe/` do `config/blueprints/automation/`.
3. Uruchom ponownie Home Assistant i dodaj integrację.

### Pierwsze logowanie

1. Wpisz **e-mail** zarejestrowany w aplikacji Chery Europe.
2. Wpisz **kod jednorazowy** z wiadomości e-mail.
3. Wpisz **PIN** do zdalnego sterowania pojazdem.
4. Integracja wykryje pojazd i utworzy encje.

Po wygaśnięciu sesji użyj **Ponownej autoryzacji** na karcie integracji
(**„Wyślij mi nowy kod”** — kod nie leci, dopóki o to nie poprosisz).

### Opcje

**Ustawienia → Urządzenia i usługi → Chery Europe → ⋮ → Opcje**

| Opcja | Domyślnie | Opis |
| ----- | --------- | ---- |
| PIN pojazdu | — | PIN do poleceń zdalnych |
| Interwał na postoju | 15 min | Odświeżanie na postoju (`0` = wył.) |
| Interwał przy ładowaniu | 2 min | Odświeżanie podczas ładowania |
| Interwał przy HV | 1 min | Odświeżanie przy włączonym HV/silniku |

Włącz też **Automatyczne aktualizacje** na stronie urządzenia, żeby polling działał w tle.

### Codzienne użytkowanie

- **Nie używaj oficjalnej aplikacji** równolegle z integracją na tym samym
  koncie — mogą się wzajemnie rozłączać i wymagać nowego OTP.
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
```

#### `chery_europe.send_command`

Niskopoziomowa komenda (wymaga `vin`, `command_id`, `pin`).

```yaml
action: chery_europe.send_command
data:
  vin: "LVVDB21B0PD123456"
  command_id: "ve_1101"
  pin: !secret chery_pin
```

### Blueprint nieudanej komendy

Import z repozytorium:

- polski: `blueprints/automation/chery_europe/komenda_nieudana.yaml`
- angielski: `blueprints/automation/chery_europe/failed_command.yaml`

**Ustawienia → Automatyzacje → Utwórz automatyzację → Z blueprintu** → wybierz
szablon Chery Europe i wskaż sensor **Wynik komendy**.

### Znane ograniczenia

- **Jeden pojazd na konto** — tylko pierwszy pojazd z listy w chmurze.
- **Nieoficjalne API** — Chery może zmienić backend bez ostrzeżenia.
- **Głęboki sen** — wiele komend i odczytów pada, dopóki auto nie obudzi.
- **Równoległa aplikacja** — oficjalna app i integracja dzielą jedną sesję.

### Bezpieczeństwo i prywatność

- PIN jest w opcjach integracji (szyfrowane przez HA).
- Tokeny, VIN, PIN, login i GPS są redagowane w diagnostyce.
- Ruch idzie po HTTPS; MQTT używa mutual TLS.

### Lista zmian

#### 0.2.0

- MQTT, adaptacyjny polling, konfigurowalne interwały
- Ładowanie + plan ładowania (encje, usługa, blueprint)
- Komfort, klapy, GPS, przyciski operacyjne
- Restore sensorów, sensory statusu komend/wybudzenia/pozycji
- Logowanie e-mail OTP, PIN w opcjach, redakcja diagnostyki

#### 0.1.0

- MVP: sensory, bezpieczne przełączniki, zamek, klimat, `send_command`

### Licencja

MIT — zobacz [LICENSE](LICENSE).
