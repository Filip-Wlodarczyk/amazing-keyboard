# Amazing Keyboard (amkb)

Podpowiedzi AI w **każdym polu tekstowym** Ubuntu: piszesz, a za kursorem pojawia się
przewidywane dokończenie. **Tab** je wstawia, **Ctrl+→** wstawia jedno słowo, **Esc** chowa.

Działa jako silnik wprowadzania IBus, więc obejmuje aplikacje GTK/Qt, przeglądarki, Electron,
terminal itd. – wszystko, co obsługuje metody wprowadzania (na GNOME/Wayland prawie wszystko).

## Instalacja

```bash
chmod +x install.sh uninstall.sh
./install.sh
```

Instalator poprosi o hasło sudo tylko po to, by skopiować `amkb.xml` do `/usr/share/ibus/component`
(IBus nie wczytuje silników z katalogu domowego).

## Konfiguracja z terminala

```bash
amkb config -p openai -k sk-...          # dostawca + klucz
amkb config -p anthropic                 # klucz wpiszesz niewidocznie (nie trafi do historii basha)
amkb config -p gemini -m gemini-2.5-flash
amkb config -p ollama -m llama3.2        # lokalnie, bez klucza
amkb config -p custom --base-url http://localhost:8080/v1 -m mój-model
amkb setup                               # albo interaktywny kreator
```

Następnie:

```bash
amkb test "Dzień dobry, chciałbym"       # podgląd podpowiedzi w terminalu
amkb activate                            # dodaje „Amazing Keyboard (AI)” do źródeł wprowadzania
```

Przełączanie między zwykłą klawiaturą a AI: **Super+Spacja**.

## Pozostałe komendy

| Komenda | Opis |
|---|---|
| `amkb providers` | lista dostawców i domyślnych modeli |
| `amkb status` | konfiguracja, stan silnika |
| `amkb on` / `amkb off` | włącz/wyłącz podpowiedzi bez zmiany źródła |
| `amkb config --debounce-ms 300 --max-words 5` | szybkość i długość podpowiedzi |
| `amkb config --display popup` | podpowiedź w okienku przy kursorze zamiast w tekście |
| `amkb log` | log silnika (`~/.cache/amkb/engine.log`) |
| `amkb deactivate` | usuń ze źródeł wprowadzania |

Zmiany konfiguracji działają od razu – silnik przeładowuje `~/.config/amkb/config.json` sam.

## Dostawcy

`openai`, `anthropic`, `gemini`, `groq`, `openrouter`, `mistral`, `deepseek`, `ollama`,
`custom` (dowolne API zgodne z OpenAI) i `mock` (test bez sieci).

Dla `anthropic` domyślny model to `claude-opus-5-5`. Do autouzupełniania szybszy i dużo tańszy
jest `claude-haiku-5-5`: `amkb config -p anthropic -m claude-haiku-5-5`.

## Prywatność

- Tekst przed kursorem (do 1500 znaków) jest wysyłany do wybranego dostawcy.
- Pola haseł i PIN-ów są pomijane (aplikacja musi je oznaczać – większość to robi).
- Klucz API leży w `~/.config/amkb/config.json` z uprawnieniami `600`.
- Treść pisanego tekstu trafia do logu tylko przy `amkb config --debug on`.

## Ograniczenia

- **Kolor szary**: silnik prosi o szary kolor, ale na GNOME/Wayland protokół wprowadzania
  nie przekazuje kolorów – wtedy podpowiedź jest wyświetlana stylem aplikacji (zwykle podkreślona).
  Jeśli wolisz wyraźnie odróżnioną podpowiedź: `amkb config --display popup`.
- Podpowiedź pokazuje się tylko na końcu linii (gdy za kursorem nic nie ma).
- W terminalu Tab bez widocznej podpowiedzi działa normalnie (uzupełnianie basha).

## Odinstalowanie

```bash
./uninstall.sh
```
