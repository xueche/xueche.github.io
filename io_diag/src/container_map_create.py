#!/bin/python
"""
create the map between container_name and container_id
"""

import os
import subprocess
import time

CONTAINER_PATH = '/matrix/run/container'
ROOT_CGROUP_NAME = 'v2'
GET_CPATH_SHELL = '/io_diag/src/get_container_path.sh'
GET_CID_BIN = '/io_diag/src/get_container_id'

class ContainerMapCreate(object):
	"""
	create container map
	"""
	def __init__(self):
		self.container_name = []
	
	def _get_containers(self):
		"""
		get the container name list
		"""
		if not os.path.exists(CONTAINER_PATH):
			print("container path not exits!")
			return

		for c_name in os.listdir(CONTAINER_PATH):
			if c_name.startswith('.') or c_name.endswith('.MaTRIX'):
				continue
			if not os.path.isfile(os.path.join(CONTAINER_PATH, c_name)):
				continue
			self.container_name.append(c_name)
		
		self.container_name.append(ROOT_CGROUP_NAME)

	def _get_cg_path(self, cn):
		"""
		get cg path by container name
		"""
		if not os.path.isfile(GET_CPATH_SHELL):
			print("get_container_path.sh file not exits!")
			return ""

		cmd = 'sh %s %s' % (GET_CPATH_SHELL, cn)
		ret = os.popen(cmd).read()
		#print(ret)
		return ret

	def _execute(self, cmd, shell=True, timeout=None):
		"""
		execute a cmd in a subprocess, and return the object
		"""
		process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=shell)

       		now = time.time()
       		while process.poll() is None:
        		if timeout and now + timeout <= time.time():
            			process.kill(i)
			time.sleep(0.1)
	
		outs,errs = process.communicate()
		if errs:
			print(errs)
			return -1
	   	str = outs.split('\n')
		str = str[0].split(':')
		return str[1]

	def _create_container_map(self):
		"""
		create container map
		"""
		cid_dict = {}
		if not os.path.isfile(GET_CID_BIN):
			print("get_container_id file not exits!")
			return cid_dict

		self._get_containers()
		for c in self.container_name:
			path = self._get_cg_path(c)
			if path is None or not os.path.exists(path):
				continue
			#print('add container:%s' % c)
		   	cmd = '%s -p %s -d' % (GET_CID_BIN, path)
		   	#print(cmd)
		   	cgid = self._execute(cmd, 2)
			if cgid > 0:
				if c == ROOT_CGROUP_NAME:
					cid_dict[cgid] = "root"
				else:
					cid_dict[cgid] = c
			
		return cid_dict

