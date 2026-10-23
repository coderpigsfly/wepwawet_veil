# Changelog

Versions are year.month.release, the way Home Assistant numbers its own: 2026.10.0 is the first
release in October 2026, 2026.10.1 the next, 2026.11.0 the first in November. Before October 2026
they were 1.0.0, 1.0.1 and 1.0.2. The Wepwawet standard keeps its own version number (version 2).

## 2026.10.2

- The video plays in the README (GitHub doesn't play a video stored in the repo); the full-size
  file stays in `docs/media/`.

## 2026.10.1

- **See it work:** the README links a short video of a request through Wepwawet
  (`docs/media/littleassistant.mp4`): a tablet assistant asked about the weather, answered at home.
- The tested setup lists Oread 2026.10.0.

## 2026.10.0

The release that was planned as 1.1.0, numbered the new way.

**Add-ons.** Everything that isn't the router's own job is now an add-on in `addons/`, switched
on or off on the Add-ons page. Each one says what it serves, how long its data lives, where on the
path it works and what it may touch. It also has to pass a gate (`tools/test_addon.py`) before it
counts as one.
- On the way in: Mishearings (fixes the words you marked first), Brain fleas (small household
  facts answered at home), Time (a day another app knows, such as a feast's date), Loose language
  (fills and asks for what was said loosely), the Off-Platform Bank, Did you mean (when speech to
  text loses a word like "chore", she asks "Did you mean ...? Shall I?" before the request
  leaves the house; the word lists are yours to fill in, and each answer is recorded), and the
  Firewall (always last).
- On the way out: Persona Flair, Name Sparkle and Roman numerals. You set their order on the
  Add-ons page.

**Trainer.** Switched on for a person, it walks a request they didn't say in full through the
house's routine (a chore's name, day, time and who it's for), announcing trainer mode first, and
stays silent when it was said in full. Switched on the Trainer page or by voice ("Turn on trainer
mode for ..."), with no restart.

**Who can answer this?** A request nothing at home claimed is asked of the apps before it goes
Off-Platform: each app whose own find opens it looks it up, read only, and the one that finds it
answers. It must fit by two words (or the one word said); two apps that both find it, she asks which.
The weather brain is asked whether it's a weather question, and a brain flea that fits is offered
("Did you mean ...? Shall I?"), never answered on a guess.

**The chaining protocol.** A request is claimed by the first app or add-on whose key word it has,
integrations first. If the claimer can't answer, it names what's missing (the weather needs
*when*). The add-ons that are still free are asked to fill it, and the claimer is asked again. If
nobody can fill it, she asks you: "When is the picnic?"
- "Will it rain Easter Sunday?" asks the weather about March 28, 2027.
- When two feasts fit the words, she asks which one you mean.

**Loose language.**
- A deadline is the last possible moment ("submit tax documents by April 15"), and she offers a
  reminder before it.
- "Remind me to … on Sunday" asks whether Sunday is the reminder's day or the day it's due.
- "… not until Friday" means the reminder comes after Friday.
- A chore "for" an event offers the days before the event.
- When an answer isn't clear, she asks you to say it another way.
- With Loose language switched off, chores work as they always did.
- "Next Tuesday" is the Tuesday of the following week (weeks run Monday to Sunday, as "next
  week" does): said on a Monday or a Tuesday, it's a week on.
- A day put into her words reads naturally: "rain for the picnic tomorrow", not "on tomorrow".

**Chores.**
- Vikunja ships as the second worked example: each person's own list, a shared house list,
  briefings, reminders spoken and pushed, delete by voice (always asked first), and a time change
  ("change the time on that to 3:45 pm").
- On the Integrations page, a clean-up button brings overdue repeating chores forward to their
  next date.
- "Do I have a picnic in my chores?" answers yes with the day, or no.

**Her own echo.** When the device hears her sentence followed by yours, your words are kept. A
"yes" that opens a request keeps the thing she offered as "that". A question about her words
("What's the dog's name?" right after she said it) is a question, not her echo.

**Her confirmations.** A "thank you" to "… Right?" counts as yes; "No, thank you" stays a no.

**When the outside model is slow.** She says "My helpers outside the house are slow right now."
when the wait runs out, and keeps "I can't reach my helpers" for a connection that can't be made.
The wait is a setting (settings.yaml, integrations: litellm: timeout).

**Storage by how fast data changes.**
- Slow data (the calendar, Wikipedia's on-this-day) lives in its own SQLite file per app,
  `data/tables/<app>.db`, and is refilled every six months.
- An app's own records are read live, and only when a request involves that app.
- The weather is never stored.

**The Wepwawet standard, version 2.** An app's actions are declared and compiled into rules. Veil
writes a compliant copy for an app that has no Wepwawet section of its own.

**Security.**
- A model's device commands are judged by what they do.
- Veil Guard Service 1.2.0 checks scripts a model starts, and locks, covers and alarms fail closed.

**Faster at home.** Each sentence is diagrammed once, each app address is read once per request,
and an app's list is read only when the request needs it.

## 1.0.2

The guides were checked against the pages, and the code was read through. Fixes:
- assistant names stay inside a thing's name;
- greetings are matched as whole words;
- a door's token opens only its own door;
- the Settings allow lists are checked.

## 1.0.1

Fixes for what a fresh install ran into:
- no made-up Off-Platform address;
- apps ship switched off;
- a public .gitignore.

The Liturgical calendar and Wikipedia were added as sample apps.

## 1.0.0

The first public release.
