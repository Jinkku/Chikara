"""Player countries: detection from Cloudflare, the change rule, names and flags.

- A player's country is filled in automatically the first time they're seen logged in (website or game),
  from Cloudflare's CF-IPCountry header. It's only trusted when the request really came through Cloudflare
  (nginx's X-Real-IP is one of Cloudflare's addresses), so nobody can fake it by talking to the server directly.
- Every day a logged-in player is seen, their country that day is noted (dbview.CountrySeen).
- They can change it in settings once they have a stable history somewhere else:
    their current country was set CHANGE_AFTER_DAYS (6 months) ago or more, and in the new country they were
    first seen CHANGE_AFTER_DAYS ago or more, on MIN_DAYS different days or more, on SHARE of the days they
    were seen in the last 6 months, and within the last RECENT_DAYS days.
- The team can set anyone's country any time in the admin panel.
Flags: static/img/flags/<code>.svg (flag-icons 7.2.3, MIT).
"""
import datetime
import ipaddress

from django.utils import timezone
from django.utils.html import escape

CHANGE_AFTER_DAYS = 180
MIN_DAYS = 30
SHARE = 0.7
RECENT_DAYS = 30

# https://www.cloudflare.com/ips/
CLOUDFLARE = [ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
    "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29",
    "2c0f:f248::/32")]

NAMES = {
    "AD": "Andorra",
    "AE": "United Arab Emirates",
    "AF": "Afghanistan",
    "AG": "Antigua and Barbuda",
    "AI": "Anguilla",
    "AL": "Albania",
    "AM": "Armenia",
    "AO": "Angola",
    "AQ": "Antarctica",
    "AR": "Argentina",
    "AS": "American Samoa",
    "AT": "Austria",
    "AU": "Australia",
    "AW": "Aruba",
    "AX": "Aland Islands",
    "AZ": "Azerbaijan",
    "BA": "Bosnia and Herzegovina",
    "BB": "Barbados",
    "BD": "Bangladesh",
    "BE": "Belgium",
    "BF": "Burkina Faso",
    "BG": "Bulgaria",
    "BH": "Bahrain",
    "BI": "Burundi",
    "BJ": "Benin",
    "BL": "Saint Barthélemy",
    "BM": "Bermuda",
    "BN": "Brunei Darussalam",
    "BO": "Bolivia",
    "BQ": "Bonaire, Sint Eustatius and Saba",
    "BR": "Brazil",
    "BS": "Bahamas",
    "BT": "Bhutan",
    "BV": "Bouvet Island",
    "BW": "Botswana",
    "BY": "Belarus",
    "BZ": "Belize",
    "CA": "Canada",
    "CC": "Cocos (Keeling) Islands",
    "CD": "Democratic Republic of the Congo",
    "CF": "Central African Republic",
    "CG": "Republic of the Congo",
    "CH": "Switzerland",
    "CI": "Côte d'Ivoire",
    "CK": "Cook Islands",
    "CL": "Chile",
    "CM": "Cameroon",
    "CN": "China",
    "CO": "Colombia",
    "CR": "Costa Rica",
    "CU": "Cuba",
    "CV": "Cabo Verde",
    "CW": "Curaçao",
    "CX": "Christmas Island",
    "CY": "Cyprus",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "DJ": "Djibouti",
    "DK": "Denmark",
    "DM": "Dominica",
    "DO": "Dominican Republic",
    "DZ": "Algeria",
    "EC": "Ecuador",
    "EE": "Estonia",
    "EG": "Egypt",
    "EH": "Western Sahara",
    "ER": "Eritrea",
    "ES": "Spain",
    "ET": "Ethiopia",
    "FI": "Finland",
    "FJ": "Fiji",
    "FK": "Falkland Islands",
    "FM": "Federated States of Micronesia",
    "FO": "Faroe Islands",
    "FR": "France",
    "GA": "Gabon",
    "GB": "United Kingdom",
    "GD": "Grenada",
    "GE": "Georgia",
    "GF": "French Guiana",
    "GG": "Guernsey",
    "GH": "Ghana",
    "GI": "Gibraltar",
    "GL": "Greenland",
    "GM": "Gambia",
    "GN": "Guinea",
    "GP": "Guadeloupe",
    "GQ": "Equatorial Guinea",
    "GR": "Greece",
    "GS": "South Georgia and the South Sandwich Islands",
    "GT": "Guatemala",
    "GU": "Guam",
    "GW": "Guinea-Bissau",
    "GY": "Guyana",
    "HK": "Hong Kong",
    "HM": "Heard Island and McDonald Islands",
    "HN": "Honduras",
    "HR": "Croatia",
    "HT": "Haiti",
    "HU": "Hungary",
    "ID": "Indonesia",
    "IE": "Ireland",
    "IL": "Israel",
    "IM": "Isle of Man",
    "IN": "India",
    "IO": "British Indian Ocean Territory",
    "IQ": "Iraq",
    "IR": "Iran",
    "IS": "Iceland",
    "IT": "Italy",
    "JE": "Jersey",
    "JM": "Jamaica",
    "JO": "Jordan",
    "JP": "Japan",
    "KE": "Kenya",
    "KG": "Kyrgyzstan",
    "KH": "Cambodia",
    "KI": "Kiribati",
    "KM": "Comoros",
    "KN": "Saint Kitts and Nevis",
    "KP": "North Korea",
    "KR": "South Korea",
    "KW": "Kuwait",
    "KY": "Cayman Islands",
    "KZ": "Kazakhstan",
    "LA": "Laos",
    "LB": "Lebanon",
    "LC": "Saint Lucia",
    "LI": "Liechtenstein",
    "LK": "Sri Lanka",
    "LR": "Liberia",
    "LS": "Lesotho",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "LV": "Latvia",
    "LY": "Libya",
    "MA": "Morocco",
    "MC": "Monaco",
    "MD": "Moldova",
    "ME": "Montenegro",
    "MF": "Saint Martin",
    "MG": "Madagascar",
    "MH": "Marshall Islands",
    "MK": "North Macedonia",
    "ML": "Mali",
    "MM": "Myanmar",
    "MN": "Mongolia",
    "MO": "Macau",
    "MP": "Northern Mariana Islands",
    "MQ": "Martinique",
    "MR": "Mauritania",
    "MS": "Montserrat",
    "MT": "Malta",
    "MU": "Mauritius",
    "MV": "Maldives",
    "MW": "Malawi",
    "MX": "Mexico",
    "MY": "Malaysia",
    "MZ": "Mozambique",
    "NA": "Namibia",
    "NC": "New Caledonia",
    "NE": "Niger",
    "NF": "Norfolk Island",
    "NG": "Nigeria",
    "NI": "Nicaragua",
    "NL": "Netherlands",
    "NO": "Norway",
    "NP": "Nepal",
    "NR": "Nauru",
    "NU": "Niue",
    "NZ": "New Zealand",
    "OM": "Oman",
    "PA": "Panama",
    "PE": "Peru",
    "PF": "French Polynesia",
    "PG": "Papua New Guinea",
    "PH": "Philippines",
    "PK": "Pakistan",
    "PL": "Poland",
    "PM": "Saint Pierre and Miquelon",
    "PN": "Pitcairn",
    "PR": "Puerto Rico",
    "PS": "State of Palestine",
    "PT": "Portugal",
    "PW": "Palau",
    "PY": "Paraguay",
    "QA": "Qatar",
    "RE": "Réunion",
    "RO": "Romania",
    "RS": "Serbia",
    "RU": "Russia",
    "RW": "Rwanda",
    "SA": "Saudi Arabia",
    "SB": "Solomon Islands",
    "SC": "Seychelles",
    "SD": "Sudan",
    "SE": "Sweden",
    "SG": "Singapore",
    "SH": "Saint Helena, Ascension and Tristan da Cunha",
    "SI": "Slovenia",
    "SJ": "Svalbard and Jan Mayen",
    "SK": "Slovakia",
    "SL": "Sierra Leone",
    "SM": "San Marino",
    "SN": "Senegal",
    "SO": "Somalia",
    "SR": "Suriname",
    "SS": "South Sudan",
    "ST": "Sao Tome and Principe",
    "SV": "El Salvador",
    "SX": "Sint Maarten",
    "SY": "Syria",
    "SZ": "Eswatini",
    "TC": "Turks and Caicos Islands",
    "TD": "Chad",
    "TF": "French Southern Territories",
    "TG": "Togo",
    "TH": "Thailand",
    "TJ": "Tajikistan",
    "TK": "Tokelau",
    "TL": "Timor-Leste",
    "TM": "Turkmenistan",
    "TN": "Tunisia",
    "TO": "Tonga",
    "TR": "Türkiye",
    "TT": "Trinidad and Tobago",
    "TV": "Tuvalu",
    "TW": "Taiwan",
    "TZ": "Tanzania",
    "UA": "Ukraine",
    "UG": "Uganda",
    "UM": "United States Minor Outlying Islands",
    "US": "United States of America",
    "UY": "Uruguay",
    "UZ": "Uzbekistan",
    "VA": "Holy See",
    "VC": "Saint Vincent and the Grenadines",
    "VE": "Venezuela",
    "VG": "Virgin Islands (British)",
    "VI": "Virgin Islands (U.S.)",
    "VN": "Vietnam",
    "VU": "Vanuatu",
    "WF": "Wallis and Futuna",
    "WS": "Samoa",
    "YE": "Yemen",
    "YT": "Mayotte",
    "ZA": "South Africa",
    "ZM": "Zambia",
    "ZW": "Zimbabwe",
}

# shorter everyday names for the long official ones (profiles, ranking, settings)
NAMES.update({
    "US": "United States", "PS": "Palestine", "VA": "Vatican City", "FM": "Micronesia", "CD": "DR Congo",
    "CG": "Congo", "BN": "Brunei", "VC": "St Vincent", "SH": "St Helena", "GS": "South Georgia",
    "UM": "US Outlying Islands", "HM": "Heard & McDonald Islands", "IO": "British Indian Ocean Territory",
    "BQ": "Caribbean Netherlands", "KN": "St Kitts and Nevis", "PM": "St Pierre and Miquelon",
})

_seen_today = set()  # (username, day) already recorded in this process


def name(code):
    return NAMES.get((code or "").upper(), "")


def flag(code, size=""):
    """<img> of the country's flag, or "" for no / unknown country. size: CSS class modifier ("", "lg")."""
    code = (code or "").upper()
    if code not in NAMES:
        return ""
    cls = "flag" + (" flag-" + size if size else "")
    return (f'<img class="{cls}" src="/static/img/flags/{code.lower()}.svg" alt="{escape(code)}" '
            f'title="{escape(NAMES[code])}" width="20" height="15">')


def from_request(request):
    """The visitor's country from Cloudflare, or None (unknown, Tor, or not via Cloudflare)."""
    code = (request.META.get("HTTP_CF_IPCOUNTRY") or "").upper()
    if code not in NAMES:
        return None
    try:
        ip = ipaddress.ip_address((request.META.get("HTTP_X_REAL_IP") or "").strip())
    except ValueError:
        return None
    return code if any(ip in net for net in CLOUDFLARE) else None


def pending(username):
    """True if this player's country for today hasn't been recorded yet (so it's worth checking their login)."""
    return (username, datetime.date.today()) not in _seen_today


def note(request, username):
    """Record where a logged-in player is today, and give them a country if they have none. Cheap: once a day."""
    today = datetime.date.today()
    if not username or (username, today) in _seen_today:
        return
    if len(_seen_today) > 50000:
        _seen_today.clear()
    _seen_today.add((username, today))  # even with no country, so the game's login isn't re-checked all day
    code = from_request(request)
    if code is None:
        return
    from dbview.models import CountrySeen, User
    u = User.objects.filter(username=username).only("id", "country").first()
    if u is None:
        return
    CountrySeen.objects.get_or_create(user_id=u.id, day=today, country=code)
    if not u.country:
        User.objects.filter(id=u.id, country__isnull=True).update(country=code, country_set=timezone.now())


def history(user_id):
    """{code: {"first": date, "last": date, "days": n}} over everything seen for this player."""
    from dbview.models import CountrySeen
    out = {}
    for code, day in CountrySeen.objects.filter(user_id=user_id).values_list("country", "day"):
        h = out.setdefault(code, {"first": day, "last": day, "days": 0})
        h["first"], h["last"], h["days"] = min(h["first"], day), max(h["last"], day), h["days"] + 1
    return out


def can_change(user, new, hist=None):
    """(ok, reason) for switching `user` to country `new` by themselves."""
    new = (new or "").upper()
    if new not in NAMES:
        return False, "Pick a country from the list."
    if new == (user.country or ""):
        return False, "That's already your country."
    today = datetime.date.today()
    if user.country and user.country_set and (timezone.now() - user.country_set).days < CHANGE_AFTER_DAYS:
        when = (user.country_set + datetime.timedelta(days=CHANGE_AFTER_DAYS)).strftime("%-d %B %Y")
        return False, f"You can change your country again from {when}."
    hist = hist if hist is not None else history(user.id)
    h = hist.get(new)
    if not h:
        return False, f"You haven't played from {NAMES[new]} yet."
    if (today - h["first"]).days < CHANGE_AFTER_DAYS:
        when = (h["first"] + datetime.timedelta(days=CHANGE_AFTER_DAYS)).strftime("%-d %B %Y")
        return False, f"You first played from {NAMES[new]} recently: you can switch to it from {when} if you're still there."
    if h["days"] < MIN_DAYS:
        return False, f"You've played from {NAMES[new]} on {h['days']} days; you need {MIN_DAYS}."
    if (today - h["last"]).days > RECENT_DAYS:
        return False, f"You haven't played from {NAMES[new]} in the last {RECENT_DAYS} days."
    since = today - datetime.timedelta(days=CHANGE_AFTER_DAYS)
    from dbview.models import CountrySeen
    days = set(CountrySeen.objects.filter(user_id=user.id, day__gte=since).values_list("day", flat=True))
    there = set(CountrySeen.objects.filter(user_id=user.id, day__gte=since, country=new).values_list("day", flat=True))
    share = len(there) / len(days) if days else 0
    if share < SHARE:
        return False, f"Only {share:.0%} of your days in the last 6 months were in {NAMES[new]}; you need {SHARE:.0%}."
    return True, ""


def options(user):
    """Countries this player has played from, each with (code, name, ok, reason), for the settings page."""
    hist = history(user.id)
    out = []
    for code in sorted(hist, key=lambda c: -hist[c]["days"]):
        if code == user.country:
            continue
        ok, why = can_change(user, code, hist)
        out.append({"code": code, "name": NAMES.get(code, code), "ok": ok, "reason": why, "days": hist[code]["days"],
                    "since": hist[code]["first"].isoformat()})
    return out


def set_country(user_id, code):
    from dbview.models import User
    User.objects.filter(id=user_id).update(country=(code or None) and code.upper(), country_set=timezone.now())
