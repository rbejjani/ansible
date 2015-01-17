#!/usr/bin/python

import os, os.path, sys
import pyudev

UDEV_PATH='/etc/udev/rules.d/72-multiseat.rules'
CONF_PATH='/etc/multiseat.conf'
USB_ID_PATH='/usr/share/multiseat/usb-logical-hubs.txt'

udev_context = pyudev.Context()

def write_conf(config_file, seat_list):
    try:
        f = open(config_file, 'w')
    except:
        print "Unable to write to %s" % (config_file, )
        return False
    f.write("# This file is autogenerated.  Please don't touch it.\n")
    for seat in seat_list:
        f.write('%s\n' % (seat,))
    f.close()

def read_conf(config_file):
    seat_list = []
    try:
        f = open(config_file, 'r')
    except:
        print "%s doesn't exist" % (config_file, )
        return []

    line = f.readline()
    while line != '':
        line = line.strip()
        if line.find('#') > -1:
            line = line[:line.find('#')].strip()
        if line != '':
            seat_list.append(line)
        line = f.readline()
    f.close()
    return seat_list

def get_hubs(usb_devices):
    # This is a bit hacky.  We check the device type and assume that a hub's
    # type starts with 9/0.  We then assume that the last number is the number
    # of logical hubs in the physical hub.  If it is two, we then skip the next
    # hub since it's really just part of the physical hub.  If it is three,
    # we're screwed and everything will be messed up. :(
    seat_list = []
    this_seat = []

    count = 1
    for device in udev_context.list_devices(subsystem='usb'):
        if not device.get('TYPE').startswith('9/0/'):
            continue

        if device.get('ID_VENDOR_ID') is None:
            continue  # No vendor id, not one of our hubs
    
        if device.get('ID_VENDOR_ID') is not None and device.get('ID_VENDOR_ID').lower() in ('8087', '1d6b'):
            continue  # These are builtin hubs, not external

        if device.get('ID_MODEL_ID') is None:
            continue  # Unknown model, so we'll ignore it

        end_num = 1
        for usb_item in usb_devices:
            if "%s:%s" % (device.get('ID_VENDOR_ID'), device.get('ID_MODEL_ID')) == usb_item[0]:
                end_num = int(usb_item[1])

        count -= 1
        if count == 0:
            count = end_num
            seat_list.append(device.get('ID_FOR_SEAT'))
    return seat_list

def get_graphics(id_path):
    for device in udev_context.list_devices(subsystem='graphics'):
        if device.get('ID_FOR_SEAT') is None:
            continue  # No seat ID, not primary card
        if device.get('ID_PATH') == id_path:
            return device.get('ID_FOR_SEAT')
    return ''

def get_video():
    seat_list = []
    for device in udev_context.list_devices(subsystem='drm'):
        done = False
        if device.get('ID_FOR_SEAT') is None:
            continue  # No seat ID, not primary card
        for i in seat_list:
            if device.get('ID_FOR_SEAT') == i[0]:
                done = True
                break
        if done:
            continue
        graphics_seat_id = get_graphics(device.get('ID_PATH'))
        seat_list.append((device.get('ID_FOR_SEAT'), graphics_seat_id)) 
    return seat_list

usb_devices = []
for item in read_conf(USB_ID_PATH):
    usb_item = item.split(',')
    for num in range(0, len(usb_item)):
        usb_item[num] = usb_item[num].strip()
    usb_devices.append(usb_item)

hubs = get_hubs(usb_devices)
hubs.sort()
hubs.reverse()
vcards = get_video()
vcards.sort()
print vcards

seats = len(vcards) if len(vcards) < len(hubs) else len(hubs)
if len(hubs) < len(vcards):
    print "This computer is currently short a hub: %i hubs, %i video cards" % (len(hubs), len(vcards))
elif len(vcards) < len(hubs):
    print "This computer has more usb hubs than video cards: %i hubs, %i video cards" % (len(hubs), len(vcards))

if seats <= 1: # Don't bother with multiseat rules with <= 1 hub
    if os.path.exists(UDEV_PATH):
        try:
            os.unlink(UDEV_PATH)
        except:
            print "Unable to remove %s" % (UDEV_PATH, )
            sys.exit(1)
    if os.path.exists(CONF_PATH):
        try:
            os.unlink(CONF_PATH)
        except:
            print "Unable to remove %s" % (CONF_PATH, )
            sys.exit(1)
    os.system('udevadm control --reload')
    os.system('udevadm trigger')
    sys.exit(0)

old_seats = read_conf(CONF_PATH)
for seat in hubs:  # If any of our current hubs isn't in multiseat.conf, recalculate
    if seat not in old_seats:
        old_seats = []
        continue

if len(hubs) <= len(old_seats): # All present and accounted for, let's get out of here
    sys.exit(0)

# Write out new udev rules
try:
    f = open(UDEV_PATH, 'w')
except:
    print "Unable to open %s for writing" % (UDEV_PATH, )
    sys.exit(1)

f.write("# This file has been automatically generated.  Please do not change it.\n\n")
for x in reversed(range(0, seats)):
    f.write('# Seat %i' % (x,))
    if x == 0:
        f.write(' - Commented out because the default is seat0')
    f.write('\n')
    for dev in hubs[(seats-1) - x], vcards[x][0], vcards[x][1]:
        suffix = '-%i' % (x,)
        if x == 0:
            suffix = '%i' % (x,)
            f.write("#")
        f.write('TAG=="seat", ENV{ID_FOR_SEAT}=="%s", ENV{ID_SEAT}="seat%s"\n' % (dev, suffix))
f.close()

write_conf(CONF_PATH, hubs[:seats])

# Reload rules
os.system('udevadm control --reload')
os.system('udevadm trigger') 
