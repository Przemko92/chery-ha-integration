# Chery Europe — Home Assistant integration

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![License][license-shield]](LICENSE)

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]

[![hacs][hacsbadge]][hacs]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Przemko92&repository=chery-ha-integration&category=integration)
[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=chery_europe)

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
- Charging power, traction battery voltage and current
- Door/window/trunk/engine/HV binary sensors
- Diagnostic vehicle metadata (nickname, model, colour, picture)
- **Restore last-known values** after a Home Assistant restart
- **Alerts** — a count plus the alert texts (tyre pressure, low traction battery, oil service, open doors/windows/trunk/sunroof)
- **Messages** — the vehicle message inbox in a single sensor: its state is the full text of the newest message (`date — title: text`) and the `history` attribute holds every earlier message as one line, oldest first, so the list grows downwards as new mail arrives. The attributes also carry `total`, `unread_count`, `latest`, `last_message` (with the full `text`, date and read flag), `last_message_text`, `history_count` and `history_truncated`. The first run imports the whole inbox (all pages, a few requests), later polls only read the newest page every 30 minutes; the full history (up to 2000 entries) is stored in `.storage` and mirrored to `config/chery_messages.json`

**Remote control**
- Lock/unlock, climate (16–30 °C), front/rear glass heating
- **Heat everything** and **Cool everything** (the app's one-shot HI / LO macros)
- Theft alarm arm/disarm
- Seat heating/ventilation, steering wheel heating
- Covers: trunk
- Selects: windows (closed / vent / open), sunroof (closed / tilt / open)
- Charging: start/stop, scheduled charging (time + duration entities)
- Scheduled **cabin/battery preparation** (departure time, repeat, temperature, battery/steering wheel/seat heating, defrost)
- **Departure time** — a configuration `time` entity for the next departure, plus a **Departure start**
  switch that arms or disarms it without touching your other plans
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

- Home Assistant **2026.5.0** or newer (see `hacs.json`)
- Blueprints require Home Assistant **2024.10.0** or newer
- A Chery Europe account (same email or phone as the official app)
- Vehicle remote-control PIN (from the official app)
- Internet access from Home Assistant to the Chery Europe cloud

### Installation

Chery Europe is in the [default HACS store](https://my.home-assistant.io/redirect/hacs_repository/?owner=Przemko92&repository=chery-ha-integration&category=integration).

#### HACS (recommended)

1. Install [HACS](https://hacs.xyz/) in Home Assistant.
2. Open **HACS → Integrations**, search for **Chery Europe**, and download it.
   The button at the top of this page opens the same repository in HACS.
3. Restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Chery Europe**
   (or use the **Open integration** button at the top).

If you added `https://github.com/Przemko92/chery-ha-integration` earlier as a
**custom repository**, remove that entry (**HACS → ⋮ → Custom repositories**).
The installed copy stays; HACS then tracks the default listing.

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
5. The integration discovers your vehicles. If the account has more than one,
   choose which ones to add. They share this login. A single vehicle is added
   automatically.
6. The integration creates entities for every selected vehicle.

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
| Vehicles | all found | Shown when the account has more than one vehicle |

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

#### `chery_europe.set_prepare_plan`

Create or update a scheduled **cabin/battery preparation** plan — the same
feature as *Zaplanowane wstępne przygotowanie kabiny* in the official app. The
car pre-conditions the cabin (and optionally the traction battery) so it is
ready at your departure time.

```yaml
action: chery_europe.set_prepare_plan
data:
  plan_name: "Work"          # max 10 characters, must be unique
  travel_time: "07:30"       # departure time, HH:MM
  repeat: workdays           # daily | workdays | weekend | custom
  # days: [1, 2, 3, 4, 5]    # only for repeat: custom (1 = Monday)
  temperature: 22            # optional, 16–32 °C
  battery_heat: true         # optional; pre-heat the HV battery
  steering_wheel_heat: true  # optional
  driver_seat_heat: false    # optional
  front_defrost: true        # optional
  rear_defrost: false        # optional
```

Add `plan_id: "<id>"` to edit an existing plan instead of creating a new one.
The car accepts **at most 5 plans**, names of **10 characters**, and departures
**at least 20 minutes apart**; the service rejects anything else before talking
to the car.

Add `dry_run: true` to only build and return the payload:

```yaml
action: chery_europe.set_prepare_plan
data:
  plan_name: "Test"
  travel_time: "06:45"
  battery_heat: true
  dry_run: true
response_variable: preview
# {{ preview.body.preparePlans }}
```

#### `chery_europe.cancel_prepare_plan`

Switch a plan off. The car insists a plan is **deactivated before it can be
deleted**, so the integration clears `enabled` and every heating flag instead of
removing the entry.

```yaml
action: chery_europe.cancel_prepare_plan
data:
  plan_id: "1234567890"
```

#### `chery_europe.list_prepare_plans`

Read the plans stored in the car and return them (single query, no full
refresh):

```yaml
action: chery_europe.list_prepare_plans
response_variable: plans
# {{ plans.plans }}, {{ plans.next_departure }}
```

The same data is exposed as two read-only sensors: **Scheduled preparation**
(enabled plan count, full plan list in the attributes) and **Next departure**.
Plans are re-read at most once an hour, so a short polling interval does not
multiply the requests sent to your account.

#### Departure time and departure switch

Two entities drive the plan the integration manages itself, so a daily
departure needs no service call:

- **Departure time** (`time`, configuration, `time.godzina_wyjazdu`) — reads the
  time of the plan named `Wyjazd`, or the default `07:30` when that plan does not
  exist yet.
- **Departure start** (`switch`, `switch.wyjazd_start`) — `on` while the plan is
  armed, `off` when it is deactivated.

Changing the time only keeps a local draft until the switch is turned on; that
is deliberate, because a `time` value has to exist before a plan can be created.
Turning the switch on sends the plan to the car, turning it off clears the
`enabled` flag (the car will not let an armed plan be deleted). Both actions send
the whole plan list, so your other plans are preserved, and a departure closer
than 20 minutes to another plan is rejected with a message instead of being
written.

#### `chery_europe.get_messages`

Return a page of the stored message history. It only reads the local copy — no
request is sent to the Chery cloud, so it is safe in automations and templates:

```yaml
action: chery_europe.get_messages
data:
  page: 1
  page_size: 20
  unread_only: false
response_variable: inbox
# {{ inbox.total }}, {{ inbox.pages }}, {{ inbox.messages }}
```

Everything lives in one entity: **Messages** shows the newest message as its state
and keeps the growing list in the `history` attribute — oldest line first, newest
last, capped (200 lines / 9000 characters) so the payload stays inside the recorder
limit — while the whole history lives in `config/chery_messages.json` (keyed by VIN)
and in the integration `.storage` file. The `messages` attribute keeps the last 10
entries as structured dicts for templates.

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

- **Existing installs** that were added before vehicle selection keep monitoring
  the first vehicle on the account. Open **Options** when more than one vehicle
  is available, or remove the integration and add it again, to choose.
- **Unofficial API** — Chery may change the backend without notice.
- **Deep sleep** — many commands and readings fail with “vehicle asleep” until the car wakes.
- **Simultaneous app use** — one session per account: HA login signs out the
  official app. Use a separate account with shared vehicle access if you need both.

### Security & privacy

- PIN is stored in integration options (encrypted by Home Assistant config storage).
- Tokens, VIN, PIN, login, phone number, area code, vehicle nickname, and GPS are redacted from diagnostics.
- All traffic uses HTTPS to the Chery Europe cloud. MQTT uses mutual TLS and checks the broker hostname.

### License

MIT — see [LICENSE](LICENSE). Portions ported from the Omoda/Jaecoo integration keep that project's copyright; see [NOTICE](NOTICE).

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
- Moc ładowania, napięcie i prąd baterii trakcyjnej
- Binary sensory: drzwi, okna, silnik, HV itd.
- Metadane diagnostyczne pojazdu (nick, model, kolor, zdjęcie)
- **Przywracanie ostatnich wartości** po restarcie Home Assistant
- **Alarmy** — licznik i treść aktywnych alarmów (ciśnienie w oponach, niski poziom baterii trakcyjnej, serwis oleju, otwarte drzwi/okna/klapa bagażnika/szyberdach)
- **Wiadomości** — skrzynka wiadomości z serwisu w jednym sensorze: stan to pełna treść najnowszej wiadomości (`data — tytuł: tekst`), a atrybut `history` trzyma wszystkie wcześniejsze wiadomości po jednej linii, **od najstarszej**, więc lista rośnie w dół wraz z nową pocztą. Atrybuty zawierają też `total`, `unread_count`, `latest`, `last_message` (z pełnym `text`, datą i flagą przeczytania), `last_message_text`, `history_count` i `history_truncated`. Pierwsze uruchomienie pobiera całą skrzynkę (wszystkie strony, kilka zapytań), później odczytywana jest tylko najnowsza strona co 30 minut; pełna historia (do 2000 wpisów) leży w `.storage` i w kopii `config/chery_messages.json`

**Sterowanie zdalne**
- Zamek, klimatyzacja (16–30 °C), ogrzewanie szyb
- **Grzej wszystko** i **Chłodź wszystko** (makra HI / LO z aplikacji)
- Uzbrajanie i rozbrajanie alarmu antykradzieżowego
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

- Home Assistant **2026.5.0** lub nowszy (patrz `hacs.json`)
- Blueprinty wymagają Home Assistant **2024.10.0** lub nowszego
- Konto Chery Europe (ten sam e-mail lub telefon co w aplikacji)
- PIN do zdalnego sterowania (z aplikacji)
- Dostęp do Internetu z Home Assistant do chmury Chery Europe

### Instalacja

Chery Europe jest w [domyślnym sklepie HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=Przemko92&repository=chery-ha-integration&category=integration).

#### HACS (zalecane)

1. Zainstaluj [HACS](https://hacs.xyz/).
2. Otwórz **HACS → Integracje**, wyszukaj **Chery Europe** i pobierz integrację.
   Przycisk na górze tej strony otwiera to samo repozytorium w HACS.
3. Uruchom ponownie Home Assistant.
4. **Ustawienia → Urządzenia i usługi → Dodaj integrację → Chery Europe**
   (albo przycisk **Open integration** na górze strony).

Jeśli wcześniej dodałeś `https://github.com/Przemko92/chery-ha-integration` jako
**custom repository**, usuń ten wpis (**HACS → ⋮ → Custom repositories**).
Zainstalowana kopia zostaje; HACS przechodzi wtedy na wpis z domyślnego sklepu.

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
5. Integracja wykryje pojazdy. Jeśli konto ma więcej niż jedno auto, wybierz,
   które dodać. Korzystają z tego samego logowania. Jedno auto dodaje się samo.
6. Integracja utworzy encje dla każdego wybranego pojazdu.

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
| Pojazdy | wszystkie znalezione | Widoczne, gdy konto ma więcej niż jeden pojazd |

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

#### `chery_europe.get_messages`

Zwraca stronę zapisanej historii wiadomości. Czyta tylko lokalną kopię — żadne
zapytanie nie leci do chmury Chery, więc można jej używać w automatyzacjach:

```yaml
action: chery_europe.get_messages
data:
  page: 1
  page_size: 20
  unread_only: false
response_variable: inbox
# {{ inbox.total }}, {{ inbox.pages }}, {{ inbox.messages }}
```

Najnowsze wiadomości są pierwsze. Encje celowo pozostają małe: **Wiadomości**
niosą liczniki i ostatnie 20 wpisów, **Wiadomości – treść** pokazuje najnowszą
wiadomość jako stan i trzyma narastającą listę w atrybucie `history` (najnowsze
pierwsze, przycinana do limitu recordera), a cała historia leży
w `config/chery_messages.json` (klucz: VIN) oraz w pliku `.storage` integracji.

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

- **Istniejące instalacje** sprzed wyboru pojazdów nadal śledzą pierwsze auto
  na koncie. Gdy aut jest więcej, wybór jest w **Opcjach**, albo po usunięciu
  i ponownym dodaniu integracji.
- **Nieoficjalne API** — Chery może zmienić backend bez ostrzeżenia.
- **Głęboki sen** — wiele komend i odczytów pada, dopóki auto nie obudzi.
- **Równoległa aplikacja** — jedna sesja na konto: logowanie w HA wyloguje
  oficjalną app. Jeśli potrzebujesz obu, użyj osobnego konta z udostępnionym dostępem.

### Bezpieczeństwo i prywatność

- PIN jest w opcjach integracji (szyfrowane przez HA).
- Tokeny, VIN, PIN, login, numer telefonu, numer kierunkowy, nazwa pojazdu i GPS są redagowane w diagnostyce.
- Ruch idzie po HTTPS. MQTT używa mutual TLS i sprawdza nazwę hosta brokera.

### Licencja

MIT — zobacz [LICENSE](LICENSE). Fragmenty przeniesione z integracji Omoda/Jaecoo zachowują copyright tamtego projektu; zobacz [NOTICE](NOTICE).

[buymecoffee]: https://www.buymeacoffee.com/przemko92
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge

[maintainer]: https://github.com/Przemko92
[maintainer-shield]: https://img.shields.io/badge/maintainer-%40Przemko92-blue.svg?style=for-the-badge

[commits]: https://github.com/Przemko92/chery-ha-integration/commits/main
[commits-shield]: https://img.shields.io/github/commit-activity/y/Przemko92/chery-ha-integration.svg?style=for-the-badge

[hacs]: https://github.com/custom-components/hacs
[hacsbadge]: https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge


[releases]: https://github.com/Przemko92/chery-ha-integration/releases
[releases-shield]: https://img.shields.io/github/release/Przemko92/chery-ha-integration.svg?style=for-the-badge

[license-shield]: https://img.shields.io/github/license/Przemko92/chery-ha-integration.svg?style=for-the-badge
