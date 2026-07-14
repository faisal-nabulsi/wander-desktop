import locale
import os
import re
import sys
import time
if sys.platform == "win32":
    import pyuac  # Windows-only (UAC admin elevation); unused on macOS/Linux
import psutil
import signal
import socket
import random
import asyncio
import argparse
import requests
import threading
import webbrowser
import subprocess
import pycountry

from flask import Flask, jsonify, render_template, request
from urllib3.exceptions import InsecureRequestWarning, ConnectionError
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
from contextlib import asynccontextmanager

from pymobiledevice3.usbmux import list_devices
from pymobiledevice3.cli.mounter import auto_mount
from pymobiledevice3.lockdown import create_using_usbmux, create_using_tcp, get_mobdev2_lockdowns
from pymobiledevice3.services.amfi import AmfiService
from pymobiledevice3.exceptions import DeviceHasPasscodeSetError, NoDeviceConnectedError
from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
from pymobiledevice3.remote.utils import stop_remoted_if_required, resume_remoted_if_required, get_rsds
from pymobiledevice3.remote.tunnel_service import create_core_device_tunnel_service_using_rsd, get_remote_pairing_tunnel_services, start_tunnel, create_core_device_tunnel_service_using_remotepairing, get_core_device_tunnel_services, CoreDeviceTunnelProxy
#from pymobiledevice3.cli.remote import install_driver_if_required
from pymobiledevice3.osu.os_utils import get_os_utils
from pymobiledevice3.bonjour import DEFAULT_BONJOUR_TIMEOUT, browse_mobdev2
from pymobiledevice3.pair_records import get_local_pairing_record, get_remote_pairing_record_filename, get_preferred_pair_record
from pymobiledevice3.common import get_home_folder
try:
    from pymobiledevice3.cli.remote import cli_install_wetest_drivers  # Windows driver installer; not present in all versions / unused on macOS
except ImportError:
    cli_install_wetest_drivers = None

from pymobiledevice3.cli.remote import tunnel_task
from pymobiledevice3.lockdown import LockdownClient
from pymobiledevice3.lockdown_service_provider import LockdownServiceProvider
from pymobiledevice3.remote.common import TunnelProtocol

#========= Arg Parser ========
# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument('--no-browser', action='store_true', help='Skip auto opening the browser')
parser.add_argument('--port', type=int, help='Specify port number to listen on for web browser requests')
parser.add_argument('--wifihost', type=str, help='Specify the wifi IP address to connect to')
parser.add_argument('--udid', type=str, help='Specify the device udid to target')
parser.add_argument('--parent-pid', type=int, help='(internal) elevated backend exits when this PID dies')
args = parser.parse_args()
#========= Arg Parser ========

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
OSUTILS = get_os_utils()


import logging


# Get or create a logger instance named "Wander"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# Create a logger named "Wander"
logger = logging.getLogger("Wander")
logging.getLogger("urllib3").setLevel(logging.WARNING)

logging.getLogger('werkzeug').disabled = True
#log.disabled = True

# Resource base — src/ when run from source, or the PyInstaller bundle when packaged.
_RES = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__,
            template_folder=os.path.join(_RES, 'templates'),
            static_folder=os.path.join(_RES, 'static'))


# Optional Google Maps API key powering the Street View teleport panel. Resolved (in order):
#   1. the WANDER_MAPS_KEY environment variable, or
#   2. data/config.json  ->  {"google_maps_key": "..."}  (gitignored; bundled at build time)
# If neither is set the key stays "" and the Street View UI is hidden — the app works
# exactly as before, with zero extra network calls.
def _load_maps_key():
    env = os.environ.get('WANDER_MAPS_KEY', '').strip()
    if env:
        return env
    try:
        import json as _json
        with open(os.path.join(_RES, 'data', 'config.json'), 'r', encoding='utf-8') as f:
            return str(_json.load(f).get('google_maps_key', '')).strip()
    except Exception:
        return ''

GOOGLE_MAPS_KEY = _load_maps_key()

# Define constants
# Get the home directory of the current user
home_dir = os.path.expanduser("~")
is_windows = sys.platform == 'win32'
base_directory = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(sys.argv[0])))
flask_port = 54321
user_locale = None
location = None
rsd_data = None
rsd_host = None
rsd_port = None
rsd_data_map = {}
wifi_address = None
wifihost = args.wifihost
wifi_port = None
connection_type = None
udid = None
lockdown = None
ios_version = None
pair_record = None
error_message = None
sudo_message = ""
captured_output = None
GITHUB_REPO = 'faisal-nabulsi/wander-desktop'
CURRENT_VERSION_FILE = 'CURRENT_VERSION'
BROADCAST_FILE = 'BROADCAST'
APP_VERSION_NUMBER = "1.0.0"
APP_VERSION_TYPE = "standard"
# Single source of truth for the desktop app version used by the /update-check
# route. Bump WANDER_VERSION here AND version in wander-site desktop.json each release.
WANDER_VERSION = "1.3.0"
terminate_tunnel_thread = False
terminate_location_thread = False
location_threads = []
timeout = DEFAULT_BONJOUR_TIMEOUT

# Get the current platform using sys.platform
current_platform = sys.platform

# Map the platform names to standard values
platform = {
    'win32': 'Windows',
    'linux': 'Linux',
    'darwin': 'MacOS',
}.get(current_platform, 'Unknown')

# Check if running as sudo
if current_platform == "darwin":
    if os.geteuid() != 0:
        logger.error("*********************** WARNING ***********************")
        logger.error("Not running as Sudo, this probably isn't going to work")
        logger.error("*********************** WARNING ***********************")
        sudo_message = "Not running as Sudo, this probably isn't going to work"
    else:
        logger.info("Running as Sudo")
        sudo_message = ""



def create_wander_folder():
    # Define the path to the Wander folder
    wander_folder = os.path.join(home_dir, 'Wander')

    # Check if the Wander folder exists, create it if not
    if not os.path.exists(wander_folder):
        os.makedirs(wander_folder)
        logger.info(f"Wander Home: {wander_folder}")
        logger.info("Wander folder created successfully")

    # Set permissions for the Wander folder
    if current_platform == 'win32':
        # Windows permissions (read/write for everyone)
        os.system(f"icacls {wander_folder} /grant Everyone:(OI)(CI)F")
        logger.info("Permissions set for Wander folder on Windows")
    else:  # Linux and MacOS
        # POSIX permissions (read/write for everyone)
        os.chmod(wander_folder, 0o777)
        logger.info("Permissions set for Wander folder on MacOS")



# Define the function to be executed in the thread
def run_tunnel(service_provider):

    try:
        asyncio.run(start_quic_tunnel(service_provider))

        logger.info("run_tun completed")
        sys.exit(0)

    except Exception as e:
        error_message = str(e)

        # Handle the exception, such as logging it or returning an error response
        with app.app_context():
            return jsonify({'error': error_message})

    #return

# Define a function to start the tunnel thread
def start_tunnel_thread(service_provider):
    global terminate_tunnel_thread  # Declare the global variable
    terminate_tunnel_thread = False  # Set the value of the global variable
    thread = threading.Thread(target=run_tunnel, args=(service_provider,))
    thread.start()
    return

async def start_quic_tunnel(service_provider: RemoteServiceDiscoveryService) -> None:

    logger.warning("Start USB QUIC tunnel")

    global terminate_tunnel_thread
    stop_remoted_if_required()
    #install_driver_if_required()

    # if sys.platform == 'win32':
    #     logger.info("Windows System - Driver Check Required")
    #     if version_check(ios_version):
    #         logger.warning("Installing WeTest Driver - QUIC Tunnel")
    #         cli_install_wetest_drivers()

    service = await create_core_device_tunnel_service_using_rsd(service_provider, autopair=True)

    async with service.start_quic_tunnel() as tunnel_result:
        resume_remoted_if_required()

        logger.info(f"QUIC Address: {tunnel_result.address}")
        logger.info(f"QUIC Port: {tunnel_result.port}")
        global rsd_port
        global rsd_host
        rsd_host = tunnel_result.address

        rsd_port = str(tunnel_result.port)


        while True:
            if terminate_tunnel_thread is True:
                return
            # wait user input while the asyncio tasks execute
            await asyncio.sleep(.5)


# Define the function to be executed in the thread
def run_tcp_tunnel(service_provider):

    try:
        asyncio.run(start_tcp_tunnel(service_provider))

        logger.info("run_tun completed")
        sys.exit(0)

    except Exception as e:
        error_message = str(e)

        # Handle the exception, such as logging it or returning an error response
        with app.app_context():
            return jsonify({'error': error_message})

    #return

# Define a function to start the tunnel thread
def start_tcp_tunnel_thread(service_provider):
    global terminate_tunnel_thread  # Declare the global variable
    terminate_tunnel_thread = False  # Set the value of the global variable
    thread = threading.Thread(target=run_tcp_tunnel, args=(service_provider,))
    thread.start()
    return

async def start_tcp_tunnel(service_provider: CoreDeviceTunnelProxy) -> None:

    logger.warning("Start USB TCP tunnel")

    global terminate_tunnel_thread
    stop_remoted_if_required()
    #install_driver_if_required()

    #service = await create_core_device_tunnel_service_using_rsd(service_provider, autopair=True)

    lockdown = create_using_usbmux(udid, autopair=True)
    #print("Lockdown for Windows: ", lockdown)
    service = CoreDeviceTunnelProxy(lockdown)
    #asyncio.run(tunnel_task(service, secrets=None, protocol=TunnelProtocol.TCP), debug=True)
    async with service.start_tcp_tunnel() as tunnel_result:
        logger.info(f"TCP Address: {tunnel_result.address}")
        logger.info(f"TCP Port: {tunnel_result.port}")
        global rsd_port
        global rsd_host
        rsd_host = tunnel_result.address

        rsd_port = str(tunnel_result.port)

        while True:
            if terminate_tunnel_thread is True:
                return
            # wait user input while the asyncio tasks execute
            await asyncio.sleep(.5)





def is_major_version_17_or_greater(version_string):
    # Check if the major version in the given version string is 17 or greater.
    try:
        major_version = int(version_string.split('.')[0])
        return major_version >= 17
    except (ValueError, IndexError):
        # Handle invalid version string or missing major version
        return False

def is_major_version_less_than_16(version_string):
    # Check if the major version in the given version string is 17 or greater.
    try:
        major_version = int(version_string.split('.')[0])
        return major_version < 16
    except (ValueError, IndexError):
        # Handle invalid version string or missing major version
        logger.error(f"Error: {ValueError}, {IndexError}")
        return False


def version_check(version_string):
    try:
        # Split the version string into major and minor version parts
        version_parts = version_string.split('.')

        # Extract the major and minor version parts
        major_version = int(version_parts[0])
        minor_version = int(version_parts[1]) if len(version_parts) > 1 else 0

        # Check if the version string satisfies the condition
        if major_version == 17 and 0 <= minor_version <= 3:
            if sys.platform == 'win32':
                logger.info("Checking Windows Driver requirement")
                logger.info("Driver is required")
            return True
        else:
            if sys.platform == 'win32':
                logger.info("Driver is not required")
                return False
            logger.info("MacOS - pass")
            return False



    except (ValueError, IndexError) as e:
        logger.error(f"Driver check error: {e}")
        # Handle invalid version string or missing major/minor version
        return False

def get_user_country():
    global user_locale
    try:
        # Attempt to get the user's country using locale and pycountry
        user_locale, _ = locale.getlocale()

        if user_locale is None:
            logger.warning("User locale is None. Defaulting to IP geolocation service.")
            return get_country_from_ip()

        country_code = user_locale.split('_')[-1]
        country = pycountry.countries.get(alpha_2=country_code)
        country_name = country.name if country else None

        # If country_name is None, try IP geolocation service as a fallback
        if country_name is None:
            logger.warning("Failed to retrieve country name using locale. Using IP geolocation service.")
            return get_country_from_ip()
        else:
            return country_name

    except Exception as e:
        logger.error(f"Error getting user country: {e}")
        return None


def get_country_from_ip():
    try:
        response = requests.get("http://ip-api.com/json/", timeout=3)
        if response.status_code == 200:
            data = response.json()
            country_name = data.get("country")
            if country_name:
                return country_name
            else:
                logger.warning("Failed to retrieve country name from IP geolocation service.")
        else:
            logger.error(f"Error: Unable to retrieve data. Status code: {response.status_code}")
            logger.warning("Setting to default country")
            country_name = "Spain"
        return country_name
    except Exception as e:
        logger.error(f"Error getting country from IP geolocation service: {e}")
        country_name = "Spain"
        return country_name
def get_devices_with_retry(max_attempts=10):
    if sys.platform == 'win32':
        logger.info(f"iOS Version: {ios_version}")
        if version_check(ios_version):
            logger.info("Windows Driver Install Required")
            cli_install_wetest_drivers()
    for attempt in range(1, max_attempts + 1):
        try:
            devices = asyncio.run(get_rsds(timeout))
            #dev1 = asyncio.run(get_rsds(timeout))
            #devices = asyncio.run(get_core_device_tunnel_services(timeout))
            #print("devices: ", devices)
            #print("dev1: ", dev1)
            if devices:
                return devices  # Return devices if the list is not empty
            else:
                logger.warning(f"Attempt {attempt}: No devices found")
        except Exception as e:
            logger.warning(f"Attempt {attempt}: Error occurred - {e}")
        time.sleep(1)  # Add a delay between attempts if needed
    raise RuntimeError("No devices found after multiple attempts.\n Ensure you are running Wander as sudo / Administrator \n Please see the FAQ: https://github.com/faisal-nabulsi/wander-desktop/blob/main/FAQ.md \n If you still have the error please raise an issue on github: https://github.com/faisal-nabulsi/wander-desktop/issues ")


def get_wifi_with_retry(max_attempts=10):
    global udid, wifi_address, wifi_port

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("Discovering Wifi Devices - This may take a while...")
            devices = asyncio.run(get_remote_pairing_tunnel_services(timeout))
            #devices = get_remote_pairing_tunnel_services(timeout)



            if devices:
                if udid:
                    for device in devices:
                        if device.remote_identifier == udid:
                            logger.info(f"Device found with udid: {udid}.")
                            wifi_address = device.hostname
                            wifi_port = device.port
                            return device
                else:
                    return devices
            else:
                logger.warning(f"Attempt {attempt}: No devices found")
        except Exception as e:
            logger.warning(f"Attempt {attempt}: Error occurred - {e}")

        # Add a delay between attempts
        time.sleep(1)

    raise RuntimeError("No devices found after multiple attempts. Please see the FAQ.")
@app.route('/stop_tunnel', methods=['POST'])
def stop_tunnel_thread():
    global terminate_tunnel_thread
    logger.info("stop tunnel thread")
    # Set the terminate flag to True to stop the thread
    terminate_tunnel_thread = True
    return jsonify("Tunnel stopped")


@app.route('/update_location', methods=['POST'])
def update_location():
    # Use 'request' to get the JSON data from the client
    data = request.get_json()

    # Convert latitude and longitude to float values
    lat = float(data['lat'])
    lng = float(data['lng'])

    global location
    location = f"{lat} {lng}"
    return 'Location updated successfully'

def check_pair_record(udid):
    global pair_record
    logger.info(f"Connection Type: {connection_type}")
    logger.info("Enable Developer Mode")

    home = get_home_folder()
    logger.info(f"Pair Record Home: {home}")

    filename = get_remote_pairing_record_filename(udid)
    logger.info(f"Pair Record File: {filename}")

    # pair_record = get_local_pairing_record(filename, home)
    pair_record = get_preferred_pair_record(udid, home)
    #logger.info(f"Pair Record: {pair_record}")
    return pair_record

def check_developer_mode(udid, connection_type):
    try:

        logger.warning(f"Check Developer Mode")

        lockdown = create_using_usbmux(udid, connection_type=connection_type, autopair=True)

        result = lockdown.developer_mode_status
        logger.info(f"Developer Mode Check result:  {result}")

        # Check if developer mode is enabled
        if result:
            logger.info("Developer Mode is true")
            return True
        else:
            logger.warning("Developer Mode is false")
            return False

    except subprocess.CalledProcessError as e:
        return False


def enable_developer_mode(udid, connection_type):
    check_pair_record(udid)


    logger.info(f"Connection Type: {connection_type}")
    logger.info("Enable Developer Mode")

    home = get_home_folder()
    logger.info(f"Pair Record Home: {home}")
    #
    # filename = get_remote_pairing_record_filename(udid)
    # logger.info(f"Pair Record File: {filename}")
    #
    # pair_record = get_local_pairing_record(filename, home)
    # logger.info(f"Pair Record: {pair_record}")
    if connection_type == "Network":
        if pair_record is None:
            logger.error("Network: No Pair Record Found. Please use a USB cable first to create a pair record")
            return False, "No Pair Record Found. Please use a USB cable first to create a pair record"
    else:
        logger.error("No Pair Record Found. USB cable detected. Creating a pair record")
        pass
        #return False, "No Pair Record Found. Please use a USB cable first to create a pair record"

    lockdown = create_using_usbmux(
        udid,
        connection_type=connection_type,
        autopair=True,
        pairing_records_cache_folder=home)


    try:

        AmfiService(lockdown).enable_developer_mode()
        logger.info("Enable complete, mount developer image...")
        mount_developer_image()

    except DeviceHasPasscodeSetError:
        error_message = "Error: Device has a passcode set\n \n Please temporarily remove the passcode and run Wander again to enable Developer Mode \n \n Go to \"Settings - Face ID & Passcode\"\n"
        logger.error(f"{error_message}")
        return False, error_message

    # except Exception as e:  # Catch any other exception
    #     logger.error(f"An error occurred: {str(e)}")
    #     return False, f"An error occurred: {str(e)}"

    return True, None




@app.route('/enable_developer_mode', methods=['POST'])
def enable_developer_mode_route():
    try:
        global udid
        data = request.get_json()

        # Extract the udid from the request
        udid = data.get('udid', None)

        success, error_message = enable_developer_mode(udid, connection_type)

        if success:
            # Return a success response with any additional data needed
            return jsonify({'success': True, 'udid': udid})
        else:
            return jsonify({'error': error_message})

    except Exception as e:
        error_message = str(e)
        return jsonify({'error': error_message})



@app.route('/connect_device', methods=['POST'])
def connect_device():
    global udid, connection_type, ios_version, rsd_data, rsd_host, rsd_port, wifi_address

    data = request.get_json()
    logger.info(f"Connect Device Data: {data}")

    # Extract the udid from the request
    udid = data.get('udid', None)
    #ios_version = data.get('ios_version')

    connection_type = data.get('connType')



    if udid in rsd_data_map:
        if connection_type in rsd_data_map[udid]:
            logger.info(f"Connect_Device Map - Looking for {udid} in {connection_type}")
            rsd_data = rsd_data_map[udid][connection_type]

            rsd_host = rsd_data['host']
            rsd_port = rsd_data['port']

            logger.info(f"RSD in udid mapping is: {rsd_data}")
            logger.info("RSD already created. Reusing connection")
            logger.info(f"RSD Data: {rsd_data}")
            return jsonify({'rsd_data': rsd_data})

        # If no matching entry found for the udid and desired connection type
        logger.info(f"No matching RSD entry found for udid: {udid} and connection type: {connection_type}")


    # Check if developer mode is enabled, and enable it if not
    #logger.info("Must be iOS17")
    if not check_developer_mode(udid, connection_type):
        # Display modal to inform the user and give options
        return jsonify({'developer_mode_required': 'True'})

    if connection_type == "USB":
        return connect_usb(data)

    elif connection_type == "Network":
        check_pair_record(udid)

        if pair_record is None:
            logger.error("No Pair Record Found. Please use a USB Cable to create one")
            return jsonify({"Error": "No Pair Record Found"})
        result = connect_wifi(data)
        #result = await connect_wifi(data)
        #return await connect_wifi(data)
        return result

    elif connection_type == "Manual":
        check_pair_record(udid)

        if pair_record is None:
            logger.error("No Pair Record Found. Please use a USB Cable to create one")
            return jsonify({"Error": "No Pair Record Found"})
        result = connect_wifi(data)
        # result = await connect_wifi(data)
        # return await connect_wifi(data)
        return result
    else:
        logger.error("Error: No matching connection type")
        return jsonify({"Error": "No matching connection type"})

def check_rsd_data():
    max_attempts = 30
    attempts = 0
    while attempts < max_attempts:
        if rsd_host is not None and rsd_port is not None:
            return True  # Data is available
        time.sleep(1)
        attempts += 1
    return False  # Data is still None after all attempts

def connect_usb(data):
    try:
        global udid, connection_type
        global ios_version
        global rsd_data, rsd_host, rsd_port

        logger.info(f"USB data: {data}")

        # Extract the udid from the request
        udid = data.get('udid', None)
        ios_version = data.get('ios_version')
        #ios_version = "17.0"
        connection_type = data.get('connType')
        rsd_host = None
        rsd_port = None

        if ios_version is not None and is_major_version_17_or_greater(ios_version):
            logger.info("iOS 17+ detected")


            logger.info(f"iOS Version: {ios_version}")
            if version_check(ios_version):
                if sys.platform == 'win32':
                    logger.warning("iOS is between 17.0 and 17.3.1, WHY?")
                    logger.warning("You should upgrade to 17.4+")
                    logger.error("We need to install a 3rd party driver for these versions")
                    logger.error("which may stop working at any time")
                    try:
                        devices = get_devices_with_retry()
                        logger.info(f"Devices: {devices}")
                        rsd = [device for device in devices if device.udid == udid]
                        if len(rsd) > 0:
                            rsd = rsd[0]
                        start_tunnel_thread(rsd)

                    except RuntimeError as e:
                        error_message = str(e)
                        logger.error(f"Error: {error_message}")
                        return jsonify({'error': 'No Devices Found'})
                else:
                    logger.warning("ios <17.4 on non-windows")
                    try:
                        devices = get_devices_with_retry()
                        logger.info(f"Devices: {devices}")
                        rsd = [device for device in devices if device.udid == udid]
                        if len(rsd) > 0:
                            rsd = rsd[0]
                        start_tunnel_thread(rsd)

                    except RuntimeError as e:
                        error_message = str(e)
                        logger.error(f"Error: {error_message}")
                        return jsonify({'error': 'No Devices Found'})

            else:
                global lockdown
                lockdown = create_using_usbmux(udid, autopair=True)
                logger.info(f"Create Lockdown {lockdown}")
                start_tcp_tunnel_thread(lockdown)


            #time.sleep(3)
            if not check_rsd_data():
                logger.error("RSD Data is None, Perhaps the tunnel isn't established")
            else:
                rsd_data = rsd_host, rsd_port
                logger.info(f"RSD Data: {rsd_data}")

            rsd_data_map.setdefault(udid, {})[connection_type] = {"host": rsd_host, "port": rsd_port}
            logger.info(f"Device Connection Map: {rsd_data_map}")
            return jsonify({'rsd_data': rsd_data})

        elif ios_version is not None and not is_major_version_17_or_greater(ios_version):
            rsd_data = ios_version, udid
            logger.info(f"RSD Data: {rsd_data}")

            # # Check if developer mode is enabled, and enable it if not
            # if not check_developer_mode(udid, connection_type):
            #     # Display modal to inform the user and give options
            #     return jsonify({'developer_mode_required': 'True'})

            # create LockdownServiceProvider
            #global lockdown
            lockdown = create_using_usbmux(udid, autopair=True)
            logger.info(f"Lockdown client = {lockdown}")
            #rsd_data = rsd_host, rsd_port
            rsd_host, rsd_port = rsd_data

            #rsd_data_map[udid] = rsd_data
            rsd_data_map.setdefault(udid, {})[connection_type] = {"host": rsd_host, "port": rsd_port}

            return jsonify({'message': 'iOS version less than 17', 'rsd_data': rsd_data})

        else:
            # Invalid ios_version
            return jsonify({'error': 'No iOS version present'})
    finally:
        logger.warning("Connect Device function completed")

def connect_wifi(data):
    try:
        global udid, wifi_address, connection_type, wifi_port
        global ios_version
        global rsd_data, rsd_host, rsd_port

        logger.info(f"Wifi data: {data}")

        # Extract the udid from the request
        udid = data.get('udid', None)
        ios_version = data.get('ios_version')
        #ios_version = "17.3.1"
        #wifi_address = data.get('wifiAddress')
        #logger.error(f"wifi address: {wifi_address}")
        connection_type = data.get('connType')

        if ios_version is not None and is_major_version_17_or_greater(ios_version):
            logger.info("iOS 17+ detected")

            if version_check(ios_version):
                try:
                    devices = get_wifi_with_retry()
                    #devices = "blah"
                    logger.info(f"Connect Wifi Devices: {devices}")
                    logger.info(f"Wifi Address:  {wifi_address}")
                except RuntimeError as e:
                    error_message = str(e)
                    logger.error(f"Error: {error_message}")
                    return jsonify({'error': 'No Devices Found'})


            rsd_host = None
            rsd_port = None

            # Run tun(devices) as a background task
            #asyncio.create_task(tun(devices))
            #await tun(devices)
            #start_wifi_tunnel_thread(devices)
            start_wifi_tunnel_thread()

            if not check_rsd_data():
                logger.error("RSD Data is None, Perhaps the tunnel isn't established")
            else:
                rsd_data = rsd_host, rsd_port
                logger.info(f"RSD Data: {rsd_data}")

            rsd_data_map.setdefault(udid, {})[connection_type] = {"host": rsd_host, "port": rsd_port}
            logger.info(f"Device Connection Map: {rsd_data_map}")
            return jsonify({'rsd_data': rsd_data})

        elif ios_version is not None and not is_major_version_17_or_greater(ios_version):
            rsd_data = ios_version, udid
            logger.info(f"RSD Data: {rsd_data}")

            # create LockdownServiceProvider
            global lockdown
            lockdown = create_using_usbmux(udid, connection_type=connection_type, autopair=True)
            #lockdown = create_using_tcp(wifi_address, udid)
            logger.info(f"Lockdown client = {lockdown}")

            rsd_data_map.setdefault(udid, {})[connection_type] = {"host": rsd_host, "port": rsd_port}

            return jsonify({'message': 'iOS version less than 17', 'rsd_data': rsd_data})

        else:
            # Invalid ios_version
            return jsonify({'error': 'No iOS version present'})
    finally:
        logger.warning("Connect Device function completed")




async def start_wifi_tcp_tunnel() -> None:

    logger.warning(f"Start Wifi TCP Tunnel")

    global terminate_tunnel_thread
    stop_remoted_if_required()
    #install_driver_if_required()

    # if sys.platform == 'win32':
    #     if is_driver_required:
    #         logger.warning("Installing WeTest Driver")
    #         cli_install_wetest_drivers()

    #service = await create_core_device_tunnel_service_using_remotepairing(udid, wifi_address, wifi_port)
    lockdown = create_using_usbmux(udid)
    service = CoreDeviceTunnelProxy(lockdown)

    async with service.start_tcp_tunnel() as tunnel_result:
        resume_remoted_if_required()

        logger.info(f'Identifier: {service.remote_identifier}')
        logger.info(f'Interface: {tunnel_result.interface}')
        logger.info(f'RSD Address: {tunnel_result.address}')
        logger.info(f'RSD Port: {tunnel_result.port}')
        global rsd_port
        global rsd_host
        rsd_host = tunnel_result.address

        rsd_port = str(tunnel_result.port)


        while True:
            if terminate_tunnel_thread is True:
                return
            # wait user input while the asyncio tasks execute
            await asyncio.sleep(.5)

async def start_wifi_quic_tunnel() -> None:

    logger.warning(f"Start Wifi QUIC Tunnel")

    global terminate_tunnel_thread
    stop_remoted_if_required()
    #install_driver_if_required()

    # if sys.platform == 'win32':
    #     if is_driver_required:
    #         logger.warning("Installing WeTest Driver")
    #         cli_install_wetest_drivers()
    #get_wifi_with_retry()
    service = await create_core_device_tunnel_service_using_remotepairing(udid, wifi_address, wifi_port)
    # lockdown = create_using_usbmux(udid)
    # service = CoreDeviceTunnelProxy(lockdown)

    async with service.start_quic_tunnel() as tunnel_result:
        resume_remoted_if_required()

        logger.info(f'Identifier: {service.remote_identifier}')
        logger.info(f'Interface: {tunnel_result.interface}')
        logger.info(f'RSD Address: {tunnel_result.address}')
        logger.info(f'RSD Port: {tunnel_result.port}')
        global rsd_port
        global rsd_host
        rsd_host = tunnel_result.address

        rsd_port = str(tunnel_result.port)


        while True:
            if terminate_tunnel_thread is True:
                return
            # wait user input while the asyncio tasks execute
            await asyncio.sleep(.5)

# Define a function to start the tunnel thread
def start_wifi_tunnel_thread():
    global terminate_tunnel_thread
    terminate_tunnel_thread = False  # Set the value of the global variable
    thread = threading.Thread(target=run_wifi_tunnel)
    thread.start()
    return

# Entry point for running the tunnel async function
def run_wifi_tunnel():
    try:
        if version_check(ios_version):
            asyncio.run(start_wifi_quic_tunnel())
        #TODO: or win32 / 17.0-17.3 special tunnel

        else:
            asyncio.run(start_wifi_tcp_tunnel())
        #await tun(devices)
    except Exception as e:
        logger.error(f"Error in run_wifi_tunnel: {e}")


@app.route('/mount_developer_image', methods=['POST'])
def mount_developer_image():
    try:

        global lockdown
        lockdown = create_using_usbmux(udid, autopair=True)
        logger.info(f"mount lockdown: {lockdown}")

        auto_mount(lockdown)

        return 'Developer image mounted successfully'
    except Exception as e:
        error_message = str(e)
        return jsonify({'error': error_message})

async def set_location_thread(latitude, longitude):
    global terminate_location_thread

    try:
        global rsd_host, rsd_port, udid, ios_version, connection_type

        if udid in rsd_data_map:
            if connection_type in rsd_data_map[udid]:
                rsd_data = rsd_data_map[udid][connection_type]
                rsd_host = rsd_data['host']
                rsd_port = rsd_data['port']

                logger.info(f"RSD in udid mapping is: {rsd_data}")
                logger.info("RSD already created. Reusing connection")
                logger.info(f"RSD Data: {rsd_data}")


                if ios_version is not None and is_major_version_17_or_greater(ios_version):
                    async with RemoteServiceDiscoveryService((rsd_host, rsd_port)) as sp_rsd:
                        with DvtSecureSocketProxyService(sp_rsd) as dvt:
                            LocationSimulation(dvt).set(latitude, longitude)
                            logger.warning("Location Set Successfully")
                            #OSUTILS.wait_return()
                            while not terminate_location_thread:
                                time.sleep(0.5)


                elif ios_version is not None and not is_major_version_17_or_greater(ios_version):
                    with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
                        LocationSimulation(dvt).clear()
                        LocationSimulation(dvt).set(latitude, longitude)
                        logger.warning("Location Set Successfully")
                        #await asyncio.wait_for(OSUTILS.wait_return(), timeout=1)  # Adjust timeout as needed
                        while not terminate_location_thread:
                            time.sleep(0.5)

                await asyncio.sleep(1)  # Adjust sleep time according to your requirements

    except asyncio.CancelledError:
        # Handle cancellation gracefully
        pass
    except ConnectionResetError as cre:
        if "[Errno 54] Connection reset by peer" in str(cre):
            logger.error("The Set Location buffer is full. Try to 'Stop Location' to clear old connections")
    except Exception as e:
        logger.error(f"Error setting location: {e}")


# Function to start the set_location_thread in a separate thread
def start_set_location_thread(latitude, longitude):
    global terminate_location_thread
    # Stop existing threads
    stop_set_location_thread()

    # Reset the terminate flag before starting the thread
    terminate_location_thread = False



    # Define a helper function to run the async function in the thread
    async def run_async_function():
        await set_location_thread(latitude, longitude)

    # Define a function to periodically check if the thread should terminate
    def check_termination():
        while not terminate_location_thread:
            asyncio.run(asyncio.sleep(1))  # Adjust sleep time as needed
        logger.info("Location Thread Terminated")

    # Create a new thread and start it
    location_thread = threading.Thread(target=lambda: asyncio.run(run_async_function()))
    location_thread.start()

    # Create a new thread for checking termination
    termination_thread = threading.Thread(target=check_termination)
    termination_thread.start()


# Function to stop the location thread
def stop_set_location_thread():
    # Set the flag to indicate that the thread should stop
    global terminate_location_thread
    terminate_location_thread = True




@app.route('/set_location', methods=['POST'])
def set_location():
    try:
        global rsd_data, rsd_host, rsd_port
        global location
        global udid, connection_type
        global ios_version

        if ios_version is not None and is_major_version_17_or_greater(ios_version):
            # Split the location string into latitude and longitude
            latitude, longitude = location.split()

            #asyncio.run(set_location_thread(latitude, longitude))
            start_set_location_thread(latitude, longitude)

            return 'Location set successfully'

        elif ios_version is not None and not is_major_version_17_or_greater(ios_version):
            global lockdown
            # Split the location string into latitude and longitude
            latitude, longitude = location.split()

            mount_developer_image()
            #asyncio.run(set_location_thread(latitude, longitude))
            start_set_location_thread(latitude, longitude)


            return 'Location set successfully'

        else:
            # Invalid ios_version
            return jsonify({'error': 'No iOS version present'})

    except Exception as e:
        error_message = str(e)
        return jsonify({'error': error_message})


@app.route('/stop_location', methods=['POST'])
def stop_location():
    # NOTE: this is a SYNC view on purpose. It used to be `async def`, which threw
    # "Install Flask with the 'async' extra" on every call — so the location never
    # cleared. We run the async clear over the tunnel via asyncio.run() instead.
    try:
        stop_set_location_thread()
        stop_all_movement()   # also stop joystick/route/jump movement if running
        global rsd_data
        global rsd_host
        global rsd_port
        global lockdown
        global ios_version, udid, connection_type
        logger.info(f"stop set location data:  {rsd_data}")

        if udid in rsd_data_map:
            if connection_type in rsd_data_map[udid]:
                rsd_data = rsd_data_map[udid][connection_type]
                rsd_host = rsd_data['host']
                rsd_port = rsd_data['port']

            if ios_version is not None and is_major_version_17_or_greater(ios_version):
                async def _clear_ios17():
                    async with RemoteServiceDiscoveryService((rsd_host, rsd_port)) as sp_rsd:
                        with DvtSecureSocketProxyService(sp_rsd) as dvt:
                            LocationSimulation(dvt).clear()
                            logger.warning("Location Cleared Successfully")
                asyncio.run(_clear_ios17())
                return 'Location cleared successfully'

            elif ios_version is not None and not is_major_version_17_or_greater(ios_version):
                with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
                    LocationSimulation(dvt).clear()
                    logger.warning("Location Cleared Successfully")
                return 'Location cleared successfully'
        return 'Location cleared successfully'
    except Exception as e:
        error_message = str(e)
        logger.error(f"stop_location error: {error_message}")
        return jsonify({'error': error_message})


# ============================================================================
# Wander movement engine — powers Teleport / Route / Joystick / Jump modes.
# Everything is LocationSimulation.set(lat,lng) fired repeatedly over ONE held
# DVT connection. A generator `get_next()` yields (lat,lng) or (lat,lng,sleep)
# each tick; returning None ends the stream. Reuses the same device connection
# globals the app already established.
# ============================================================================
import math

_move_stop = threading.Event()
_move_thread = None
_move_state = {"mode": None, "point": 0, "total": 0}
_joystick = {"lat": None, "lng": None, "heading": 0.0, "speed_mps": 1.4, "moving": False}


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _offset(lat, lng, heading_deg, dist_m):
    """Move dist_m metres from (lat,lng) along a compass heading (0=N, 90=E)."""
    R = 6371000.0
    brng = math.radians(heading_deg)
    p1, l1 = math.radians(lat), math.radians(lng)
    p2 = math.asin(math.sin(p1) * math.cos(dist_m / R) +
                   math.cos(p1) * math.sin(dist_m / R) * math.cos(brng))
    l2 = l1 + math.atan2(math.sin(brng) * math.sin(dist_m / R) * math.cos(p1),
                         math.cos(dist_m / R) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), math.degrees(l2)


def pogo_cooldown_minutes(km):
    """Pokémon GO soft-ban cooldown: safe minutes to wait after moving `km`."""
    tbl = [(0, 0), (1, 0.5), (5, 2), (10, 6), (25, 9), (30, 11), (65, 22),
           (81, 25), (100, 35), (250, 45), (500, 60), (750, 75), (1000, 85),
           (1250, 90), (1500, 100), (2000, 120)]
    prev = tbl[0]
    for d, m in tbl:
        if km <= d:
            if d == prev[0]:
                return m
            frac = (km - prev[0]) / (d - prev[0])
            return round(prev[1] + (m - prev[1]) * frac, 1)
        prev = (d, m)
    return 120.0


def _build_path(points, speed_mps, interval=1.0, loop="once"):
    """Sample (lat,lng) along the waypoint list at speed_mps (one sample per interval s)."""
    samples = []
    seq = list(points)
    if loop == "round" and len(seq) > 1:
        seq = seq + list(reversed(seq[:-1]))
    for i in range(len(seq) - 1):
        a, b = seq[i], seq[i + 1]
        dist = _haversine_m(a[0], a[1], b[0], b[1])
        steps = max(1, int(dist / max(0.1, speed_mps * interval)))
        for s in range(1, steps + 1):
            samples.append((a[0] + (b[0] - a[0]) * s / steps,
                            a[1] + (b[1] - a[1]) * s / steps))
    return samples


def _bearing(lat1, lon1, lat2, lon2):
    """Initial compass bearing (0=N, 90=E) from point A to point B, in degrees."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _turn_angle(b1, b2):
    """Smallest absolute change in heading (0..180) between two bearings."""
    d = abs((b2 - b1 + 180.0) % 360.0 - 180.0)
    return d


def _build_realistic_path(points, speed_mps, interval=1.0, loop="once"):
    """Like _build_path but models human/vehicle movement: slow down into sharp
    turns, ease back up on the straights, and add small speed variance so the
    trace never looks like a metronome. Mirrors iOS buildRealisticSamples."""
    seq = list(points)
    if loop == "round" and len(seq) > 1:
        seq = seq + list(reversed(seq[:-1]))
    if len(seq) < 2:
        return []

    # Per-segment bearings so we can measure how sharp each corner is.
    bearings = [_bearing(seq[i][0], seq[i][1], seq[i + 1][0], seq[i + 1][1])
                for i in range(len(seq) - 1)]

    base = max(0.2, speed_mps)
    samples = []
    for i in range(len(seq) - 1):
        a, b = seq[i], seq[i + 1]
        dist = _haversine_m(a[0], a[1], b[0], b[1])
        if dist <= 0.0:
            continue
        # Turn severity at the *start* of this segment (how hard we just cornered).
        if i == 0:
            weight_in = 1.0
        else:
            ang = _turn_angle(bearings[i - 1], bearings[i])
            # 0 deg -> full speed, 90 deg -> ~0.55x, 180 deg (U-turn) -> ~0.28x.
            weight_in = max(0.28, 1.0 - (ang / 180.0) * 0.72)
        # Ease back to cruising speed by the end of the segment.
        seg_speed_start = base * weight_in
        seg_speed_end = base
        steps = max(1, int(dist / max(0.1, base * interval)))
        for s in range(1, steps + 1):
            f = s / steps
            # Linear ramp from the slowed corner speed back up to cruise.
            spd = seg_speed_start + (seg_speed_end - seg_speed_start) * f
            spd *= random.uniform(0.88, 1.12)          # +/-12% natural variance
            spd = max(0.2, spd)
            lat = a[0] + (b[0] - a[0]) * f
            lng = a[1] + (b[1] - a[1]) * f
            # Emit (lat, lng, dwell) so the pump waits longer where we move slower.
            step_dist = dist / steps
            dwell = max(0.2, min(4.0, step_dist / spd))
            samples.append((lat, lng, dwell))
    return samples


def _jitter(lat, lng, on, radius_m=None):
    """Nudge the point by a small random offset so the fix looks like a real GPS
    reading. `radius_m` is the max offset in metres; None keeps the legacy ~4.4 m
    default. Longitude degrees are scaled by cos(lat) so the radius is metric."""
    if not on:
        return (lat, lng)
    if radius_m is None:
        # Legacy behaviour: +/- 0.00004 deg (~4.4 m at the equator) on each axis.
        lat += random.uniform(-0.00004, 0.00004)
        lng += random.uniform(-0.00004, 0.00004)
        return (lat, lng)
    try:
        r = max(0.0, float(radius_m))
    except (TypeError, ValueError):
        r = 0.0
    if r <= 0.0:
        return (lat, lng)
    dlat = r / 111320.0                                     # metres -> degrees latitude
    dlng = r / (111320.0 * max(0.01, math.cos(math.radians(lat))))
    lat += random.uniform(-dlat, dlat)
    lng += random.uniform(-dlng, dlng)
    return (lat, lng)


async def _pump(get_next):
    """Open ONE DVT LocationSimulation and drive it from get_next() until stop/None."""
    try:
        global rsd_host, rsd_port
        if udid in rsd_data_map and connection_type in rsd_data_map[udid]:
            rsd = rsd_data_map[udid][connection_type]
            rsd_host, rsd_port = rsd["host"], rsd["port"]

        def drive(sim):
            while not _move_stop.is_set():
                nxt = get_next()
                if nxt is None:
                    break
                lat, lng = nxt[0], nxt[1]
                sleep_s = nxt[2] if len(nxt) > 2 else 1.0
                try:
                    sim.set(float(lat), float(lng))
                except Exception as e:
                    logger.error(f"sim.set error: {e}")
                    break
                waited = 0.0
                while waited < sleep_s and not _move_stop.is_set():
                    step = min(0.25, sleep_s - waited)
                    time.sleep(step)
                    waited += step

        if ios_version is not None and is_major_version_17_or_greater(ios_version):
            async with RemoteServiceDiscoveryService((rsd_host, rsd_port)) as sp_rsd:
                with DvtSecureSocketProxyService(sp_rsd) as dvt:
                    drive(LocationSimulation(dvt))
        else:
            with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
                drive(LocationSimulation(dvt))
    except Exception as e:
        logger.error(f"movement stream error: {e}")


def _start_stream(get_next, mode):
    global _move_thread
    stop_all_movement()
    _move_stop.clear()
    _move_state.update({"mode": mode, "point": 0})
    _move_thread = threading.Thread(target=lambda: asyncio.run(_pump(get_next)), daemon=True)
    _move_thread.start()


def stop_all_movement():
    global terminate_location_thread
    _move_stop.set()
    terminate_location_thread = True
    _move_state["mode"] = None


@app.route('/wander/teleport', methods=['POST'])
def wander_teleport():
    d = request.get_json(force=True) or {}
    lat, lng = float(d['lat']), float(d['lng'])
    fluc = bool(d.get('fluctuate'))
    jm = d.get('jitter_m')

    def nxt():
        return _jitter(lat, lng, fluc, jm)   # hold the point (re-jitter if enabled)
    _start_stream(nxt, "teleport")
    return jsonify({"ok": True, "lat": lat, "lng": lng})


@app.route('/wander/route', methods=['POST'])
def wander_route():
    d = request.get_json(force=True) or {}
    pts = [(float(p[0]), float(p[1])) for p in d['points']]
    speed = float(d.get('speed_mps', 1.4))
    loop = d.get('loop', 'once')              # once | round | loop
    realistic = bool(d.get('realistic'))
    fluc = bool(d.get('fluctuate') or realistic)
    jm = d.get('jitter_m')
    seg_loop = 'round' if loop == 'round' else 'once'
    if realistic:
        # Turn-aware samples carry their own dwell time (lat, lng, dwell).
        samples = _build_realistic_path(pts, speed, 1.0, seg_loop)
    else:
        samples = _build_path(pts, speed, 1.0, seg_loop)
    _move_state["total"] = len(samples)
    idx = {"i": 0}

    def nxt():
        i = idx["i"]
        if i >= len(samples):
            if loop == 'loop' and samples:
                idx["i"] = 0
                i = 0
            else:
                last = samples[-1] if samples else pts[-1]
                lat, lng = last[0], last[1]
                return _jitter(lat, lng, fluc, jm)   # hold at the end
        smp = samples[i]
        lat, lng = smp[0], smp[1]
        idx["i"] = i + 1
        _move_state["point"] = idx["i"]
        j = _jitter(lat, lng, fluc, jm)
        if len(smp) > 2:                              # realistic path -> honour dwell
            return (j[0], j[1], smp[2])
        return j
    _start_stream(nxt, "route")
    return jsonify({"ok": True, "samples": len(samples), "realistic": realistic})


@app.route('/wander/jump', methods=['POST'])
def wander_jump():
    d = request.get_json(force=True) or {}
    seq = [(float(p[0]), float(p[1])) for p in d['points']]
    auto = bool(d.get('auto_cooldown'))
    fluc = bool(d.get('fluctuate'))
    jm = d.get('jitter_m')
    _move_state["total"] = len(seq)
    st = {"i": 0, "prev": None}

    def nxt():
        i = st["i"]
        if i >= len(seq):
            lat, lng = seq[-1]
            return _jitter(lat, lng, fluc, jm)       # hold last
        lat, lng = seq[i]
        wait = 1.0
        if auto and st["prev"] is not None:
            km = _haversine_m(st["prev"][0], st["prev"][1], lat, lng) / 1000.0
            wait = max(1.0, pogo_cooldown_minutes(km) * 60.0)
        st["prev"] = (lat, lng)
        st["i"] = i + 1
        _move_state["point"] = st["i"]
        j = _jitter(lat, lng, fluc, jm)
        return (j[0], j[1], wait)
    _start_stream(nxt, "jump")
    return jsonify({"ok": True, "points": len(seq)})


@app.route('/wander/joystick/start', methods=['POST'])
def wander_joystick_start():
    d = request.get_json(force=True) or {}
    _joystick.update({
        "lat": float(d['lat']), "lng": float(d['lng']),
        "heading": float(d.get('heading', 0)),
        "speed_mps": float(d.get('speed_mps', 1.4)),
        "moving": False,
    })

    def nxt():
        if _joystick["lat"] is None:
            return None
        if _joystick["moving"]:
            _joystick["lat"], _joystick["lng"] = _offset(
                _joystick["lat"], _joystick["lng"], _joystick["heading"], _joystick["speed_mps"])
        return (_joystick["lat"], _joystick["lng"])
    _start_stream(nxt, "joystick")
    return jsonify({"ok": True})


@app.route('/wander/joystick/dir', methods=['POST'])
def wander_joystick_dir():
    d = request.get_json(force=True) or {}
    if 'heading' in d:
        _joystick["heading"] = float(d['heading'])
    if 'speed_mps' in d:
        _joystick["speed_mps"] = float(d['speed_mps'])
    if 'moving' in d:
        _joystick["moving"] = bool(d['moving'])
    return jsonify({"ok": True, "heading": _joystick["heading"], "moving": _joystick["moving"]})


@app.route('/wander/cooldown', methods=['GET'])
def wander_cooldown():
    km = float(request.args.get('km', 0))
    return jsonify({"km": km, "minutes": pogo_cooldown_minutes(km)})


def _parse_maxspeed(raw):
    """Turn an OSM maxspeed tag ('50', '30 mph', 'RU:urban', 'walk') into m/s."""
    if not raw:
        return None
    s = str(raw).strip().lower()
    if s in ('none', 'signals', 'variable'):
        return None
    if s == 'walk':
        return 1.4
    m = re.search(r'(\d+(?:\.\d+)?)', s)
    if not m:
        return None
    val = float(m.group(1))
    if 'mph' in s:
        return val * 0.44704            # miles/h -> m/s
    if 'knot' in s:
        return val * 0.514444
    return val / 3.6                    # default km/h -> m/s


@app.route('/wander/osm_speed', methods=['GET'])
def wander_osm_speed():
    """Look up the posted speed limit of the nearest road via OpenStreetMap's
    Overpass API and return it in m/s so route modes can drive at road speed.
    Mirrors iOS speedLimit mode (fetchOpenStreetMapWays)."""
    try:
        lat = float(request.args.get('lat'))
        lng = float(request.args.get('lng'))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "lat/lng required"}), 400
    # Search outward until we find a highway with a maxspeed tag.
    query = (
        '[out:json][timeout:12];'
        'way(around:180,%f,%f)[highway][maxspeed];'
        'out tags center 1;'
    ) % (lat, lng)
    endpoints = [
        'https://overpass-api.de/api/interpreter',
        'https://overpass.kumi.systems/api/interpreter',
    ]
    for url in endpoints:
        try:
            r = requests.post(url, data={'data': query}, timeout=15,
                              headers={'User-Agent': 'Wander-Desktop/1.0'})
            if r.status_code != 200:
                continue
            js = r.json()
            for el in js.get('elements', []):
                mps = _parse_maxspeed((el.get('tags') or {}).get('maxspeed'))
                if mps and mps > 0:
                    tags = el.get('tags') or {}
                    return jsonify({
                        "ok": True,
                        "speed_mps": round(mps, 2),
                        "speed_kmh": round(mps * 3.6, 1),
                        "maxspeed": tags.get('maxspeed'),
                        "road": tags.get('name') or tags.get('highway'),
                    })
            return jsonify({"ok": False, "error": "no speed limit found nearby"})
        except Exception as e:
            logger.error(f"osm_speed error ({url}): {e}")
            continue
    return jsonify({"ok": False, "error": "OpenStreetMap lookup failed"}), 502


@app.route('/wander/stop', methods=['POST'])
def wander_stop():
    stop_all_movement()
    return jsonify({"ok": True})


@app.route('/wander/status', methods=['GET'])
def wander_status():
    return jsonify({"mode": _move_state["mode"], "point": _move_state["point"], "total": _move_state["total"]})


@app.route('/wander/pogo', methods=['GET'])
def wander_pogo():
    """PoGo Mode data: curated hotspot coordinate packs + premade routes."""
    import json as _json
    try:
        p = os.path.join(_RES, 'data', 'pogo.json')
        with open(p, 'r', encoding='utf-8') as f:
            return jsonify(_json.load(f))
    except Exception as e:
        logger.error(f"pogo data error: {e}")
        return jsonify({"hotspots": [], "routes": [], "error": str(e)}), 500


# Server-side geocode proxy. Nominatim rejects browser/no-User-Agent/datacenter
# requests, so the in-app GeoSearch provider frequently returned "No results found".
# We proxy the query through the desktop process with a proper User-Agent and cache
# results in-memory so repeated searches don't hammer the public endpoint.
_geocode_cache = {}


@app.route('/geocode', methods=['GET'])
def geocode():
    q = (request.args.get('q') or '').strip()
    if not q:
        return app.response_class('[]', mimetype='application/json')

    key = q.lower()
    if key in _geocode_cache:
        return app.response_class(_geocode_cache[key], mimetype='application/json')

    import json as _json
    _UA = {'User-Agent': 'Wander/1.0 (https://wanderspoofer.com; support@wanderspoofer.com)'}
    results = []
    upstream_error = False   # True = a provider errored/rate-limited (vs. a genuine "no match")

    # 1) Nominatim (best display names, but rate-limits aggressively).
    try:
        resp = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={'format': 'json', 'limit': 5, 'q': q},
            headers=_UA, timeout=6,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                results = data
        else:
            upstream_error = True
            logger.warning(f"geocode: nominatim status {resp.status_code} for {q!r}")
    except Exception as e:
        upstream_error = True
        logger.warning(f"geocode: nominatim error for {q!r}: {e}")

    # 2) Photon (komoot) fallback — same OSM data, far more lenient, no key. Runs
    #    whenever Nominatim gave nothing (a real miss OR a rate-limit/error), which
    #    is what makes searches keep working when Nominatim throttles us.
    if not results:
        try:
            r2 = requests.get(
                'https://photon.komoot.io/api/',
                params={'q': q, 'limit': 5}, headers=_UA, timeout=6,
            )
            if r2.status_code == 200:
                gj = r2.json()
                for feat in (gj.get('features') or []):
                    geom = feat.get('geometry') or {}
                    coords = geom.get('coordinates')   # [lon, lat]
                    if coords and len(coords) >= 2:
                        props = feat.get('properties') or {}
                        label = ', '.join(
                            str(props[k]) for k in ('name', 'street', 'city', 'state', 'country')
                            if props.get(k)
                        )
                        results.append({'lat': str(coords[1]), 'lon': str(coords[0]),
                                        'display_name': label or q})
                if results:
                    upstream_error = False   # fallback rescued the search
            else:
                upstream_error = True
                logger.warning(f"geocode: photon status {r2.status_code} for {q!r}")
        except Exception as e:
            upstream_error = True
            logger.warning(f"geocode: photon error for {q!r}: {e}")

    if results:
        payload = _json.dumps(results)
        _geocode_cache[key] = payload   # cache successes only
        return app.response_class(payload, mimetype='application/json')

    # Both providers unreachable/rate-limited → tell the client it's a transient
    # problem, not a genuine "no such place", so the UI can say "try again".
    if upstream_error:
        return app.response_class(_json.dumps({'error': 'geocode_unavailable'}),
                                  mimetype='application/json')
    return app.response_class('[]', mimetype='application/json')


# --- Auto update check ------------------------------------------------------
# Small in-process cache so repeated page loads don't re-hit the network.
_update_cache = {'ts': 0, 'data': None}
_UPDATE_CACHE_TTL = 900  # seconds


def _version_tuple(v):
    # Parse a dotted version string into a tuple of ints for a simple semver
    # compare. Non-numeric / missing parts fall back to 0 so junk never crashes.
    parts = []
    for chunk in str(v).strip().split('.'):
        num = ''.join(ch for ch in chunk if ch.isdigit())
        parts.append(int(num) if num else 0)
    # Pad to at least major.minor.patch so "1.0" and "1.0.0" compare equal and
    # different-length versions never mis-order (e.g. "1.0" isn't seen as < "1.0.0").
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


@app.route('/update-check', methods=['GET'])
def update_check():
    # Fetch the published desktop manifest, compare against WANDER_VERSION, and
    # tell the UI whether a newer build exists plus the right download URL for
    # this OS. Any failure is swallowed into {updateAvailable: false} so the map
    # never blocks on the network.
    now = time.time()
    if _update_cache['data'] is not None and (now - _update_cache['ts']) < _UPDATE_CACHE_TTL:
        return jsonify(_update_cache['data'])

    result = {'updateAvailable': False}
    try:
        resp = requests.get(
            'https://wanderspoofer.com/downloads/desktop.json',
            timeout=4,
        )
        if resp.status_code == 200:
            data = resp.json()
            remote_version = str(data.get('version', '')).strip()
            # Darwin -> mac zip, Windows -> win installer. current_platform is
            # sys.platform ('darwin' / 'win32' / 'linux').
            if current_platform == 'darwin':
                url = data.get('url_mac')
            elif current_platform == 'win32':
                url = data.get('url_win')
            else:
                url = None
            if (remote_version and url
                    and _version_tuple(remote_version) > _version_tuple(WANDER_VERSION)):
                result = {
                    'updateAvailable': True,
                    'version': remote_version,
                    'url': url,
                    'notes': data.get('notes', ''),
                }
    except Exception as e:
        logger.error(f"update-check error: {e}")
        result = {'updateAvailable': False}

    _update_cache['ts'] = now
    _update_cache['data'] = result
    return jsonify(result)


def get_github_version():
    try:
        # Make a request to the GitHub API to get the content of CURRENT_VERSION file
        url = f'https://raw.githubusercontent.com/{GITHUB_REPO}/main/{CURRENT_VERSION_FILE}'
        response = requests.get(url, timeout=3)

        # Defensive: a missing file returns 200-with-"404: Not Found" body on
        # some hosts, or a real error status. Never surface junk as a version.
        if response.status_code != 200:
            return None

        # Parse the content of the file
        github_version = response.text.strip()


        return github_version
    except requests.RequestException as e:

        return None


def get_github_broadcast():
    try:
        # Make a request to the GitHub API to get the content of CURRENT_VERSION file
        url = f'https://raw.githubusercontent.com/{GITHUB_REPO}/main/{BROADCAST_FILE}'
        logger.error(f"Github URL: {url}")

        response = requests.get(url, verify=False, timeout=3)
        logger.error(f"github response: {response}")

        # If the broadcast file is missing (404) or any non-200 status, the
        # response body is junk like "404: Not Found". Return an empty string
        # so a missing broadcast shows NO toast at all.
        if response.status_code != 200:
            return ""

        # Parse the content of the file
        github_broadcast = response.text.strip()
        logger.error(f"GITHUB BROADCAST MESSAGE:")

        return github_broadcast
    except requests.RequestException as e:

        return ""


def remove_ansi_escape_codes(text):
    ansi_escape = re.compile(r'\x1b[^m]*m')
    return ansi_escape.sub('', text)

async def get_network_devices():
# you can also query network lockdown instances using the following:
    async for ip, lockdown in get_mobdev2_lockdowns():
        print(ip, lockdown.short_info)

@app.route('/list_devices')
def py_list_devices():
    try:
        connected_devices = {}

        # Retrieve all devices
        all_devices = list_devices()
        #wifi_devices = None
        #wifi_devices = asyncio.run(get_network_devices())
        logger.info(f"\n\nRaw Devices:  {all_devices}\n")
        #logger.info(f"\n\nWifi Devices:  {wifi_devices}\n")


        if wifihost:
            udid = args.udid
            logger.warning(f"Wifi requested to {wifihost}")
            logger.warning(f"udid: {udid}")
            lockdown = create_using_tcp(hostname=wifihost, identifier=udid)

            # udid = lockdown.udid
            # print("wifi udid", udid)
            info = lockdown.short_info
            logger.warning(f"Wifi Short Info: {info}")
            # Modify the info dictionary to include wifiConState
            wifi_connection_state = lockdown.enable_wifi_connections = True
            info['wifiState'] = wifi_connection_state

            # Modify the info dictionary to include user locale
            info['userLocale'] = get_user_country()

            info['ConnectionType'] = 'Network'

            # Substitute "Network" with "Wifi" in the connection_type
            connection_type = "Manual Wifi"
            # if connection_type == "Network":
            #     connection_type = "Wifi"

            # If the serial already exists in the connected_devices dictionary
            if udid in connected_devices:
                # If the connection_type already exists under the serial, append the device to the list
                if connection_type in connected_devices[udid]:
                    connected_devices[udid][connection_type].append(info)
                # If the connection_type doesn't exist under the serial, create a new list with the device
                else:
                    connected_devices[udid][connection_type] = [info]
            # If the serial is new, create a new dictionary entry with the connection_type as a list
            else:
                connected_devices[udid] = {connection_type: [info]}






        # Iterate through all devices

        for device in all_devices:
            udid = device.serial
            connection_type = device.connection_type

            # Create lockdown and info variables
            #global lockdown
            lockdown = create_using_usbmux(udid, connection_type=connection_type, autopair=True)
            info = lockdown.short_info


            wifi_connection_state = lockdown.enable_wifi_connections

            if wifi_connection_state == False:
                logger.info("Enabling Wifi Connections")
                wifi_connection_state = lockdown.enable_wifi_connections = True
                logger.info(f"Wifi Connection State: True")

            # Modify the info dictionary to include wifiConState
            info['wifiState'] = wifi_connection_state

            # Modify the info dictionary to include user locale
            info['userLocale'] = get_user_country()

            # Substitute "Network" with "Wifi" in the connection_type
            if connection_type == "Network":
                connection_type = "Wifi"

            # If the serial already exists in the connected_devices dictionary
            if udid in connected_devices:
                # If the connection_type already exists under the serial, append the device to the list
                if connection_type in connected_devices[udid]:
                    connected_devices[udid][connection_type].append(info)
                # If the connection_type doesn't exist under the serial, create a new list with the device
                else:
                    connected_devices[udid][connection_type] = [info]
            # If the serial is new, create a new dictionary entry with the connection_type as a list
            else:
                connected_devices[udid] = {connection_type: [info]}

        logger.info(f"\n\nConnected Devices: {connected_devices}\n")

        # Check if running as sudo
        if current_platform == "darwin":
            if os.geteuid() != 0:
                logger.error("*********************** WARNING ***********************")
                logger.error("Not running as Sudo, this probably isn't going to work")
                logger.error("*********************** WARNING ***********************")
        return jsonify(connected_devices)

    except ConnectionAbortedError as e:
        logger.error(f"ConnectionAbortedError occurred: {e}")
        return {"error"}

    except Exception as e:
        error_message = str(e)
        return jsonify({'error': error_message})

def clear_wander():
    logger.info("clear any Wander instances")
    substring = "Wander"

    for process in psutil.process_iter(['pid', 'name']):
        if substring in process.info['name']:
            logger.info(f"Found process: {process.info['pid']} - {process.info['name']}")

            # Terminate the process
            process.terminate()
    else:
        logger.warning("No Wander found")


def clear_old_wander():
    logger.info("clear old Wander instances")
    substring = "Wander"

    current_pid = os.getpid()

    for process in psutil.process_iter(['pid', 'name']):
        if substring in process.info['name'] and process.info['pid'] != current_pid:
            logger.info(f"Found process: {process.info['pid']} - {process.info['name']}")

            # Terminate the process
            process.terminate()


def shutdown_server():
    logger.warning("shutdown server")
    asyncio.run(stop_location())
    stop_set_location_thread()
    stop_tunnel_thread()
    cancel_async_tasks()
    terminate_threads()


    # Terminate the current process
    clear_wander()

    logger.error("OS Kill")
    os.kill(os.getpid(), signal.SIGINT)
    list_threads()
    terminate_threads()
    logger.error("sys exit")
    os._exit(0)


def terminate_threads():
    """
    Terminate all threads.
    """
    for thread in threading.enumerate():
        if thread != threading.main_thread():
            logger.info(f"thread: {thread}")
            terminate_flag = threading.Event()
            terminate_flag.set()
            #thread.terminate()  # Terminate the thread

def list_threads():
    """
    Terminate all threads.
    """
    for thread in threading.enumerate():
        logger.info(f"thread: {thread}")
def cancel_async_tasks():
    try:
        #loop = asyncio.get_running_loop()
        tasks = asyncio.all_tasks()
        for task in tasks:
            logger.info(f"task: {task}")
            task.cancel()
    except RuntimeError as e:
        if "no running event loop" in str(e):
            logger.error("No running event loop found.")
        else:
            raise e  # Re-raise the error if it's not related to the event loop



@app.route('/exit', methods=['POST'])
def exit_app():
    logger.warning("Exit Wander")
    shutdown_server()
    # Send a response to the client immediately
    response = {"success": True, "message": "Server is shutting down..."}

    return jsonify(response)


# Values fetched once in the background at startup, so the first page render is INSTANT.
# (Doing the GitHub / IP calls inside index() made "/" slow on a poor connection, which
# stalled the loading window's poll and produced "Couldn't start the tunnel".)
_boot = {'ready': False, 'gh_version': None, 'gh_broadcast': '', 'country': None}
def _prefetch_boot():
    try: _boot['gh_version'] = get_github_version()
    except Exception: pass
    try: _boot['gh_broadcast'] = get_github_broadcast() or ''
    except Exception: pass
    try: _boot['country'] = get_user_country()
    except Exception: pass
    _boot['ready'] = True


@app.route('/healthz')
def healthz():
    # Instant liveness check — no network, no device. The loading window polls THIS so it
    # swaps to the app the moment Flask is up, independent of how long a page render takes.
    return 'ok', 200


@app.route('/')
def index():
    # Read the values prefetched at startup instead of blocking on the network here.
    github_version = _boot['gh_version']
    github_broadcast = _boot['gh_broadcast']
    user_locale = _boot['country']
    logger.info(f"Current platform: {platform}")
    logger.info(f"App Version = {APP_VERSION_NUMBER}")

    # Compare with the locally hardcoded version
    if github_version and github_version > APP_VERSION_NUMBER:
        version_message = f"Update available. New Version is {github_version}"

    elif github_version and github_version < APP_VERSION_NUMBER:
        version_message = f"Beta Testing. App version is {APP_VERSION_NUMBER} - github is {github_version}"

    else:
        version_message = None

    return render_template('map.html', version_message=version_message, github_broadcast=github_broadcast,
                           user_locale=user_locale, app_version_num=APP_VERSION_NUMBER,
                           app_version_type=APP_VERSION_TYPE, error_message=error_message, current_platform=platform,
                           sudo_message=sudo_message, google_maps_key=GOOGLE_MAPS_KEY)


def open_browser():
    time.sleep(2)  # Wait for the Flask app to start
    #webbrowser.open(f'http://localhost:{chosen_port}')
    browser = webbrowser.get()
    browser.open(f'http://localhost:{chosen_port}')


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0
    # with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    #     try:
    #         s.bind((' ', port))
    #         return False  # Port is available
    #     except OSError:
    #         return True  # Port is already in use


# Define try_bind_listener_on_free_port function
def try_bind_listener_on_free_port():
    global chosen_port
    min_port = 49215
    max_port = 65535

    # Check if --port argument is provided
    if args.port:
        chosen_port = args.port
    else:
        chosen_port = flask_port

    if is_port_in_use(chosen_port):
        chosen_port = random.randint(min_port, max_port)
    logger.info(f'Serving: http://localhost:{chosen_port}')
    return chosen_port


# ------------------------------------------------------------------ #
#  macOS auto-elevation (split privilege)                            #
#  The tunnel needs root, but a root GUI window won't reliably show.  #
#  So on double-click we open the WINDOW as the user and start a      #
#  headless tunnel BACKEND as root via one native password prompt.    #
# ------------------------------------------------------------------ #
def _start_parent_watchdog(parent_pid):
    """Elevated backend: quit when the user-facing window process disappears."""
    import time as _t
    def _watch():
        while True:
            try:
                os.kill(parent_pid, 0)          # root may signal-check any pid
            except Exception:
                logger.info(f"Window closed (parent {parent_pid} gone) — stopping backend.")
                os._exit(0)
            _t.sleep(1)
    threading.Thread(target=_watch, daemon=True).start()


def _relaunch_argv(port):
    """argv that re-runs THIS app as a headless backend, watching our pid."""
    if getattr(sys, 'frozen', False):
        base = [sys.executable]                 # PyInstaller .app binary
    else:
        base = [sys.executable, os.path.abspath(sys.argv[0])]
    return base + ['--no-browser', '--port', str(port), '--parent-pid', str(os.getpid())]


def _spawn_root_backend_via_prompt(port):
    """Start the headless backend as root via one native admin password prompt."""
    import shlex
    argv = _relaunch_argv(port)
    shell_cmd = ('PYTHONUNBUFFERED=1 nohup ' + ' '.join(shlex.quote(a) for a in argv) +
                 ' </dev/null >/tmp/wander-backend.log 2>&1 &')
    as_cmd = shell_cmd.replace('\\', '\\\\').replace('"', '\\"')
    prompt = "Wander Desktop needs administrator access to open a secure tunnel to your iPhone."
    osa = f'do shell script "{as_cmd}" with administrator privileges with prompt "{prompt}"'
    subprocess.run(['osascript', '-e', osa], check=True)   # raises if user cancels


def _wait_for_backend(port, timeout=25):
    import urllib.request, time as _t
    deadline = _t.time() + timeout
    while _t.time() < deadline:
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=4)
            return True
        except Exception:
            _t.sleep(0.5)
    return False


def _open_window(port):
    """Open the native window (as the current user) pointing at the local server."""
    import webview
    webview.create_window(
        "Wander Desktop",
        f"http://127.0.0.1:{port}",
        width=1240, height=840, min_size=(960, 640),
    )
    webview.start()   # blocks until the window closes


_LOADING_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{height:100%;margin:0}
  body{display:flex;align-items:center;justify-content:center;flex-direction:column;
    font-family:-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif;color:#fff;
    background:linear-gradient(135deg,#185FA5,#0f4c86)}
  .mark{width:78px;height:78px;border-radius:20px;background:rgba(255,255,255,.14);
    display:flex;align-items:center;justify-content:center;font-size:42px;margin-bottom:22px;
    box-shadow:inset 0 0 0 1px rgba(255,255,255,.28)}
  h1{font-size:22px;font-weight:700;margin:0 0 6px}
  p{opacity:.82;font-size:14px;margin:0}
  .spin{width:26px;height:26px;border:3px solid rgba(255,255,255,.3);border-top-color:#fff;
    border-radius:50%;animation:s .8s linear infinite;margin-top:24px}
  @keyframes s{to{transform:rotate(360deg)}}
</style></head><body>
  <div class="mark">&#128039;</div>
  <h1>Starting Wander&hellip;</h1>
  <p>Opening the secure tunnel to your iPhone</p>
  <div class="spin"></div>
</body></html>"""

_ERROR_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{height:100%;margin:0}
  body{display:flex;align-items:center;justify-content:center;flex-direction:column;
    font-family:-apple-system,Helvetica,Arial,sans-serif;color:#fff;text-align:center;padding:0 30px;
    background:linear-gradient(135deg,#185FA5,#0f4c86)}
  h1{font-size:20px;margin:0 0 10px}
  p{opacity:.85;font-size:14px;line-height:1.5;margin:0}
  code{background:rgba(0,0,0,.25);padding:2px 6px;border-radius:6px}
</style></head><body>
  <h1>Couldn&rsquo;t start the tunnel</h1>
  <p>The background service didn&rsquo;t come up. Check <code>/tmp/wander-backend.log</code>,<br>
  or launch from Terminal with <code>sudo</code>.</p>
</body></html>"""


def _open_window_loading(port):
    """Split path: show the window immediately with a loading screen, then swap to the
    app the moment the root backend answers. Turns the cold-start wait into a fast,
    branded 'Starting Wander…' screen instead of a blank 30-second delay."""
    import webview, time as _t, urllib.request as _u
    win = webview.create_window(
        "Wander Desktop", html=_LOADING_HTML,
        width=1240, height=840, min_size=(960, 640),
    )
    def _swap():
        deadline = _t.time() + 90
        while _t.time() < deadline:
            try:
                _u.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=4)
                win.load_url(f'http://127.0.0.1:{port}')
                return
            except Exception:
                _t.sleep(0.4)
        try:
            win.load_html(_ERROR_HTML)
        except Exception:
            pass
    webview.start(_swap)   # runs _swap after the GUI loop is ready; blocks until the window closes


def _run_window_inprocess(port):
    """Serve Flask + open the window in ONE process (already-root / non-mac / fallback)."""
    def _serve():
        app.run(debug=False, use_reloader=False, port=port, host='0.0.0.0', threaded=True)
    try:
        threading.Thread(target=_serve, daemon=True).start()
        _open_window(port)
    except Exception as e:
        logger.error(f"Native window unavailable ({e}); opening in browser instead")
        open_browser()
        _serve()


if __name__ == '__main__':
    #create_wander_folder()
    if is_windows:
        try:
            import pyi_splash

            pyi_splash.update_text('UI Loaded ...')
            logger.info("clear splash")
            pyi_splash.close()
        except:
            pass
        if not pyuac.isUserAdmin():
            print("Relaunching as Admin")
            # runAsAdmin() spawns an ELEVATED copy of this process and returns here in
            # the original (non-admin) one. Without exiting, the non-admin process would
            # fall through and start a SECOND, unelevated Flask + window. Exit so only
            # the elevated child continues to _run_window_inprocess().
            pyuac.runAsAdmin()
            sys.exit(0)
    #else:




    chosen_port = try_bind_listener_on_free_port()

    # Warm the GitHub/IP values in the background so the first page render never blocks on them.
    threading.Thread(target=_prefetch_boot, daemon=True).start()

    if args.no_browser:
        # Headless backend (this is also the elevated root process). Quit when the window closes.
        if getattr(args, 'parent_pid', None):
            _start_parent_watchdog(args.parent_pid)
        logger.info("--no-browser: serving Flask only, no app window")
        app.run(debug=False, use_reloader=False, port=chosen_port, host='0.0.0.0', threaded=True)

    elif sys.platform == 'darwin' and hasattr(os, 'geteuid') and os.geteuid() != 0:
        # Double-clicked on macOS without root: open the window as the user, and start the
        # tunnel backend as root via ONE native password prompt — no Terminal needed.
        logger.info("Not root on macOS — requesting admin once for the tunnel backend.")
        try:
            _spawn_root_backend_via_prompt(chosen_port)   # native password prompt
            # Window appears immediately with a "Starting Wander…" screen and swaps to the
            # app the moment the backend answers — no blank wait during cold-start.
            try:
                _open_window_loading(chosen_port)
            except Exception as e:
                logger.error(f"Window unavailable ({e}); opening in browser once backend is up.")
                if _wait_for_backend(chosen_port):
                    open_browser()
                import time as _t
                while True:
                    _t.sleep(3600)
        except Exception as e:
            # User cancelled the prompt or elevation failed — still open the app (tunnel limited).
            logger.error(f"Admin elevation cancelled/failed ({e}); running in-process.")
            _run_window_inprocess(chosen_port)

    else:
        # Already root (Terminal `sudo`) or non-macOS: original single-process behavior.
        _run_window_inprocess(chosen_port)




