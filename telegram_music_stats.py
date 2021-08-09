#!/usr/bin/env python

import sys, time, os, re, json, ast, pprint
from pymongo import MongoClient

def print_usage():
	"""
	Prints usage.
	"""
	print("Usage: telegram_music_stats.py logfile")
	sys.exit()

def follow_log(logfile):
	"""

	"""
	logfile.seek(0,2)
	while True:
		line = logfile.readline()
		if not line:
			time.sleep(0.1)
			continue
		yield line
	
def process_log(line, db):
	"""
	"""
	match = re.search(r'New update: ({.*})', line.strip())
	if match:
		update_dict=ast.literal_eval(match.group(1))
		pprint.pprint(update_dict)
		db.updates.insert_one(update_dict)	

def main():
	if len(sys.argv) != 2: print_usage()
	
	bot_name = os.path.basename(sys.argv[1]).partition('.')[0]
	mongo_client = MongoClient()	
	db = mongo_client[bot_name]
	
	logfile = open(sys.argv[1])
	loglines = follow_log(logfile)
	for line in loglines:
		process_log(line,db)

if __name__ == '__main__': main()
