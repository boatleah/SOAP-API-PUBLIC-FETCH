# soap_weather.py

import xml.etree.ElementTree as ET
from datetime import date

from flask import Flask, jsonify, request
from zeep import Client

# ---------------------------------------------------------------------------
# 1️⃣ Define the WSDL URL -- this is the contract that describes the API.
WSDL_URL = "https://graphical.weather.gov/xml/SOAP_server/ndfdXMLserver.php?wsdl"

# 2️⃣ Create a Zeep client. Internally it parses the WSDL and builds stubs.
client = Client(wsdl=WSDL_URL)
client.service._binding_options["address"] = (
    "https://graphical.weather.gov/xml/SOAP_server/ndfdXMLserver.php"
)

VALID_UNITS = ["e", "m"]
MIN_DAYS, MAX_DAYS = 1, 7

app = Flask(__name__)


# ---------------------------------------------------------------------------
def validate_inputs(lat, lon, days, units):
    try:
        lat, lon, days = float(lat), float(lon), int(days)
    except ValueError:
        raise ValueError("latitude, longitude and days must be numbers")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"coordinates {lat}, {lon} are out of range")
    if not MIN_DAYS <= days <= MAX_DAYS:
        raise ValueError(f"days {days} is outside the range {MIN_DAYS}-{MAX_DAYS}")
    if units not in VALID_UNITS:
        raise ValueError(f"units '{units}' is not one of {VALID_UNITS}")
    return lat, lon, days, units


def get_forecast(lat, lon, days, units):
    """
    Calls the NDFD service
    and returns the forecast as plain Python objects.
    """
    lat, lon, days, units = validate_inputs(lat, lon, days, units)

    # 3️⃣ Call the SOAP operation -- Zeep returns the reply.
    forecast_xml = client.service.NDFDgenByDay(
        latitude=lat,
        longitude=lon,
        startDate=date.today(),
        numDays=days,
        Unit=units,
        XMLformat="DWML",
        format="24 hourly",
    )

    # 4️⃣ Convert the XML reply into plain Python dicts and lists.
    root = ET.fromstring(forecast_xml)
    layouts = {
        layout.findtext("layout-key"): [
            t.text for t in layout.findall("start-valid-time")
        ]
        for layout in root.iter("time-layout")
    }
    forecast = {"latitude": lat, "longitude": lon, "units": units}
    for temp in root.iter("temperature"):
        kind = temp.get("type")
        values = [v.text for v in temp.findall("value")]
        forecast[kind] = [
            {"start": start, "temperature": value}
            for start, value in zip(layouts.get(temp.get("time-layout"), []), values)
        ]
    return forecast


def handle(lat, lon, days, units):
    try:
        return jsonify(get_forecast(lat, lon, days, units))
    except Exception as exc:
        message = (
            "Invalid input: send latitude, longitude, days from "
            f"{MIN_DAYS} to {MAX_DAYS}, and units 'e' or 'm'. " + f"Error detail: {exc}"
        )
        status = 400 if isinstance(exc, ValueError) else 502
        return jsonify({"error": message}), status


# ---------------------------------------------------------------------------
@app.get("/forecast")
def forecast_get():
    return handle(
        request.args.get("lat", ""),
        request.args.get("lon", ""),
        request.args.get("days", "3"),
        request.args.get("units", "e"),
    )


@app.post("/forecast")
def forecast_post():
    body = request.get_json(silent=True) or {}
    return handle(
        body.get("lat", ""),
        body.get("lon", ""),
        body.get("days", 3),
        body.get("units", "e"),
    )


if __name__ == "__main__":
    # 5️⃣ Run as a Flask service so the user can make repeated attempts.
    app.run(debug=True)
