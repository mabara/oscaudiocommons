#!/usr/bin python2.7
#freesoundquery.py
#Retrieval and audio playback of Freesound sounds using OSC server
#listening to text-based queries
#
#You need to specify a Freesound key below, otherwise requests won't work
#To request your own Freesound API key, go to:
#https://freesound.org/apiv2/apply
#
#Dependencies:
#pyosc: https://github.com/ptone/pyosc/
#
#Usage:
#python freesoundquery.py
#(uses default OSC address /query and port 7777)
#
#python freesoundquery.py <OSC address> <OSC port>
#(uses specified OSC address and port)
#example: python freesoundquery.py /play 8888
#
#Useful links:
#Freesound API: https://freesound.org/docs/api/
#Freesound API Search resources:
#https://freesound.org/docs/api/resources_apiv2.html#search-resources
#Freesound API Token authentication:
#https://freesound.org/docs/api/authentication.html#token-authentication
#
#Here, HTTP GET requests are handled with the Python requests package
#(http://docs.python-requests.org/en/master/). Help can be found here:
#https://flask-restless.readthedocs.io/en/stable/searchformat.html
#
#Note that the Python client for the Freesound API could also be used:
#https://github.com/MTG/freesound-python/blob/master/freesound.py
#Examples of use of Freesound Python client for the Freesound API:
#https://github.com/MTG/freesound-python/blob/master/examples.py
#
# Copyright (c) 2017-2018, Mathieu Barthet, Some Rights Reserved

from __future__ import print_function

import freesound,sys,os
from os.path import expanduser
import argparse
import math
from OSC import OSCServer
import subprocess
from multiprocessing import Process
from time import sleep
from threading import Thread
from Queue import Queue, Empty
import signal
from cStringIO import StringIO
import random
import requests
import json
import urllib
import types

home = expanduser("~")
sounddir = home + "/Documents/sounds"

PLAYERPATH = "/usr/bin/afplay"
OSC_PORT_DEFAULT = 7777

#to request your own Freesound API key, go to: https://freesound.org/apiv2/apply
#specify here your Freesound key (otherwise requests won't work)
FREESOUND_KEY = ""

url = 'http://freesound.org/apiv2/search/text/'

OSC_ADDRESS_DEFAULT = "/query"

WIFI_INT_DEFAULT = "en0" #default WiFi interface

MIN_DUR = 1 #minimum duration (s) for retrieved sounds
MAX_DUR = 20 #maximum duration (s) for retrieved sounds
SHOWRES = 10 #only displays first SHOWRES results from Freesound
SOUND_RANGE = 5 #play random sound within first SOUND_RANGE retrieved sounds

def download_sound(q,sound,dir):

	path=os.path.join(dir,sound["name"] + ".mp3")

	#this selects the type of audio file to download from Freesound
	url = sound["previews"]["preview-hq-mp3"]

	params = dict(token=FREESOUND_KEY)
	response = requests.get(url, params=params)

	print(urllib.unquote(response.url).decode('utf8'))

	try:
		assert response.status_code == 200 #response OK
		
		#stores the sound at specified location
		with open (path, 'wb') as f:
			f.write(response.content)

	except AssertionError:
		print('There is an issue with the HTTP GET request to download the sound. Check that you have specified a Freesound key.')

#Queries sounds from Freesound given text-based search and filtering options
def retrieve_sound(keyword):
	
	soundpath = [] #stays empty if no sounds can be found matching the criteria
	
	queue = Queue() #queue for process

	print("Query")

	#specifies the query through keyword and filtering options
	#For other filtering options, check the Freesound API Search resources:
	#https://freesound.org/docs/api/resources_apiv2.html#search-resources
	#here, the filters specify to list sounds which have a duration between
	#MIN_DUR and MAX_DUR, by decreasing rating order
	params = dict(query=keyword,fields="id,name,previews",sort="rating_desc",filter="duration:[%d TO %d]"%(MIN_DUR,MAX_DUR),token=FREESOUND_KEY)
	response = requests.get(url, params=params)
	restext = response.text

	print(urllib.unquote(response.url).decode('utf8'))

	resdic = json.loads(restext)

	try:
		assert response.status_code == 200 #response OK
	
		nsounds = resdic["count"]

		print("Number of results for query %s: %d"%(keyword, nsounds))

		results = resdic["results"]

		if nsounds>=1: #if there is at least 1 sound matching the criteria
			i=1
			#display first SHOWRES results in sys.stdout
			for sound in results:
				if (i == SHOWRES or i>nsounds):
					break
				print("Sound name: ",sound["name"])
				i=i+1

			#download random result within first SOUND_RANGE sounds if no of sounds
			#is greater than 1
			if nsounds==1:
				sound_index=0
			else:
				sound_index = random.randint(0,min(SOUND_RANGE,nsounds))
			sound = results[sound_index]
			print("Downloading ",sound["name"])

			soundpath = os.path.join(sounddir,sound["name"] + ".mp3")
			print("Sound download location: ",soundpath)

			if os.path.exists(soundpath) == 0: #if the file has not yet been downloaded
				#starts a process to download the sound
				p = Process(target=download_sound, args=(queue, sound, sounddir))
				p.start()
				p.join() # this blocks until the process terminates
				print("Sound downloaded.")

			else: #sound already exists
				print("Sound already exists.")
	
	except AssertionError:
		print('There is an issue with the HTTP GET request to query sounds. Check that you have specified a Freesound key.')
	
	return soundpath

def play_sound(soundpath):		
	if os.path.exists(soundpath):
		print("Sound downloaded, ready to be played!")

		#uses the afplay player to play the sound
		playcmd = "afplay %s"%'''"''' + soundpath + '''"'''
		print("About to execute following command:",playcmd)

		playcmdnoshell=["afplay","%s"%soundpath]
		pplay = subprocess.Popen(playcmdnoshell,shell=False,stderr=subprocess.PIPE)

	else:
		print("Sound can't be found at location.")

# from pyosc example:
# this method of reporting timeouts only works by convention
# that before calling handle_request() field .timed_out is
# set to False
def handle_timeout(self):
	self.timed_out = True

# adapted from pyosc example
def user_callback(path, tags, args, source):
	# query is determined by path:
	# we just throw away all slashes and join together what's left
	oscadd = ''.join(path.split("/"))
	print("osc address:", oscadd)
	# expected OSC message with tag containing 's'
	# args is a OSCMessage with data
	# source is where the message came from (in case you need to reply)
	#print ("Now do something with", user,args[2],args[0],1-args[1])
	keyword = args[0]
	print ("Process OSC address",oscadd,"with keyword",keyword)

	path = retrieve_sound(keyword)
	
	if path != []:
		print ("Finished retrieving sound.")
		play_sound(path)

# from pyosc example
def quit_callback(path, tags, args, source):
	# don't do this at home (or it'll quit blender)
	global run
	run = False

# from pyosc example
# user script that's called by the game engine every frame
def each_frame(server):

	# clear timed_out flag
	server.timed_out = False
	# handle all pending requests then return
	while not server.timed_out:
		server.handle_request()

def main():

	if len(sys.argv)>1:
		OSC_ADDRESS = str(sys.argv[1])
	else:
		OSC_ADDRESS = OSC_ADDRESS_DEFAULT

	if len(sys.argv)>2:
		OSC_PORT = int(sys.argv[2])
	else:
		OSC_PORT = OSC_PORT_DEFAULT

	if len(sys.argv)>3:
		WIFI_INT = str(sys.argv[3])
	else:
		WIFI_INT = WIFI_INT_DEFAULT

	#creates directory to store sounds
	if not os.path.exists(sounddir):
		os.makedirs(sounddir)
	print("Sound directory: ",sounddir)

	#example of use of pyosc,
	#see: https://github.com/ptone/pyosc/blob/master/examples/knect-rcv.py
	#we use here the WiFi interface provided on device en0
	ipcmd = "ipconfig getifaddr %s"%WIFI_INT
	print(ipcmd)
	ipaddress = os.popen(ipcmd).read().rstrip()
	print("IP address: ",ipaddress)
	server = OSCServer((ipaddress, OSC_PORT))
	server.timeout = 0
	global run
	run = True

	print("Listening to OSC address",OSC_ADDRESS,"on port",OSC_PORT)

	#python's way to add a method to an instance of a class
	server.handle_timeout = types.MethodType(handle_timeout, server)

	server.addMsgHandler(OSC_ADDRESS, user_callback)

	#sound query engine
	try:
		while run:
			#sleep(1)
			#call user script
			each_frame(server)
	except KeyboardInterrupt: #to quit program
		print("\n")
		pass
	server.close()

if __name__ == "__main__":
	main()
