# Wander - FAQ
Current Version: v2.2.0

# What's new
- Map Enhancements: New Provider, new look
- Map Enahncements: Import geojson and GPX files for all your previously saved locations
- Map Enahncements: Save your favorite locations or tracks to geojson files and share with friends!
- Map Enahncements: Draw your own track on the map
- Map Enahncements: Select the playback speed (walk, run, ride, drive or custom)
- Resolved: Errno 54: Connection Refused by Remote Host (error due to too many open connections)


# Create Tracks on the map
- Select the `Line` button
- Choose a start location on the map
- Click from point to point to create a route / track on the map
- Select `Download` to save your track
  

# Import / Save markers on the map
- Select the `Upload` button
- Choose a file with coordinates / markers / GPX tracks
- Information is loaded to the map
- You can select the `Download` button to save your markers to a file
- 

# Replay a track / auto-walk with speed selection
- Select the `Upload` button
- Choose a GPX / geojson file with playback coordinates
- Select the `Speed` button
- Choose the playback speed (walk = 6km/h, run = 12km/h, ride = 20km/h, drive = 50km/h, custom = 3 digit input in km/h)
- 

# Update / Save markers on the map
- Double-click the map to place an icon
- Right-click the icon to pop-up the properties of the marker
- Enter the details of the location
- Select `Download` to save your marker information to a file
- 





# Untethered Wifi connection
Live life untethered. No longer be tied to using a USB cable to connect the device and spoof location!
Thanks to some updates in <a href="https://github.com/doronz88/pymobiledevice3">pymobiledevice3</a> I have integrated wifi capability into **Wander**

You will need to connect at least once with a USB cable to create / accept the pairing request. This enables the wifi connection to then be discovered after.



**Please note**: 
Wifi devices may not appear when the phone is locked. 
Wifi is also dependant on your network. The devices should be on the same LAN / Subnet as bonjour can have issues across network ranges / networking devices.
If your device doesn't appear in the list. Unlock your device, hit refresh a few times. Wifi is not a guaranteed connection method etc etc but it's damn cool and works well!


# Location Notifications

## How to install Mac version
MacOS installation has been improved to use the Apple DMG process
I don't have a developer certificate to sign the app, so you will get some popups the first time after downloading.
Open the DMG file then you can run Wander directly there, or you can drag it into your Applications folder



### Additional Mac installation steps - One time only

<br>
Open `Settings` 
Select `Privacy & Security`
Select `Open`
<br>
<br>

## FAQ / Troubleshooting

### Windows Specific

If you are running as administrator and receive `Unable to create tunnel within timeout` there is most likely a Windows firewall issue. When Wander runs for the first time, you receive a network access prompt when the tunnel adapter is created. In some cases, only a single option is selected. You need to select both **Public** and **Private** networks.

If Wander is already installed, you can change this setting by going into:
- `Control Panel - System and Security`
- Select `Allow an app through Windows Firewall`
- Select `Change settings`
- Scroll down to the entry for `Wander`
- Your options here are:

1. Allow both `Public` and `Private`
2. Delete the entry for Wander. Re-run Wander and when prompted to allow connects - select both checkboxes

### Figure 1 - Windows Firewall in Control Panel


### Figure 2 - Windows firewall incoming rules

### Figure 3 - Network adapter pop-up on first run

### Supported iOS
All - iOS 17 and below

### Supported OS
Windows 64-bit
MacOS ARM
MacOS Intel
Linux - Ubuntu 22.04

# Need more help?
