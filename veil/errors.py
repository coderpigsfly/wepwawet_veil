# veil/errors.py - the one kind of error a page or API call is refused with: a message fit
# to show a person, plus the web status that goes with it (turned into a reply in web.py).


class VeilError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status
