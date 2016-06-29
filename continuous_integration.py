#!/usr/bin/python
import argparse, datetime, os, psycopg2, subprocess, sys, collections
import tempfile
import shutil
import yaml
import json
#from tendo import singleton
import logging

_mapping_tag = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG

def dict_representer(dumper, data):
    return dumper.represent_dict(data.iteritems())

def dict_constructor(loader, node):
    return collections.OrderedDict(loader.construct_pairs(node))

yaml.add_representer(collections.OrderedDict, dict_representer)
yaml.add_constructor(_mapping_tag, dict_constructor)

LOG_FILE_LOCATION = "~/.cintegration/log"
LOG_ERROR_FILE_LOCATION = "~/.cintegration/logError"

logging.basicConfig(filename=os.path.expanduser(LOG_ERROR_FILE_LOCATION),
                            filemode='a',
                            format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                            datefmt='%H:%M:%S',
                            level=logging.DEBUG)
logging.info("Running CIntegration")

logger = logging.getLogger('CIntegration')

try:
	def time_now():
		a = datetime.datetime.now()
		return "%d:%d:%d" % (a.hour, a.minute, a.second)

	print "[+] Starting... "+time_now()

	def delete_content_of_file(fName):
		subprocess.check_output("echo '' > "+fName, shell=True)

	def setup_tables(cur):
		cur.execute('''
		CREATE TABLE IF NOT EXISTS CI_Project_Manager(
		Id serial primary key not null,
		directory text
		);''')	

		try:
			cur.execute('''CREATE TYPE AprovalStatus AS ENUM
		(
			'APROVED', 'REPROVED_FAILED_TEST'	
		)''')
		except:
			pass

		cur.execute('''
		CREATE TABLE IF NOT EXISTS CI_Commit_History(
		Id serial primary key not null,
		hash char(10) not null,
		date timestamp not null,
		status AprovalStatus,	
		project int references CI_Project_Manager(Id)
					ON DELETE CASCADE ON UPDATE CASCADE,
		cli_response text
		)''')

	parser = argparse.ArgumentParser(description='Manage the integration of source code on git server and test and deploy for end user', prog='CIntegration')
	parser.add_argument('-cl','--clear-log', help='Clear the log created by this program', action='store_true')
	parser.add_argument('-vl','--view-log', help='View the log in real time', action='store_true')
	parser.add_argument('-a', '--add', help='Add repo directory to manager')
	parser.add_argument('-r', '--remove', help='Remove repo from management')
	parser.add_argument('-f', '--file', help='File with json access to the database, case not used, %prog will search for enviroment variables')
	args = parser.parse_args()



	def connect():
		ac = []
		if args.file:
			ac = json.loads(open(args.file).read())
		else:
			ac = os.environ
		conn = psycopg2.connect(database=ac['LF_DB_NAME'], user=ac['LF_DB_USER'], password=ac['LF_DB_PASSWORD'], host=ac['LF_DB_HOST'], port=ac['LF_DB_PORT'])
		cur = conn.cursor()
		conn.autocommit = True
		return (conn, cur)

	if args.clear_log:
		print '['+time_now()+'+] Clearing log as requested'
		delete_content_of_file(LOG_FILE_LOCATION)
	elif args.view_log:
		subprocess.call('tail -f '+LOG_FILE_LOCATION, shell=True)
	elif args.add or args.remove:
		#singleton.SingleInstance()
		conn, cur = connect()
		setup_tables(cur)
		if args.add:
			cur.execute("INSERT INTO CI_Project_Manager (directory) VALUES(%s)" , (args.add,) )
		else:
			cur.execute("DELETE FROM CI_Project_Manager WHERE directory = %s" , (args.remove,) )
	else:
		#singleton.SingleInstance()
		conn, cur = connect()
		setup_tables(cur)
		cur.execute("SELECT * FROM CI_Project_Manager")
		projects = cur.fetchall()
		print "Projects to process:", len(projects)
		for Id, directory in projects:	
		
			remote = str(subprocess.check_output("cd "+directory+" && git remote -v", shell=True)).split('\t')[1].split(" ")[0]
			print "["+time_now()+"+] Starting verification for project",os.path.basename(directory)
			dirpath = tempfile.mkdtemp() 
			print "["+time_now()+"+] Located at",dirpath
			popen = subprocess.Popen("cd "+dirpath+" && git clone --progress "+remote+" "+dirpath, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, universal_newlines=True, shell=True)
			stdout_lines = iter(popen.stdout.readline, "")
			for stdout_line in stdout_lines:	
				if "Receiving objects" in stdout_line or "Compressing objects" in stdout_line or "Resolving deltas" in stdout_line:
					sys.stdout.write("\r"+stdout_line.replace("\n", ""))
					sys.stdout.flush()
					if "100%" in stdout_line:
						print ""
				else:
					print ""
					print stdout_line,
			popen.stdout.close()
			return_code = popen.wait()
			lastHash = subprocess.check_output("cd "+dirpath+" && git log -1 --format=%h", shell=True)
			cur.execute("SELECT COUNT(*) FROM CI_Commit_History WHERE hash=%s", (lastHash,))
			if cur.fetchone()[0] > 0:
				print "[!] Already tested this commit, skiping"
				continue
			yamlFile = os.path.join(dirpath, ".lackingfaces_ci.yaml")
			if os.path.isfile(yamlFile):
				stest = None
				try:
					stest = yaml.load(open(yamlFile))
				except Exception as e:
					print "[!] Invalid YAML file!\n"+str(e)
					continue			
				verificationSuccess = True
				if stest == None:
					print "[!] Invalid yaml file! Aborting"
					continue
				if 'build' not in stest:
					print "[!] No build section in yaml file, aborting"
					continue
				if len(stest['build']) == 0:
					print "[!] No method for build in section, aborting"
					continue
				resp = ""
				for etest in stest['build']:
					resp += "Testing " + etest+"\n\n"
					print "Testing",etest
					popen = subprocess.Popen("cd "+dirpath+" && "+stest['build'][etest] , stderr=subprocess.STDOUT, stdout=subprocess.PIPE, universal_newlines=True, shell=True)
					stdout_lines = iter(popen.stdout.readline, "")
					for stdout_line in stdout_lines:
						print stdout_line,
						resp += stdout_line
					popen.stdout.close()
					rc = popen.wait()
					if rc != 0:				
						verificationSuccess = False
						print "Test failed!"
					else:
						print "OK!"
				cur.execute("INSERT INTO CI_Commit_History (hash, date, status, project, cli_response) VALUES (%s, %s, %s, %s, %s)",
(lastHash,datetime.datetime.now(), 'APROVED' if verificationSuccess else 'REPROVED_FAILED_TEST', Id, resp))	
				if verificationSuccess:
					subprocess.call("cd "+directory+" && git pull", shell=True)
					print "Verification and Deploy succefuly made"
			else:
				print "[!] No valid .lackingfaces_ci.yaml file for test!"
			shutil.rmtree(dirpath)
			print "[+] End verification"
	
except Exception as e:
	logger.exception(e)
	print "Error!\n"+str(e)




