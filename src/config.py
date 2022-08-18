import csv
import os

def loadConfig():

    stations_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "data",
            "stations.csv"
        )
    )

    with open(stations_path, mode="r") as stations_file:
        stations_reader = csv.reader(stations_file)
        stations = {row[0]: row[1] for row in stations_reader}

    data = {
        "journey": {},
        "api": {}
    }

    data["all_stations"] = stations

    data["refreshTime"] = int(os.getenv("refreshTime") or 180)
    data["screenRotation"] = int(os.getenv("screenRotation") or 2)
    data["screenBlankHours"] = os.getenv("screenBlankHours") or "1-6"
    data["dualScreen"] = bool(os.getenv("dualScreen") or False)
    data["splashScreenTime"] = os.getenv("splashScreenTime") or "5"

    data["journey"]["departureStation"] = os.getenv("departureStation") or "PAD"
    data["journey"]["destinationStation"] = os.getenv("destinationStation") or ""
    data["journey"]["outOfHoursName"] = os.getenv("outOfHoursName") or stations.get(data["journey"]["departureStation"], "London Paddington")
    data["journey"]["stationAbbr"] = { "International": "Intl." }
    data["journey"]['timeOffset'] = os.getenv("timeOffset") or "0"
    data["journey"]["screen1Platform"] = os.getenv("screen1Platform") or ""
    data["journey"]["screen2Platform"] = os.getenv("screen2Platform") or ""

    data["api"]["apiKey"] = os.getenv("apiKey") or None
    data["api"]["operatingHours"] = os.getenv("operatingHours") or "8-22"

    data["api"]["logDir"] = os.getenv("logDir") or None

    return data
    