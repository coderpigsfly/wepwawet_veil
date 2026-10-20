# The Wepwawet standard: now in its own repo

The standard (*What an app's API needs so it can be used by voice*) moved out of the router on
Oct 20, 2026, so there is one copy:

- **Public:** https://github.com/coderpigsfly/wepwawet_standard (wepwawet-standard.md, CC BY 4.0)
- **Development:** ~/docker/wepwawet (dev_wepwawet_standard): changes to the standard are made
  there and released with its tools/release.py

The router follows it; the public copy names no apps (a chore app, a speech app). What's the
router's own, kept here:

- **Expectation 12** (an app gets the house's people from the voice system): Wepwawet Veil keeps
  the people grid and answers `GET /people/<app>` on the chat door, through a door whose program is
  that app (the oread door covers /people/oread in the starting copy); no such door, 403.
- **The chore app in the examples** (expectations 2, 5 to 10, 13) is Donetick; the speech app is
  Oread. Apps without the section (Donetick, Mealie) work with every tab open; Donetick's
  shortfalls are in the user's guide, Appendix A.
- **What the router does with the section:** docs/coders-guide.md, "The Wepwawet standard".
