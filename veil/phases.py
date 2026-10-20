# veil/phases.py - developer flags for a staged build (the phased-build rule: "if pigs == fly"). Each
# phase's new code runs only while its flag is on; the old path stays in the else. Hard-coded on
# purpose, for the developers only, not a setting: tier 1 (the automated tests) runs with each flag on
# and off, tier 2 (by voice) tries them; a refactor pulls them out once tier 2 is done.

PHASES = {
    "dump1": True,   # Oct 19: a command's address from the date said, each part as the app writes it
    "dump2": True,   # Oct 19: a list item read by a line of its own fields ("{year}: {title}")
    "dump3": True,   # Oct 19: a Response that says one thing at random
    "dump4": True,   # Oct 19: outside text read as plain words (inbound defense 1)
    "dump5": True,   # Oct 19: every call out says who it is (router: user_agent; Wikipedia refuses httpx's own name)
    "dump6": True,   # Oct 19: the start its spec gives every path but its address leaves out (services: <app>: spec_prefix)
    "dump7": True,   # Oct 19: a path part written as its spec's pattern says (Wikipedia's 10, 01)
    "dump8": True,   # Oct 19: a path parameter with a few allowed values, a command per value (onthisday/births/...)
    "dump9": True,   # Oct 19: nodes of the same nature: a topic's apps in order, the next when one is busy (topics: then:)
    "dump10": True,  # Oct 19: the version check once a day, not on every restart (router: check_app_versions_every_hours)
    "dump11": True,  # Oct 19: a YAML spec's numbered answers (200:) and a wrapper's list by $ref read (Wikipedia's spec)
    "dump12": True,  # Oct 19: an app's text read cleanly: sentences as sentences, its not_said words left out (Wikipedia)
    "dump13": True,  # Oct 19: the Off-Platform model says how it heard the request first; one answered at home is answered here
    # Oct 19, the parking lot's Wepwawet column (your item 3), a flag per batch:
    "dump14": True,  # reading: another year's date says its year, how many there are, a rule's read length, numbers as she reads
    "dump15": True,  # finding: "it" after a find, a find with no name asks, filler is no name, a name holding a first and last name
    "dump16": True,  # inbound: outside data kept out of the cloud's conversation, size caps, a key's way named for Accept, the firewall on every tool call, a claimed change
    "dump17": True,  # the voice path: a corrected request's tool call asks first, her own voice is an echo, two devices on one request, the router's own CPU
    "dump18": True,  # apps: what should be against what is, a thing's date for another app, following pages, spoken names
    "dump19": True,  # the bank: asked first where she'd ask around, similar sayings, an upload; numbers never a topic's door
    "dump20": True,  # Oct 19 night: Home Assistant straight to the router in LiteLLM's place (its paths, its models, other models passed through)
    "dump21": True,
    "dump23": True,  # Oct 20: the echoes heard (by her words) go to Oread with the mishearings, to teach it her voice as the device hears it
    "dump22": True,  # Oct 19 evening: an app keeps its own names in the people grid (POST /people/<app>); Oread's own-voice mark is an echo  # Oct 19 night: a rule that says the day asks which when none was said; a request brought home timed from then
}


def on(name):
    return bool(PHASES.get(name))
