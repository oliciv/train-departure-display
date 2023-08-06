import os
import sys
import time
import json
import subprocess

from datetime import timedelta
from timeloop import Timeloop
from datetime import datetime
from PIL import ImageFont, Image
import requests

from trains import loadDeparturesForStation
from config import loadConfig
from open import isRun

from luma.core.interface.serial import spi
from luma.core.render import canvas
from luma.oled.device import ssd1322
from luma.core.virtual import viewport, snapshot, hotspot
from luma.core.sprite_system import framerate_regulator

num_departures = -1
departures = []

messageRenderCount = 0
pauseCount = 0

currentlyRendered = ()

def makeFont(name, size):
    font_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            'fonts',
            name
        )
    )
    return ImageFont.truetype(font_path, size)


def renderDestination(departure_id, font):
    def drawText(draw, width, height):
        try:
            departure = departures[departure_id]
        except IndexError:
            return
        departureTime = departure["aimed_departure_time"]
        destinationName = departure["destination_name"]
        train = f"{departureTime}  {destinationName}"
        draw.text((0, 0), text=train, font=font, fill="yellow")

    return drawText


def renderServiceStatus(departure_id):
    def drawText(draw, width, height):

        try:
            departure = departures[departure_id]
        except IndexError:
            return

        departure = departures[departure_id]
        train = ""

        if departure["expected_departure_time"] == "On time":
            train = "On time"
        elif departure["expected_departure_time"] == "Cancelled":
            train = "Cancelled"
        elif departure["expected_departure_time"] == "Delayed":
            train = "Delayed"
        else:
            if isinstance(departure["expected_departure_time"], str):
                train = 'Exp '+departure["expected_departure_time"]

            if departure["aimed_departure_time"] == departure["expected_departure_time"]:
                train = "On time"

        _x, _y, w, h = draw.textbbox((0, 0), train, font)
        draw.text((width-w,0), text=train, font=font, fill="yellow")
    return drawText


def renderPlatform(departure_id):
    def drawText(draw, width, height):
        try:
            departure = departures[departure_id]
        except IndexError:
            return
        departure = departures[departure_id]
        if "platform" in departure:
            if (departure["platform"].lower() == "bus"):
                draw.text((0, 0), text="BUS", font=font, fill="yellow")
            else:
                draw.text((0, 0), text="Plat "+departure["platform"], font=font, fill="yellow")
    return drawText


def renderCallingAt(draw, width, height):
    stations = "Calling at: "
    draw.text((0, 0), text=stations, font=font, fill="yellow")


def renderStations():
    def drawText(draw, width, height):
        global stationRenderCount, pauseCount

        stations = firstDepartureDestinations

        if(len(stations) <= stationRenderCount - 5):
            stationRenderCount = 0

        draw.text(
            (0, 0), text=stations[stationRenderCount:], width=width, font=font, fill="yellow")

        if stationRenderCount == 0 and pauseCount < 8:
            pauseCount += 1
            stationRenderCount = 0
        else:
            pauseCount = 0
            stationRenderCount += 1

    return drawText

def renderTime(draw, width, height):
    rawTime = datetime.now().time()
    hour, minute, second = str(rawTime).split('.')[0].split(':')

    _x, _y, w1, h1 = draw.textbbox((0,0), "{}:{}".format(hour, minute), fontBoldLarge)
    _x, _y, w2, h2 = draw.textbbox((0,0), ":00", fontBoldTall)

    draw.text(((width - w1 - w2) / 2, 0), text="{}:{}".format(hour, minute),
              font=fontBoldLarge, fill="yellow")
    draw.text((((width - w1 - w2) / 2) + w1, 5), text=":{}".format(second),
              font=fontBoldTall, fill="yellow")


def renderStatusText(xOffset, text):
    def drawText(draw, width, height):
        draw.text((int(xOffset), 0), text=text, font=fontBold, fill="yellow")

    return drawText

def displayError(device, width, height, text):
    virtualViewport = viewport(device, width=width, height=height)

    ip_address = subprocess.getoutput('hostname -I').strip()

    with canvas(device) as draw:
        error_size = draw.textbbox((0,0), text, fontBold)
        IpAddressSize = draw.textbbox((0,0), "IP: %s" % ip_address, fontBold)
        rowOne = snapshot(width, 10, renderStatusText((width - error_size[2]) / 2, text), interval=10)
        rowTwo = snapshot(width, 10, renderStatusText((width - IpAddressSize[2]) / 2, text="IP: %s" % ip_address), interval=10)
        if len(virtualViewport._hotspots) > 0:
            for hotspot, xy in virtualViewport._hotspots:
                virtualViewport.remove_hotspot(hotspot, xy)

        virtualViewport.add_hotspot(rowOne, (0, 0))
        virtualViewport.add_hotspot(rowTwo, (0, 36))

    return virtualViewport

def renderDepartureStation(departureStation, xOffset):
    def draw(draw, width, height):
        text = departureStation
        draw.text((int(xOffset), 0), text=text, font=fontBold, fill="yellow")

    return draw


def renderMessages(messages, xOffset):
    def draw(draw, width, height):
        global messageRenderCount, pauseCount
        if len(messages) > 0:
            text = messages[0]
        else:
            return

        text = text.rjust(160)

        if(len(text) == messageRenderCount - 5):
            messageRenderCount = 0

        draw.text((0, 0), text=text[messageRenderCount:], width=width, font=font, fill="yellow")

        if messageRenderCount == 0 and pauseCount < 8:
            pauseCount += 1
            messageRenderCount = 0
        else:
            pauseCount = 0
            messageRenderCount += 1

    return draw

def loadData(config):

    apiConfig = config["api"]
    journeyConfig = config["journey"]

    runHours = [int(x) for x in apiConfig['operatingHours'].split('-')]
    if isRun(runHours[0], runHours[1]) == False:
        return False, False, journeyConfig['outOfHoursName'], []

    if config['dualScreen'] == True:
        rows = "6"
    else:
        rows = "3"

    try:
        departures, messages, stationName = loadDeparturesForStation(config, rows)
    except requests.exceptions.RequestException as e:
        return False, False, journeyConfig['outOfHoursName'], ["Unable to connect to LDB API - {}".format(e)]
    except KeyError:
        return False, False, journeyConfig['outOfHoursName'], ["Unexpected response from LDB API"]

    if (departures == None):
        return False, False, stationName, messages

    firstDepartureDestinations = departures[0]["calling_at_list"]

    return departures, firstDepartureDestinations, stationName, []

def drawStartup(device, width, height, mainTitle):
    virtualViewport = viewport(device, width=width, height=height)

    ip_address = subprocess.getoutput('hostname -I').strip()

    revision = subprocess.getoutput('git rev-parse --short HEAD').strip()

    debugText = "IP: %s / Rev: %s" % (ip_address, revision)

    with canvas(device) as draw:
        nameSize = draw.textbbox((0,0), mainTitle, fontBold)
        poweredSize = draw.textbbox((0,0), "Powered by", fontBold)
        NRESize = draw.textbbox((0,0), "National Rail Enquiries", fontBold)
        IpAddressSize = draw.textbbox((0,0), debugText, fontBold)
        rowOne = snapshot(width, 10, renderStatusText((width - nameSize[2]) / 2, mainTitle), interval=10)
        rowThree = snapshot(width, 10, renderStatusText((width - poweredSize[2]) / 2, text="Powered by"), interval=10)
        rowFour = snapshot(width, 10, renderStatusText((width - NRESize[2]) / 2, text="National Rail Enquiries"), interval=10)
        rowFive = snapshot(width, 10, renderStatusText((width - IpAddressSize[2]) / 2, text=debugText), interval=10)

        if len(virtualViewport._hotspots) > 0:
            for hotspot, xy in virtualViewport._hotspots:
                virtualViewport.remove_hotspot(hotspot, xy)

        virtualViewport.add_hotspot(rowOne, (0, 0))
        virtualViewport.add_hotspot(rowThree, (0, 24))
        virtualViewport.add_hotspot(rowFour, (0, 36))
        virtualViewport.add_hotspot(rowFive, (0, 50))

    return virtualViewport

def drawBlankSignage(device, width, height, departureStation, messages, virtualViewport=None):
    global stationRenderCount, pauseCount, currentlyRendered

    print("BLANK SIGNAGE")

    blankInfo = (departureStation, messages)
    if blankInfo == currentlyRendered:
        return virtualViewport

    currentlyRendered = blankInfo

    with canvas(device) as draw:
        welcomeSize = draw.textbbox((0,0), "Welcome to", fontBold)

    with canvas(device) as draw:
        stationSize = draw.textbbox((0,0), departureStation, fontBold)

    device.clear()

    virtualViewport = viewport(device, width=width, height=height)

    rowOne = snapshot(width, 10, renderStatusText(
        (width - welcomeSize[2]) / 2, text="Welcome to"), interval=config["refreshTime"])
    rowTwo = snapshot(width, 10, renderDepartureStation(
        departureStation, (width - stationSize[2]) / 2), interval=config["refreshTime"])
    rowThree = snapshot(width, 10, renderMessages(messages, 0), interval=0.1)
    rowTime = hotspot(width, 14, renderTime)

    if len(virtualViewport._hotspots) > 0:
        for vhotspot, xy in virtualViewport._hotspots:
            virtualViewport.remove_hotspot(vhotspot, xy)

    virtualViewport.add_hotspot(rowOne, (0, 0))
    virtualViewport.add_hotspot(rowTwo, (0, 12))
    virtualViewport.add_hotspot(rowThree, (0, 30))
    virtualViewport.add_hotspot(rowTime, (0, 50))

    return virtualViewport

def platform_filter(departureData, platformNumber, nextStations, station):
    platformDepartures = []
    for sub in departureData:
        if platformNumber == "":
            platformDepartures.append(sub)
        elif sub.get('platform') is not None:
            if sub['platform'] == platformNumber:
                res = sub
                platformDepartures.append(res)

    if (len(platformDepartures) > 0):
        firstDepartureDestinations = platformDepartures[0]["calling_at_list"]

        if platformDepartures[0]["cancel_reason"]:
            firstDepartureDestinations = platformDepartures[0]["cancel_reason"]
        elif platformDepartures[0]["delay_reason"]:
            firstDepartureDestinations = "{}.   --   {}".format(firstDepartureDestinations, platformDepartures[0]["delay_reason"])
        else:
            firstDepartureDestinations = platformDepartures[0]["calling_at_list"]

        platformData = platformDepartures, firstDepartureDestinations, station
    else:
        platformData = platformDepartures, "", station

    return platformData

def drawSignage(device, width, height, data, virtualViewport=None):
    global stationRenderCount, pauseCount, num_departures, departures, firstDepartureDestinations, currentlyRendered

    if not virtualViewport:
        print("!!! New viewport")
        virtualViewport = viewport(device, width=width, height=height)

    status = "Exp 00:00"
    callingAt = "Calling at: "

    departures, firstDepartureDestinations, departureStation = data

    if len(departures) == num_departures:
        # We can reuse the existing hotpots with the new data and not redraw them
        print("Reusing existing viwport")
        return (virtualViewport, False)
    print('new viewport')
    num_departures = len(departures)

    with canvas(device) as draw:
        _x, _y, w, h = draw.textbbox((0,0), callingAt, font)

    callingWidth = w
    width = virtualViewport.width

    # First measure the text size
    with canvas(device) as draw:
        _x, _y, w, h = draw.textbbox((0,0), status, font)
        _x, _y, pw, ph = draw.textbbox((0,0), "Plat 88", font)

    print("DEAPRTURES?", departures)

    if(len(departures) == 0):
        noTrains = drawBlankSignage(device, width=width, height=height, departureStation=departureStation, messages=[], virtualViewport=virtualViewport)
        return (noTrains, True)

    currentlyRendered = departures

    rowOneA = snapshot(
        width - w - pw - 5, 10, renderDestination(0, fontBold), interval=1)
    rowOneB = snapshot(w, 10, renderServiceStatus(
        0), interval=10)
    rowOneC = snapshot(pw, 10, renderPlatform(0), interval=1)
    rowTwoA = snapshot(callingWidth, 10, renderCallingAt, interval=1)
    rowTwoB = snapshot(width - callingWidth, 10,
                       renderStations(), interval=0.1)

    if(len(departures) > 1):
        rowThreeA = snapshot(width - w - pw, 10, renderDestination(
            1, font), interval=config["refreshTime"])
        rowThreeB = snapshot(w, 10, renderServiceStatus(
            1), interval=config["refreshTime"])
        rowThreeC = snapshot(pw, 10, renderPlatform(1), interval=1)

    if(len(departures) > 2):
        rowFourA = snapshot(width - w - pw, 10, renderDestination(2, font), interval=10)
        rowFourB = snapshot(w, 10, renderServiceStatus(
            2), interval=10)
        rowFourC = snapshot(pw, 10, renderPlatform(2), interval=1)

    rowTime = hotspot(width, 14, renderTime)

    if len(virtualViewport._hotspots) > 0:
        for vhotspot, xy in virtualViewport._hotspots:
            virtualViewport.remove_hotspot(vhotspot, xy)

    device.clear()

    stationRenderCount = 0
    pauseCount = 0

    virtualViewport.add_hotspot(rowOneA, (0, 0))
    virtualViewport.add_hotspot(rowOneB, (width - w, 0))
    virtualViewport.add_hotspot(rowOneC, (width - w - pw, 0))
    virtualViewport.add_hotspot(rowTwoA, (0, 12))
    virtualViewport.add_hotspot(rowTwoB, (callingWidth, 12))

    if(len(departures) > 1):
        virtualViewport.add_hotspot(rowThreeA, (0, 24))
        virtualViewport.add_hotspot(rowThreeB, (width - w, 24))
        virtualViewport.add_hotspot(rowThreeC, (width - w - pw, 24))

    if(len(departures) > 2):
        virtualViewport.add_hotspot(rowFourA, (0, 36))
        virtualViewport.add_hotspot(rowFourB, (width - w, 36))
        virtualViewport.add_hotspot(rowFourC, (width - w - pw, 36))

    virtualViewport.add_hotspot(rowTime, (0, 50))

    return (virtualViewport, True)

def fatalError(text):
    virtual = displayError(device, width=widgetWidth, height=widgetHeight, text=text)
    virtual.refresh()
    while True:
        time.sleep(1)


try:
    version_file = open('VERSION', 'r')

    print('Starting Train Departure Display v' + version_file.read())
    config = loadConfig()

    serial = spi(port=0)
    device = ssd1322(serial, mode="1", rotate=config['screenRotation'])
    if config['dualScreen'] == True:
        serial1 = spi(port=1,gpio_DC=5, gpio_RST=6)
        device1 = ssd1322(serial1, mode="1", rotate=config['screenRotation'])
    font = makeFont("Dot Matrix Regular.ttf", 10)
    fontBold = makeFont("Dot Matrix Bold.ttf", 10)
    fontBoldTall = makeFont("Dot Matrix Bold Tall.ttf", 10)
    fontBoldLarge = makeFont("Dot Matrix Bold.ttf", 20)

    widgetWidth = 256
    widgetHeight = 64

    stationRenderCount = 0
    pauseCount = 0
    loop_count = 0

    regulator = framerate_regulator(20)

    # display NRE attribution while data loads
    virtual = drawStartup(device, width=widgetWidth, height=widgetHeight, mainTitle=config["mainTitle"])
    virtual.refresh()
    if config['dualScreen'] == True:
        virtual = drawStartup(device1, width=widgetWidth, height=widgetHeight)
        virtual.refresh()
    time.sleep(int(config["splashScreenTime"]))

    if not config["all_stations"].get(config["journey"]["departureStation"]):
        fatalError("Invalid station code: %s" % config["journey"]["departureStation"])

    if not config["api"]["apiKey"]:
        fatalError("Mising NRE API Key")

    timeAtStart = time.time()-config["refreshTime"]
    timeNow = time.time()

    blankHours = [int(x) for x in config['screenBlankHours'].split('-')]

    virtual = None
    while True:
        with regulator:
            if isRun(blankHours[0], blankHours[1]) == True:
                device.clear()
                if config['dualScreen'] == True:
                    device1.clear()
                time.sleep(10)
            else:
                if(timeNow - timeAtStart >= config["refreshTime"]):

                    print('Effective FPS: ' + str(round(regulator.effective_FPS(),2)))
                    data = loadData(config)
                    if data[0] == False:
                        num_departures = -1 # will force the screen to rerender once it stops being blank and departures need to be displayed again
                        virtual = drawBlankSignage(
                            device, width=widgetWidth, height=widgetHeight, departureStation=data[2], messages=data[3], virtualViewport=virtual)
                        if config['dualScreen'] == True:
                            virtual1 = drawBlankSignage(
                                device1, width=widgetWidth, height=widgetHeight, departureStation=data[2], messages=data[3], virtualViewport=virtual1)
                    else:
                        departureData = data[0]
                        nextStations = data[1]
                        station = data[2]
                        screenData = platform_filter(departureData, config["journey"]["screen1Platform"], nextStations, station)
                        print("about to draw signag")
                        # time.sleep(5)
                        virtual, changed = drawSignage(device, width=widgetWidth,height=widgetHeight, data=screenData, virtualViewport=virtual)
                        print('drew signage')
                        if config['dualScreen'] == True:
                            screen1Data = platform_filter(departureData, config["journey"]["screen2Platform"], nextStations, station)
                            virtual1 = drawSignage(device1, width=widgetWidth,height=widgetHeight, data=screen1Data)

                    timeAtStart = time.time()

                timeNow = time.time()
                
                virtual.refresh()
                if config['dualScreen'] == True:
                    virtual1.refresh()

except KeyboardInterrupt:
    pass
except ValueError as err:
    print(f"Error: {err}")
# except KeyError as err:
#     print(f"Error: Please ensure the {err} environment variable is set")
