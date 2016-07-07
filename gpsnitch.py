#!/usr/bin/env python3
# coding=utf-8

"""
gpsnitch.py is tool that will try and detect if the GPS is being spoofed. 

It leverages gps3 python library. https://github.com/wadda/gps3

The human.py in that library's examples is the basis for this script

command:
    gpsnitch.py.py
    
The configuration of the checking is handled by gpsnitch.cfg and the logging configuarion by logging.cfg

"""

import sys
import sqlite3
import configparser
import logging
import logging.config
from geopy.distance import vincenty
from datetime import datetime
from gps3 import gps3

__author__ = 'Karit @nzkarit'
__copyright__ = 'Copyright 2016 Karit'
__license__ = 'MIT'
__version__ = '0.1'

def monitor():
    """
    Monitors GPSd and looks for traits of spoof GPS signals.
    """
    
    #Counter for number of alerts. This is used when require X triggers in subsequence iterations before alerting that spoofing has been detected
    alert_count = 0
    alert_threshold_number_of_iterations = cfg.getint('checks', 'alert_threshold_number_of_iterations')
    
    #Number of checks in an iteration which need to fail before marking the iteration as a fail.
    alert_threshold_number_of_checks = cfg.getint('checks','alert_threshold_number_of_checks')

    for new_data in gps_socket:
        if new_data:
            gps_fix.refresh(new_data)
            if gps_fix.TPV['mode'] != 'n/a' and gps_fix.TPV['mode'] >= 2:
                
                fix = get_fix_details()

                check_failure_count = 0
                check_failure_count += check_time_offset(fix)
                check_failure_count += check_snr_value(fix)
                check_failure_count += check_snr_range(fix)
                check_failure_count += check_location_stationary(fix)
                
                #See enough indivudal check failures in iteration to see if iteration as a whole is a failure
                if check_failure_count >= alert_threshold_number_of_checks:
                    alert_count += 1
                else:
                    if alert_count > 0:
                        alert_count -= 1    
                
                put_fix_in_db(fix, check_failure_count, alert_count)
                
                if alert_count >= alert_threshold_number_of_iterations:
                    logger.critical('Spoofing Detected')
                    logger.info('Spoofing Details. Alert Count: %s. Alert Threshold: %s. Check Failure Count: %s. Check Failure Count Threshold: %s' % (alert_count,  alert_threshold_number_of_iterations, check_failure_count, alert_threshold_number_of_checks))
                else:
                    logger.debug('No Spoofing. Alert Count: %s. Alert Threshold: %s. Check Failure Count: %s. Check Failure Count Threshold: %s' % (alert_count,  alert_threshold_number_of_iterations, check_failure_count, alert_threshold_number_of_checks))
            else:
                logger.debug('No fix')

def get_fix_details():
    """
    Will take the current GPS fix and store it in a dictionary
    
    :return: Dictionary of the GPS fix
    """
    fix = {}
    fix['time'] = gps_fix.TPV['time']
    time = datetime.strptime(fix['time'], '%Y-%m-%dT%H:%M:%S.%fZ')
    time = time.replace(tzinfo=None)
    diff = time - datetime.utcnow()
    fix['time_offset'] = diff.total_seconds()
    fix['mode'] = gps_fix.TPV['mode']
    fix['latitude'] = gps_fix.TPV['lat']
    fix['longitude'] = gps_fix.TPV['lon']
    fix['altitude'] = gps_fix.TPV['alt']
    fix['latitude_error'] = gps_fix.TPV['epy']
    fix['longitude_error'] = gps_fix.TPV['epx']
    fix['altitude_error'] = gps_fix.TPV['epv']
    fix['speed'] = gps_fix.TPV['speed']
    fix['climb'] = gps_fix.TPV['climb']
    fix['speed_error'] = gps_fix.TPV['eps']
    fix['climb_error'] = gps_fix.TPV['epc']    
    satellites = []
    if gps_fix.SKY['satellites'] != 'n/a':
        for satellite in gps_fix.SKY['satellites']:
            row = {}
            row['prn'] = satellite['PRN']
            row['snr'] = satellite['ss']
            row['azimuth'] = satellite['az']
            row['elevation'] = satellite['el']
            row['used'] = satellite['used']
            satellites.append(row)
    fix['satellites'] = satellites
    return fix

def put_fix_in_db(fix, check_failure_count, alert_count):
    """
    Will take a GPS fix and summary of alerts for the iteration and place it in sqlite database
    
    :param fix: The GPS fix object from get_fix_details()
    :param check_failure_count: Number of failed checks in the iteration
    :param alert_count: Running total of pervious iterations that also had overal failures
    """
    if log_to_db:
        c = conn.cursor()
        c.execute('INSERT INTO fix (time, time_offset, mode, latitude, latitude_error, longitude, longitude_error, altitude, altitude_error, speed, speed_error, climb, climb_error, check_failure_count, alert_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (fix['time'], fix['time_offset'], fix['mode'], fix['latitude'], fix['latitude_error'], fix['longitude'], fix['longitude_error'], fix['altitude'], fix['altitude_error'], fix['speed'], fix['speed_error'], fix['climb'], fix['climb_error'], check_failure_count, alert_count))
        for satellite in fix['satellites']:
            c.execute('INSERT INTO satellites (time, prn, snr, azimuth, elevation, used) VALUES (?, ?, ?, ?, ?, ?)', (fix['time'], satellite['prn'], satellite['snr'], satellite['azimuth'], satellite['elevation'], satellite['used']))
        conn.commit()
        c.close()

def check_time_offset(fix):
    """
    Checks if the time from GPS differs too greatly from the internal clock. 
    
    The configuartion for this is gpsnitch.cfg
    
    :param fix: The GPS fix object from get_fix_details()
    :return: 0 for a pass and 1 for the check failing
    """
    time_offset_enabled = cfg.getboolean('checks', 'time_offset_enabled')    
    if time_offset_enabled:
        time_offset = cfg.getfloat('checks', 'time_offset')
        if abs(fix['time_offset']) > time_offset:
            logger.warn('Fail Time Offset. Time Offset: %s.' % (fix['time_offset']))
            return 1
    return 0

def check_snr_value(fix):
    """
    Checks if SNR values are greater than threshold. 
    
    The configuartion for this is gpsnitch.cfg
    
    :param fix: The GPS fix object from get_fix_details()
    :return: 0 for a pass and 1 for the check failing
    """
    snr_value_enabled = cfg.getboolean('checks', 'snr_value_enabled')    
    if snr_value_enabled:
        snr_value = cfg.getint('checks', 'snr_value')
        if fix['satellites'] is not None:
            fail = False
            for satellite in fix['satellites']:
                if satellite['snr'] > snr_value:
                    logger.warn('Fail SNR. PRN: %s. SNR: %s.' % (satellite['prn'], satellite['snr']))
                    fail = True
            if fail:
                return 1
    return 0

def check_snr_range(fix):
    """
    Checks if SNR range values are less than threshold. 
    
    The configuartion for this is gpsnitch.cfg
    
    :param fix: The GPS fix object from get_fix_details()
    :return: 0 for a pass and 1 for the check failing
    """
    snr_range_enabled = cfg.getboolean('checks', 'snr_range_enabled')    
    if snr_range_enabled:
        snr_range = cfg.getint('checks', 'snr_range')
        snr_range_min_satellites = cfg.getint('checks', 'snr_range_min_satellites')
        if fix['satellites'] is not None:
            snr = []
            for satellite in fix['satellites']:
                if satellite['used']:
                    snr.append(satellite['snr'])
            if len(snr) >= snr_range_min_satellites:
                if (max(snr) - min(snr)) < snr_range:
                    logger.warn('Fail SNR Range. Range: %s.' % ((max(snr) - min(snr))))
                    return 1
    return 0

def check_location_stationary(fix):
    """
    Checks for assuming the the device is stationary. 
    
    The configuartion for this is gpsnitch.cfg
    
    :param fix: The GPS fix object from get_fix_details()
    :return: 0 for a pass and 1 or greater for the checks failing
    """
    location_stationary_enabled = cfg.getboolean('checks', 'location_stationary_enabled')    
    check_failure_count = 0
    if location_stationary_enabled:
        location_stationary_latitude = cfg.getfloat('checks', 'location_stationary_latitude')
        location_stationary_longitude = cfg.getfloat('checks', 'location_stationary_longitude')
        location_stationary_altitude = cfg.getfloat('checks', 'location_stationary_altitude')
        lat1 = (fix['latitude'], fix['longitude'])
        lat2 = (location_stationary_latitude, fix['longitude'])
        lat_diff = vincenty(lat1, lat2).meters
        if abs(lat_diff) > fix['latitude_error']:
            logger.warn('Fail Latitidue Difference to great. Diff: %s. Lat Error: +/-%s.' % (lat_diff, fix['latitude_error']))
            check_failure_count += 1
        long1 = (fix['latitude'], fix['longitude'])
        long2 = (fix['latitude'], location_stationary_longitude)
        long_diff = vincenty(lat1, lat2).meters
        if abs(long_diff) > fix['longitude_error']:
            logger.warn('Fail Longitude Difference to great. Diff: %s. Long Error: +/-%s.' % (long_diff, fix['longitude_error']))
            check_failure_count += 1
        alt_diff = fix['altitude'] - location_stationary_altitude
        if abs(alt_diff) > fix['altitude_error']:
            logger.warn('Fail Altitude Difference to great. Diff: %s. Alt Error: +/-%s.' % (alt_diff, fix['altitude_error']))
            check_failure_count += 1
        if abs(fix['speed']) >= fix['speed_error']:
            logger.warn('Fail Speed outside of error. Speed: %s. Speed Error: +/-%s.' % (fix['speed'], fix['speed_error']))
            check_failure_count += 1
        if abs(fix['climb']) >= fix['climb_error']:
            logger.warn('Fail Climb outside of error. Climb: %s. Climb Error: +/-%s.' % (fix['climb'], fix['climb_error']))
            check_failure_count += 1
    return check_failure_count

def connect_to_gpsd():
    """
    Connect to the GPSd deamons
    
    The configuartion for this is gpsnitch.cfg
    """
    logger.debug('Connecting to GPSd')
    host = cfg.get('gpsd', 'host')
    port = cfg.getint('gpsd', 'port')
    protocol = cfg.get('gpsd', 'protocol')
    global gps_socket
    global gps_fix
    gps_socket = gps3.GPSDSocket()
    gps_socket.connect(host, port)
    gps_socket.watch(gpsd_protocol=protocol)
    gps_fix = gps3.Fix()
    logger.debug('Connected to GPSd')
    
def connect_to_db():
    """
    Connect to the sqlite database
    
    The configuartion for this is gpsnitch.cfg
    """
    if log_to_db:
        logger.debug('Connecting to DB')
        global conn 
        filename = cfg.get('database' , 'db_filename')
        conn = sqlite3.connect(filename)
        logger.debug('Connected to DB')
    else:
        logger.debug('Not Logging to DB')
            
def shut_down():
    """
    Closes connections
    """
    if log_to_db:
        conn.close()
        logger.debug('Closed DB')
    gps_socket.close()
    logger.debug('Closed connection to GPSd')
    print('Keyboard interrupt received\nTerminated by user\nGood Bye.\n')
    logger.info('Keyboard interrupt received. Terminated by user. Good Bye.')
    sys.exit(1)

def start_script():
    global cfg
    cfg = configparser.ConfigParser()
    cfg.read('gpsnitch.cfg')
    
    global logger
    logging.config.fileConfig('logging.cfg')
    logger = logging.getLogger(__name__)
    logger.info('Starting gpsnitch')

    connect_to_gpsd()

    global log_to_db
    log_to_db = cfg.getboolean('database', 'log_to_db')
    connect_to_db()
    
    try:
        monitor()
    except KeyboardInterrupt:
        shut_down()
    except (OSError, IOError) as error:
        gps_socket.close()
        if log_to_db:
            conn.close()
        sys.stderr.write('\rError--> {}'.format(error))
        logger.error('Error--> {}'.format(error))
        sys.stderr.write('\rConnection to gpsd at \'{0}\' on port \'{1}\' failed.\n'.format(cfg.get('gpsd', 'host'), cfg.getint('gpsd', 'port')))
        logger.error('Connection to gpsd at \'{0}\' on port \'{1}\' failed.'.format(cfg.get('gpsd', 'host'), cfg.getint('gpsd', 'port')))
        sys.exit(1)

if __name__ == '__main__':
    start_script()
