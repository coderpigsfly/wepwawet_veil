# Wepwawet Veil

**Private smart routing. Leaner context. Smarter handoff.**

Wepwawet is a standard first and foremost, expanding on the OpenAPI standard. The purpose of the
[Wepwawet standard](https://github.com/coderpigsfly/wepwawet_standard) is fast integration of
disparate applications, devices and IoT into one environment: an app that describes itself by the
standard, built upon OpenAPI, can be taken in for immediate communication, prioritization and AI
seeding.

Wepwawet Veil is a practical implementation of the standard as a local intent router for a home
voice assistant and IoT. It sits between end-device control software (for example Home Assistant)
and a cloud language model, and answers everything the house can answer itself (the weather,
chores, its own small talk) on your own hardware. Only what's left goes out to the cloud, and the
answer comes back through the router to the device that asked.

Wepwawet is the Egyptian jackal god whose name means "Opener of the Ways": the scout who goes ahead
and decides the road. The veil is the line between the house and the outside. Everything stays
behind it unless Wepwawet decides it must pass.

## How a request travels (the example setup)

```
voice device → Home Assistant → Wepwawet Veil (in the audio path, optional) → Oread: the words and who spoke
             → Home Assistant (its own device commands first, checked by Veil Guard Service)
             → Wepwawet Veil → answered at home, or Off-Platform (a cloud model) → back to the device
```

**See it work:** [a request through Wepwawet](docs/media/littleassistant.mp4) (16 seconds): a tablet
assistant hears its wake word and a question about the weather, and Wepwawet answers it at home.

The router poses as an OpenAI-compatible model: Home Assistant's conversation agent points at it
directly. What it can't answer at home goes Off-Platform to any OpenAI-compatible endpoint (in the
tested setup, LiteLLM rotating free-tier Gemini models). With none set, it answers at home and
politely declines the rest.

Integration by the Wepwawet standard (an expanded section of OpenAPI) connects almost any API. If you
follow the examples, you'll see that an app's own JSON or YAML that isn't Wepwawet compliant is
mapped automatically when it's added. Apps built Wepwawet compliant, like the weather brain, plug in
at once.

## What it does

- **Answers at home when it's sure.** Topics are scored from public intent datasets (MASSIVE,
  CLINC150, SNIPS), never a hand-written regex, and each topic's service answers: a weather brain,
  Vikunja or Donetick for chores. One request can use several apps: "Will it rain Easter Sunday?"
  asks the weather about the date the Liturgical calendar knows, and when the app can't answer yet
  ("rain for the picnic"), the others fill in what's missing or she asks. Follow-ups ("what about Sunday?"), the persona's own questions ("want to hear
  the rest?"), adding a chore with its extras in a short conversation.
- **Keeps junk out of the cloud.** False wakes, fragments, polite words and odd overheard speech are
  answered at home; a real question goes out.
- **Learns from you by voice.** "Who answered that?", "What did you hear?", "Record that as a
  misunderstanding": misses go to a log that's replayed after every change.
- **A personality.** Each assistant's flourishes, combed from public-domain books and chosen by you,
  on some of its answers.
- **Knows who's speaking** (with [Oread](https://github.com/coderpigsfly/oread)): the router sits in
  the Wyoming audio path in front of Oread and reads who spoke from Oread's answer, per device; the
  persona says your name now and then, only when sure.
- **A firewall by voice:** keep some people from some voice devices, home devices, commands, topics
  or the cloud, including a cloud model's attempt to work a device through Home Assistant.
- **Shows what comes in and goes out:** an activity log, and a bank of the cloud's answers
  classified by the request sentence, for review.
- **Pages to run it all** (port 8771): watch, teach (topics and their seed words, the same build and
  test tools as the command line), personality, integrations, settings, firewall and security.
- **Security like Oread's:** accounts with roles, API tokens, an encrypted vault, address allow
  lists in and out, HTTPS, an audit log.
- **Add-ons:** everything that isn't the router's own job (the Bank, brain fleas, mishearings, loose
  language, flair, names, Roman numerals, the firewall) is an add-on you switch on or off; with one
  off, the router works as it did without it.
- **Loose language:** "remind me to buy palms on Sunday" asks whether Sunday is the reminder's day or
  the day it's due; a deadline ("by April 15") offers a reminder before it.
- **Slow data kept at home:** a calendar or on-this-day list is read from its app twice a year and kept
  in its own small database, instead of a trip every hour.
- **No model or dataset written into the code:** they're all in settings.yaml and tools/sources.yaml.
- **A learning module that trains:** make an application smarter or more customized. The worked
  example uses voice identification, speech-to-text correction and text-to-speech injection.

## What you need

| | |
| --- | --- |
| **Required** | Docker; Home Assistant, or another front end that speaks the OpenAI chat format |
| **Optional** | An OpenAI-compatible model endpoint for what the house can't answer (LiteLLM in the tested setup) |
| **Optional apps** | Oread (who spoke), Vikunja or Donetick (chores), the weather brain, and any app with an OpenAPI description |

## Sample apps

Every app ships switched off; switch them on from the Integrations page.

| App | Answers | Needs |
| --- | --- | --- |
| [Liturgical Calendar API](https://litcal.johnromanodorazio.com) | "What feast is today?" | Nothing to install: it's on the internet. Permit it going out (Security page) |
| [Wikipedia](https://en.wikipedia.org/wiki/Wikipedia:On_this_day), On this day | "What happened on this day?", "Who was born today?" | Nothing to install: it's on the internet. Permit it going out |
| [The weather brain](https://github.com/coderpigsfly/weather_brain) | The weather, sunrise and sunset | Its own install |
| [Vikunja](https://vikunja.io) | Chores, each person's own list and a shared one: add, list, check off, move, change the time, delete (always asked first) | Its own install and its API key; add it on Integrations (Add an app): its voice map and rules ship ready |
| [Donetick](https://github.com/donetick/donetick) | Chores: add, list, check off, move, nag | Its own install, and its API key |
| [Oread](https://github.com/coderpigsfly/oread) | Who spoke | Its own install |

The [user's guide](docs/users-guide.md#the-sample-apps) has the steps for each.

## Tested setup

| Part | Version |
| --- | --- |
| [Home Assistant Voice PE](https://www.home-assistant.io/voice-pe/) | firmware 25.10.0 |
| A low-end EcoPad Android tablet running [Ava Pro](https://github.com/knoop7/Ava-Pro) | Android 10, Ava Pro 0.7.7 |
| [LiteLLM](https://github.com/BerriAI/litellm), the Off-Platform hop | 1.104.2, rotating Gemini 3.x flash and flash-lite models |
| [Oread](https://github.com/coderpigsfly/oread), who spoke | 2026.10.0 |
| Server | Ubuntu 24.04, Docker, a Xeon VM without AVX2 |

## Get started

```bash
mkdir -p ~/docker && cd ~/docker
git clone https://github.com/coderpigsfly/wepwawet_veil.git house-router
cd house-router
cp .env.example .env          # the Off-Platform address and key (optional), Donetick's token, FILE_OWNER
docker compose up -d --build
docker compose logs house-router | grep "setup code"
```

Then open `https://<server>:8771/`, enter the setup code and make your account. In Home Assistant,
point an assistant's conversation agent at the router as an OpenAI-compatible model: in the
integration you'd use for LiteLLM (or another OpenAI-compatible one), the address
`http://<server>:8770` and the model `house-router`. The folder and the container are named
house-router.

## More

- [User's guide](docs/users-guide.md): the routes a request takes, the pages, and adding an app.
- [Coder's guide](docs/coders-guide.md): where things live, everyday changes, testing and the keyword build.
- [The Wepwawet standard](https://github.com/coderpigsfly/wepwawet_standard), and the router's own
  notes on it in [docs/wepwawet-standard.md](docs/wepwawet-standard.md).
- Datasets and books: their licenses are in NOTICE (MASSIVE CC BY 4.0, CLINC150 CC BY 3.0, SNIPS
  CC0; books public domain).

## Versions

Versions are year.month.release, the way Home Assistant numbers its own: 2026.10.0 is the first
release in October 2026, 2026.10.1 the next. What changed in each is in [CHANGELOG.md](CHANGELOG.md).
The Wepwawet standard keeps its own version number (version 2), which changes only when apps must change.

## Example implementation acknowledgements

If you follow the example implementation, you get a smart home that can do chores (courtesy of
[Donetick](https://github.com/donetick/donetick)), tell you the Roman Catholic feast day (courtesy of
the [Liturgical Calendar API](https://litcal.johnromanodorazio.com)), this day in history (courtesy
of Wikipedia's [On this day](https://en.wikipedia.org/wiki/Wikipedia:On_this_day)), and the weather
(courtesy of the [weather brain](https://github.com/coderpigsfly/weather_brain)), and perform voice
identification, device personality, language for each identified person, and second-layer speech-to-text and
text-to-speech learning (courtesy of [Oread](https://github.com/coderpigsfly/oread)). The weather
brain and Oread are the community versions.

Donetick, the Liturgical Calendar and Wikipedia are examples of integrations that aren't Wepwawet
compliant, and are added in minutes. The weather brain and Oread are Wepwawet compliant, and are
added at once. We have no affiliation with Donetick, the Liturgical Calendar, Wikipedia or LiteLLM;
this implementation is just an example, and all are fine pieces of work.

**Note:** this implementation of the Wepwawet standard for voice control is not the FinTech
Robotics implementation or library; it is, however, the same standard that produces the priority
library for advanced robotics.

## Contributing

- **Apps:** add one through the Integrations page, and share its voice map (connectors/).
- **Devices:** tell us what you've run it with, in an issue.
- **Code and docs:** issues and pull requests are welcome.

## About this project

Built on the author's own code base, with AI-assisted extensions and clean-up.
The documentation was written with AI and proofread by a second AI, under the
author's direction and review.

## License

Apache 2.0: see `LICENSE` and `NOTICE`.
